#!/bin/bash
# Linwas eklenti kataloğunu üretir ve APT deposuyla aynı Linwas anahtarıyla imzalar.
# Kullanım: packaging/build-plugin-catalog.sh <imza-anahtarı-kimliği> <çıktı-klasörü>
#   ör. packaging/build-plugin-catalog.sh 0123ABCD... build/apt-repo/plugins
# Kaynak: packaging/plugin-catalog/ (plugins/*.json, revoked.json). Anahtar GNUPGHOME'dan alınır.
# Çıktı APT deposunun "plugins/" klasörüne konur; Linwas adresi <LINWAS_APT_URL>/plugins/index.json.
set -euo pipefail

KEY=${1:?Kullanım: packaging/build-plugin-catalog.sh <anahtar-kimliği> <çıktı-klasörü>}
OUT=${2:?Çıktı klasörü verilmedi}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON=${PYTHON:-python3}

for cmd in gpg gpgv "$PYTHON"; do
    command -v "$cmd" >/dev/null || { echo "HATA: '$cmd' bulunamadı." >&2; exit 1; }
done
gpg --batch --list-secret-keys "$KEY" >/dev/null 2>&1 \
    || { echo "HATA: '$KEY' gizli anahtarı GNUPGHOME'da yok." >&2; exit 1; }

rm -rf "$OUT"
mkdir -p "$OUT"
"$PYTHON" "$ROOT/packaging/build_plugin_catalog.py" "$ROOT/packaging/plugin-catalog" "$OUT"

# Ayrık ikili imza: Linwas `gpgv --keyring <anahtar> index.json.sig index.json` ile doğrular
gpg --batch --yes --local-user "$KEY" --detach-sign -o "$OUT/index.json.sig" "$OUT/index.json"

RING=$(mktemp)
trap 'rm -f "$RING"' EXIT
gpg --batch --yes --export "$KEY" > "$RING"
gpgv --keyring "$RING" "$OUT/index.json.sig" "$OUT/index.json" 2>/dev/null \
    || { echo "HATA: imza doğrulanamadı." >&2; exit 1; }
echo "Katalog hazır ve imzalı: $OUT"
