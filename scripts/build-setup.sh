#!/bin/sh
# Tek dosyalık kurulum betiği (linwas-setup.run) üretir: içinde .deb paketi gömülüdür.
# Hedef makinede: chmod +x linwas-setup.run && ./linwas-setup.run
# Önce scripts/build-local-deb.sh ile paketi derler, sonra betiğin sonuna ekler; masaüstüne kopyalar.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

sh scripts/build-local-deb.sh
DEB=$(ls -t build/linwas_*_amd64.deb | head -n 1)
OUT="$ROOT/build/linwas-setup.run"

# Kurulum betiğinin başlığı; gömülü paket __PAYLOAD__ satırından sonra başlar.
cat >"$OUT" <<'HEADER'
#!/bin/sh
# Linwas kurulumu: gömülü .deb paketini çıkarır ve apt ile kurar (bağımlılıkları apt çözer).
set -eu

if ! command -v apt-get >/dev/null 2>&1; then
    echo "HATA: Bu kurulum yalnızca Debian/Ubuntu/Pardus tabanlı sistemler içindir." >&2
    exit 1
fi
if [ "$(dpkg --print-architecture)" != "amd64" ]; then
    echo "HATA: Yalnızca 64 bit (amd64) sistemler desteklenir." >&2
    exit 1
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
LINE=$(awk '/^__PAYLOAD__$/ { print NR + 1; exit }' "$0")
tail -n +"$LINE" "$0" >"$TMP/linwas.deb"
# apt paketi _apt kullanıcısıyla okur; okunabilir olmazsa uyarı verir.
chmod 755 "$TMP"
chmod 644 "$TMP/linwas.deb"

echo "Linwas kuruluyor (yönetici parolası istenecek)..."
if [ "$(id -u)" -eq 0 ]; then
    apt-get install -y "$TMP/linwas.deb"
else
    sudo apt-get install -y "$TMP/linwas.deb"
fi
echo
echo "Kurulum tamam. Uygulamalar menüsünden 'Linwas'ı açabilirsiniz."
exit 0
__PAYLOAD__
HEADER
cat "$DEB" >>"$OUT"
chmod +x "$OUT"

DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
if [ -d "$DESKTOP_DIR" ]; then
    cp "$OUT" "$DESKTOP_DIR/linwas-setup.run"
    echo "Masaüstüne kopyalandı: $DESKTOP_DIR/linwas-setup.run"
fi
echo "Hedef makinede: chmod +x linwas-setup.run && ./linwas-setup.run"
