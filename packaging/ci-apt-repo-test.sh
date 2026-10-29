#!/bin/bash
# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
# CI APT deposu testi (kapsayıcıda, root olarak): geçici bir anahtarla imzalı yerel depo kurar,
# depo bilgisiyle yeniden paketlenmiş Linwas'ı kurar ve şunları denetler:
#   postinst depo kaynağını ekler → apt imzayı kabul eder → güncelleme depodan gelir →
#   purge kaynağı siler.
# Gerçek imza anahtarı ve depo adresi burada kullanılmaz.
set -u

HERE=$(cd "$(dirname "$0")" && pwd)
LOG=/tmp/linwas-apt-test.log
: > "$LOG"
export DEBIAN_FRONTEND=noninteractive
REPO_DIR=/srv/linwas-apt
APT_URL="file://$REPO_DIR"
WORK=$(mktemp -d)
export GNUPGHOME="$WORK/gnupg"

run() {
    echo "+ $*" >> "$LOG"
    "$@" >> "$LOG" 2>&1
}

fail() {
    echo "HATA: $1" >> "$LOG"
    local body
    body=$(tail -n 45 "$LOG" | sed -e 's/%/%25/g' -e 's/\r//g' | awk '{printf "%s%%0A", $0}')
    echo "::error title=APT deposu testi: $1::${body}"
    cat "$LOG"
    exit 1
}

# Paketin içini açar, depo adresini ve açık anahtarı ekler, verilen sürümle yeniden paketler.
repack() {
    local version=$1 out=$2
    local dir="$WORK/pkg-$version"
    dpkg-deb -R "$SRC_DEB" "$dir" || return 1
    install -D -m 0644 "$WORK/keyring.gpg" "$dir/usr/share/keyrings/linwas-archive-keyring.gpg"
    sed -e "s|@APT_URL@|${APT_URL}|" "$HERE/debian/postinst.in" > "$dir/DEBIAN/postinst"
    chmod 0755 "$dir/DEBIAN/postinst"
    sed -i "s/^Version: .*/Version: ${version}/" "$dir/DEBIAN/control"
    # Hız için hafif sıkıştırma; içerik testi için yeterli.
    dpkg-deb --root-owner-group -Zgzip -z1 --build "$dir" "$out"
}

SRC_DEB=$(ls ./linwas_*.deb | head -n 1)
BASE_VERSION=$(dpkg-deb --field "$SRC_DEB" Version)
NEW_VERSION="${BASE_VERSION}+apttest"

run apt-get update || fail "apt-get update"
run apt-get install -y --no-install-recommends gnupg apt-utils xz-utils || fail "araçlar kurulamadı"

mkdir -m 700 "$GNUPGHOME"
run gpg --batch --passphrase '' --quick-gen-key "Linwas CI Test Key" ed25519 sign 1d \
    || fail "geçici anahtar üretilemedi"
FPR=$(gpg --batch --with-colons --list-secret-keys | awk -F: '/^fpr/ {print $10; exit}')
gpg --batch --export "$FPR" > "$WORK/keyring.gpg"

run repack "$BASE_VERSION" "$WORK/old.deb" || fail "eski sürüm paketlenemedi"
run repack "$NEW_VERSION" "$WORK/new.deb" || fail "yeni sürüm paketlenemedi"
run bash "$HERE/build-apt-repo.sh" "$FPR" "$REPO_DIR" "$WORK/new.deb" || fail "depo kurulamadı"
# apt dosyaları _apt kullanıcısıyla okur.
chmod -R a+rX "$REPO_DIR"

run apt-get install -y "$WORK/old.deb" || fail "paket kurulamadı"
SOURCES=/etc/apt/sources.list.d/linwas.sources
[ -f "$SOURCES" ] || fail "postinst depo kaynağını eklemedi"
run cat "$SOURCES"

# İmza doğrulanamazsa apt-get update hata verir; yine de uyarıları da hata say.
run apt-get update || fail "apt-get update (imzalı depo)"
if grep -Eqi "NO_PUBKEY|not signed|is not valid|Bad signature" "$LOG"; then
    fail "depo imzası kabul edilmedi"
fi
run apt-get install -y --only-upgrade linwas || fail "depodan güncelleme"
INSTALLED=$(dpkg-query -W -f='${Version}' linwas)
[ "$INSTALLED" = "$NEW_VERSION" ] || fail "güncelleme depodan gelmedi (kurulu: $INSTALLED)"

# Kullanıcı kaynağı devre dışı bıraktıysa güncellemede yeniden eklenmemeli.
mv "$SOURCES" "$SOURCES.disabled"
run /var/lib/dpkg/info/linwas.postinst configure || fail "postinst yeniden çalıştırılamadı"
[ ! -e "$SOURCES" ] || fail "devre dışı bırakılan kaynak yeniden eklendi"
mv "$SOURCES.disabled" "$SOURCES"

run apt-get purge -y linwas || fail "paket kaldırılamadı"
[ ! -e "$SOURCES" ] || fail "purge depo kaynağını silmedi"

echo "APT deposu testi başarılı ($INSTALLED)" >> "$LOG"
cat "$LOG"
