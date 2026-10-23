#!/bin/bash
# linwas-office-look .deb paketini derler.
# Kullanım: packaging/plugins/office-look/build-deb.sh [paket-sürümü] [çıktı-klasörü]
#   Sürüm verilmezse VERSION dosyasındaki kullanılır. ör. build-deb.sh "" build
# Gereken: python3, dpkg-deb, fakeroot. LibreOffice (writer, calc, impress) kuruluysa paket
# ağacı ve bu makinede üretilen sade şerit denetlenir; değilse denetim atlanır (CI'da kurulu).
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
VERSION=${1:-$(cat "$HERE/VERSION")}
OUT=${2:-$HERE/../../../build}
PKG=$(mktemp -d)
trap 'rm -rf "$PKG"' EXIT
chmod 755 "$PKG"

LO_SHARE=usr/lib/libreoffice/share
install -d "$PKG/DEBIAN" "$PKG/usr/bin" "$PKG/usr/share/linwas-office-look" \
    "$PKG/usr/share/applications" "$PKG/usr/share/doc/linwas-office-look" \
    "$PKG/$LO_SHARE/registry" "$PKG/$LO_SHARE/extensions/linwas-office-look"

cp -a "$HERE/extension/." "$PKG/$LO_SHARE/extensions/linwas-office-look/"
find "$PKG/$LO_SHARE/extensions" -name __pycache__ -prune -exec rm -rf {} +
install -m 644 "$HERE/registry/linwas-office-look.xcd" "$PKG/$LO_SHARE/registry/"
install -m 644 "$HERE/tools/cli.py" "$HERE/tools/ribbon.py" "$HERE/tools/lo_profile.py" \
    "$HERE/tools/office_names.py" \
    "$PKG/usr/share/linwas-office-look/"
install -m 755 "$HERE/linwas-office-look" "$PKG/usr/bin/"
install -m 644 "$HERE/linwas-office-look.desktop" "$PKG/usr/share/applications/"
install -m 755 "$HERE/debian/postinst" "$HERE/debian/prerm" "$PKG/DEBIAN/"
install -m 644 "$HERE/debian/triggers" "$PKG/DEBIAN/"
cat > "$PKG/usr/share/doc/linwas-office-look/copyright" <<'COPY'
linwas-office-look — Linwas projesinin parçası.
Kurulumda üretilen linwas_simple.ui dosyaları LibreOffice'in notebookbar.ui dosyalarından
türetilir (Mozilla Public License 2.0, /usr/share/common-licenses/MPL-2.0).
COPY

if [ -f /usr/lib/libreoffice/share/registry/main.xcd ]; then
    python3 -I "$HERE/tools/check.py" "$PKG"
else
    echo "UYARI: LibreOffice kurulu değil, paket denetimi atlandı." >&2
fi

SIZE=$(du -sk --exclude=DEBIAN "$PKG" | cut -f1)
sed -e "s/@VERSION@/$VERSION/" -e "s/@INSTALLED_SIZE@/$SIZE/" "$HERE/debian/control.in" \
    > "$PKG/DEBIAN/control"
mkdir -p "$OUT"
fakeroot dpkg-deb --build -Zxz "$PKG" "$OUT/linwas-office-look_${VERSION}_all.deb" >/dev/null
echo "$OUT/linwas-office-look_${VERSION}_all.deb"
