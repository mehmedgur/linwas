#!/bin/sh
# Çeviri kaynaklarını (.ts) derlenmiş dosyalara (.qm) çevirir.
# Kullanım: scripts/compile-translations.sh [python-yorumlayıcısı]
# lrelease aracını sırayla şuralarda arar: pyside6-lrelease, PySide6 paket klasörü, sistem.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON=${1:-python3}
I18N="$ROOT/linwas/i18n"

find_lrelease() {
    if command -v pyside6-lrelease >/dev/null 2>&1; then
        command -v pyside6-lrelease
        return 0
    fi
    pyside_dir=$("$PYTHON" -c 'import os, PySide6; print(os.path.dirname(PySide6.__file__))' \
        2>/dev/null || true)
    if [ -n "$pyside_dir" ]; then
        for candidate in "$pyside_dir/lrelease" "$pyside_dir/Qt/libexec/lrelease"; do
            if [ -x "$candidate" ]; then
                echo "$candidate"
                return 0
            fi
        done
    fi
    for candidate in lrelease-qt6 /usr/lib/qt6/bin/lrelease lrelease; do
        if command -v "$candidate" >/dev/null 2>&1; then
            command -v "$candidate"
            return 0
        fi
    done
    return 1
}

LRELEASE=$(find_lrelease) || {
    echo "HATA: lrelease bulunamadı. 'pip install PySide6' ile tam PySide6 paketini kurun." >&2
    exit 1
}

for ts in "$I18N"/*.ts; do
    "$LRELEASE" "$ts" -qm "${ts%.ts}.qm"
done
echo "Çeviriler derlendi ($LRELEASE)."
