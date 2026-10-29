#!/bin/bash
# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
# Linwas APT deposunu .deb dosyalarından kurar ve imzalar.
# Kullanım: packaging/build-apt-repo.sh <imza-anahtarı-kimliği> <depo-klasörü> <paket.deb>...
#   ör. packaging/build-apt-repo.sh 0123ABCD... build/apt-repo build/linwas_2.0.0_amd64.deb
# Gereken: apt-ftparchive (apt-utils paketi), gpg. Anahtar GNUPGHOME'daki anahtarlıktan alınır.
# Depo klasörü önceki yayının kopyasıysa eski paketler korunur (pool/), indeksler yeniden üretilir.
#
# Oluşan yapı (postinst'teki deb822 kaynağıyla eşleşir: Suites: stable, Components: main):
#   pool/main/l/<paket>/*.deb
#   dists/stable/main/binary-amd64/Packages{,.gz,.xz}
#   dists/stable/{Release,InRelease,Release.gpg}
#   linwas-archive-keyring.gpg   (açık anahtar; elle kurulum için)
set -euo pipefail

KEY=${1:?Kullanım: packaging/build-apt-repo.sh <anahtar-kimliği> <depo-klasörü> <paket.deb>...}
REPO=${2:?Depo klasörü verilmedi}
shift 2
[ "$#" -gt 0 ] || { echo "HATA: En az bir .deb dosyası verin." >&2; exit 1; }

SUITE=stable
COMPONENT=main
ARCH=amd64

for cmd in apt-ftparchive gpg dpkg-deb; do
    command -v "$cmd" >/dev/null || { echo "HATA: '$cmd' bulunamadı (apt-utils, gnupg)." >&2; exit 1; }
done
# Anahtar gizli anahtarlıkta yoksa imzalama sonda başarısız olur; baştan denetle.
gpg --batch --list-secret-keys "$KEY" >/dev/null 2>&1 \
    || { echo "HATA: '$KEY' gizli anahtarı GNUPGHOME'da yok." >&2; exit 1; }

mkdir -p "$REPO"
REPO=$(cd "$REPO" && pwd)

echo "==> Paketler havuza kopyalanıyor"
for deb in "$@"; do
    name=$(dpkg-deb --field "$deb" Package)
    dest="$REPO/pool/$COMPONENT/${name:0:1}/$name"
    mkdir -p "$dest"
    install -m 0644 "$deb" "$dest/"
done

echo "==> Paket indeksleri"
BIN="dists/$SUITE/$COMPONENT/binary-$ARCH"
mkdir -p "$REPO/$BIN"
# Yollar depo köküne göre yazılmalı (Filename: pool/...), bu yüzden kökte çalıştırılır.
(cd "$REPO" && apt-ftparchive packages "pool/$COMPONENT") > "$REPO/$BIN/Packages"
gzip -9nkf "$REPO/$BIN/Packages"
xz -9kf "$REPO/$BIN/Packages"

echo "==> Release ve imzalar"
DIST="$REPO/dists/$SUITE"
rm -f "$DIST/Release" "$DIST/InRelease" "$DIST/Release.gpg"
# Release dosyası kendi klasörünü taradığı için önce geçici dosyaya yazılır.
(cd "$DIST" && apt-ftparchive \
    -o APT::FTPArchive::Release::Origin=Linwas \
    -o APT::FTPArchive::Release::Label=Linwas \
    -o APT::FTPArchive::Release::Suite="$SUITE" \
    -o APT::FTPArchive::Release::Codename="$SUITE" \
    -o APT::FTPArchive::Release::Architectures="$ARCH" \
    -o APT::FTPArchive::Release::Components="$COMPONENT" \
    -o APT::FTPArchive::Release::Description="Linwas packages" \
    release .) > "$REPO/Release.tmp"
mv "$REPO/Release.tmp" "$DIST/Release"

gpg --batch --yes --local-user "$KEY" --clearsign -o "$DIST/InRelease" "$DIST/Release"
gpg --batch --yes --local-user "$KEY" --armor --detach-sign -o "$DIST/Release.gpg" "$DIST/Release"
gpg --batch --yes --export "$KEY" > "$REPO/linwas-archive-keyring.gpg"

# Son denetim: imza, dışa aktarılan açık anahtarla doğrulanabilmeli (apt de gpgv kullanır).
gpgv --keyring "$REPO/linwas-archive-keyring.gpg" "$DIST/InRelease" 2>/dev/null \
    || { echo "HATA: InRelease imzası doğrulanamadı." >&2; exit 1; }

echo "==> Hazır: $REPO"
