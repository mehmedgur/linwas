#!/bin/bash
# Linwas .deb paketini gömülü Python + PySide6 ile derler.
# Kullanım: packaging/build-deb.sh <paket-sürümü>     ör. 2.0.0~dev12
# Gereken: internet erişimi, curl, sha256sum, dpkg-deb. Çeviriler önceden derlenmiş olmalı
# (scripts/compile-translations.sh).
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
VERSION=${1:?Kullanım: packaging/build-deb.sh <paket-sürümü>}
ARCH=amd64

# Gömülü Python: python-build-standalone (astral-sh) — sürüm ve sağlama toplamı sabitlenmiştir.
PBS_TAG=20261003
PY_VERSION=3.12.15
PY_ASSET="cpython-${PY_VERSION}+${PBS_TAG}-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
PY_SHA256=731af898886c5f821890dc901eca3c651cca8e51fa7308c159d12a1194aeac91
PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/${PY_ASSET//+/%2B}"

PYSIDE_SPEC="PySide6-Essentials>=6.8,<7"

BUILD="$ROOT/build"
PKG="$BUILD/pkg"
DL="$BUILD/download"
RUNTIME="$PKG/opt/linwas/runtime"

if ! ls "$ROOT"/linwas/i18n/*.qm >/dev/null 2>&1; then
    echo "HATA: Derlenmiş çeviri (.qm) yok. Önce scripts/compile-translations.sh çalıştırın." >&2
    exit 1
fi

rm -rf "$PKG"
mkdir -p "$PKG" "$DL"

echo "==> Gömülü Python indiriliyor: $PY_ASSET"
if [ ! -f "$DL/$PY_ASSET" ]; then
    curl -fsSL --retry 3 -o "$DL/$PY_ASSET" "$PY_URL"
fi
echo "$PY_SHA256  $DL/$PY_ASSET" | sha256sum -c -

mkdir -p "$PKG/opt/linwas"
tar -xzf "$DL/$PY_ASSET" -C "$PKG/opt/linwas"
mv "$PKG/opt/linwas/python" "$RUNTIME"

echo "==> PySide6 ve Linwas gömülü Python'a kuruluyor"
"$RUNTIME/bin/python3" -m pip install --no-cache-dir --disable-pip-version-check "$PYSIDE_SPEC"
"$RUNTIME/bin/python3" -m pip install --no-cache-dir --disable-pip-version-check --no-deps "$ROOT"
# Hangi PySide6 sürümü ve platform etiketi (glibc gereksinimi) kuruldu? CI'da not olarak yaz.
PYSIDE_INFO=$("$RUNTIME/bin/python3" - <<'PY'
import importlib.metadata as m
dist = m.distribution("PySide6_Essentials")
tags = [line.split(": ", 1)[1] for line in dist.read_text("WHEEL").splitlines()
        if line.startswith("Tag: ")]
print(f"PySide6-Essentials {dist.version} tags={','.join(tags)}")
PY
)
echo "$PYSIDE_INFO"
if [ -n "${GITHUB_ACTIONS:-}" ]; then
    echo "::notice title=Gomulu PySide6::$PYSIDE_INFO"
fi
# pip'in kendi önbellek ve derleme artıkları pakette gereksiz.
find "$RUNTIME" -type d -name "__pycache__" -prune -exec rm -rf {} +

echo "==> Başlatıcı, masaüstü girişi ve simge"
install -D -m 0755 "$ROOT/packaging/linwas-launcher.sh" "$PKG/usr/bin/linwas"
install -D -m 0644 "$ROOT/packaging/linwas.desktop" "$PKG/usr/share/applications/linwas.desktop"
install -D -m 0644 "$ROOT/linwas/resources/linwas.svg" \
    "$PKG/usr/share/icons/hicolor/scalable/apps/linwas.svg"

echo "==> Root helper ve polkit eylemi"
install -D -m 0755 "$ROOT/packaging/linwas-helper.sh" "$PKG/usr/lib/linwas/linwas-helper"
install -D -m 0644 "$ROOT/packaging/org.linwas.helper.policy" \
    "$PKG/usr/share/polkit-1/actions/org.linwas.helper.policy"

echo "==> Otomatik güncelleme zamanlayıcısı"
install -D -m 0755 "$ROOT/packaging/linwas-autoupdate.sh" "$PKG/usr/lib/linwas/linwas-autoupdate"
install -D -m 0644 "$ROOT/packaging/systemd/linwas-autoupdate.service" \
    "$PKG/usr/lib/systemd/system/linwas-autoupdate.service"
install -D -m 0644 "$ROOT/packaging/systemd/linwas-autoupdate.timer" \
    "$PKG/usr/lib/systemd/system/linwas-autoupdate.timer"

echo "==> Güç planları servisi ve masaüstü ajanı"
install -D -m 0755 "$ROOT/packaging/linwas-power.sh" "$PKG/usr/lib/linwas/linwas-power"
install -D -m 0755 "$ROOT/packaging/linwas-power-switch.sh" "$PKG/usr/lib/linwas/linwas-power-switch"
install -D -m 0755 "$ROOT/packaging/linwas-power-agent.sh" "$PKG/usr/lib/linwas/linwas-power-agent"
install -D -m 0644 "$ROOT/packaging/systemd/linwas-power.service" \
    "$PKG/usr/lib/systemd/system/linwas-power.service"
install -D -m 0644 "$ROOT/packaging/linwas-power-agent.desktop" \
    "$PKG/etc/xdg/autostart/linwas-power-agent.desktop"

# APT deposu (yayın yeri kararlaştırılınca): LINWAS_APT_URL ve imza anahtarı verilirse
APT_URL=${LINWAS_APT_URL:-}
if [ -n "$APT_URL" ]; then
    if [ ! -f "$ROOT/packaging/linwas-archive-keyring.gpg" ]; then
        echo "HATA: LINWAS_APT_URL verildi ama packaging/linwas-archive-keyring.gpg yok." >&2
        exit 1
    fi
    install -D -m 0644 "$ROOT/packaging/linwas-archive-keyring.gpg" \
        "$PKG/usr/share/keyrings/linwas-archive-keyring.gpg"
fi

echo "==> Paket bilgileri"
INSTALLED_SIZE=$(du -sk --exclude=DEBIAN "$PKG" | cut -f1)
mkdir -p "$PKG/DEBIAN"
sed -e "s/@VERSION@/${VERSION}/" -e "s/@ARCH@/${ARCH}/" -e "s/@INSTALLED_SIZE@/${INSTALLED_SIZE}/" \
    "$ROOT/packaging/debian/control.in" > "$PKG/DEBIAN/control"
sed -e "s|@APT_URL@|${APT_URL}|" "$ROOT/packaging/debian/postinst.in" > "$PKG/DEBIAN/postinst"
install -m 0755 "$ROOT/packaging/debian/postrm" "$PKG/DEBIAN/postrm"
# /etc altındaki dosyalar kullanıcı değiştirirse güncellemede korunur
echo "/etc/xdg/autostart/linwas-power-agent.desktop" > "$PKG/DEBIAN/conffiles"
install -m 0755 "$ROOT/packaging/debian/prerm" "$PKG/DEBIAN/prerm"
chmod 0755 "$PKG/DEBIAN/postinst"

# İzinler: klasörler 755, dosyalar 644; çalıştırılabilir dosyalar korunur, kimse dışarıdan yazamaz.
chmod -R u+rwX,go+rX,go-w "$PKG"

OUT="$BUILD/linwas_${VERSION}_${ARCH}.deb"
# xz sıkıştırma: Debian 11 / Ubuntu 20.04'ün dpkg'si zstd ile sıkıştırılmış paketleri açamaz.
dpkg-deb --root-owner-group -Zxz --build "$PKG" "$OUT"
echo "==> Hazır: $OUT ($(du -h "$OUT" | cut -f1))"
