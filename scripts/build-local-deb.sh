#!/bin/sh
# Geliştiricinin kendi makinesinde .deb paketi derler (CI'yı beklemeden başka bir makinede denemek için).
# Çevirileri derler, packaging/build-deb.sh'ı çalıştırır, paketi masaüstüne linwasnew.deb adıyla kopyalar.
# Sürüm: 2.0.0~local<tarih-saat> (her derleme bir öncekinden yeni sayılır, apt güncelleme olarak kurar).
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

if [ ! -x .venv/bin/python ]; then
    echo "Önce kurulum gerekli: ./scripts/dev-setup.sh" >&2
    exit 1
fi

VERSION="2.0.0~local$(date +%Y%m%d%H%M)"

PATH="$ROOT/.venv/bin:$PATH" sh scripts/compile-translations.sh .venv/bin/python >/dev/null
bash packaging/build-deb.sh "$VERSION"

DEB="$ROOT/build/linwas_${VERSION}_amd64.deb"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
if [ -d "$DESKTOP_DIR" ]; then
    cp "$DEB" "$DESKTOP_DIR/linwasnew.deb"
    echo "Masaüstüne kopyalandı: $DESKTOP_DIR/linwasnew.deb"
fi
echo "Kurulum (hedef makinede): sudo apt install ./linwasnew.deb"
