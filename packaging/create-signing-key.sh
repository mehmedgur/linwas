#!/bin/bash
# Linwas APT deposu imza anahtarını bir kerelik üretir.
# Kullanım: packaging/create-signing-key.sh [anahtar-klasörü]   (varsayılan: ~/.linwas-signing)
# Sistemi değiştirmez; anahtar kişisel anahtarlığınıza değil, ayrı bir klasöre yazılır.
#
# Çıktılar:
#   <klasör>/gnupg/                      anahtarlık (GNUPGHOME)
#   <klasör>/linwas-signing-key.asc      GİZLİ anahtar → GitHub gizli değeri LINWAS_SIGNING_KEY
#   packaging/linwas-archive-keyring.gpg açık anahtar → pakete girer (Signed-By)
# Gizli anahtarın bir yedeğini çevrim dışı (ör. USB bellek) saklayın; kaybolursa kullanıcılara
# yeni anahtar dağıtmak gerekir.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DIR=${1:-$HOME/.linwas-signing}
export GNUPGHOME="$DIR/gnupg"
UID_NAME="Linwas Archive Signing Key"
# Süre dolmadan önce uzatılıp yeni açık anahtar bir Linwas güncellemesiyle dağıtılmalı.
EXPIRE=5y

if [ -d "$GNUPGHOME" ] && gpg --batch --list-secret-keys "$UID_NAME" >/dev/null 2>&1; then
    echo "HATA: $GNUPGHOME içinde zaten bir Linwas anahtarı var; üzerine yazılmadı." >&2
    exit 1
fi
mkdir -p "$GNUPGHOME"
chmod 700 "$DIR" "$GNUPGHOME"

# Parolasız: anahtar CI'da (GitHub Actions) etkileşimsiz imza atacak.
gpg --batch --passphrase '' --quick-gen-key "$UID_NAME" ed25519 sign "$EXPIRE"
FPR=$(gpg --batch --with-colons --list-secret-keys "$UID_NAME" | awk -F: '/^fpr/ {print $10; exit}')

(umask 077 && gpg --batch --armor --export-secret-keys "$FPR" > "$DIR/linwas-signing-key.asc")
gpg --batch --export "$FPR" > "$ROOT/packaging/linwas-archive-keyring.gpg"

cat <<MSG

Anahtar hazır. Parmak izi: $FPR
- Gizli anahtar: $DIR/linwas-signing-key.asc
  GitHub › Settings › Secrets and variables › Actions › New repository secret
  Ad: LINWAS_SIGNING_KEY, değer: dosyanın tüm içeriği.
- Açık anahtar: packaging/linwas-archive-keyring.gpg (depoya eklenebilir).
- Bu klasörün çevrim dışı bir yedeğini alın.
MSG
