#!/bin/sh
# Geliştirici kurulumu (bir kerelik). Son kullanıcılar için DEĞİLDİR; onlar .deb paketini kullanır.
# Depo klasöründe .venv sanal ortamı oluşturur, PySide6 ve geliştirme araçlarını kurar,
# çevirileri derler.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

if ! command -v python3 >/dev/null 2>&1; then
    echo "HATA: python3 bulunamadı." >&2
    exit 1
fi

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "HATA: Python 3.10 veya daha yenisi gerekli. Bulunan: $(python3 --version)" >&2
    exit 1
fi

if [ ! -d .venv ]; then
    if ! python3 -m venv .venv 2>/dev/null; then
        echo "HATA: Sanal ortam oluşturulamadı." >&2
        echo "Debian/Ubuntu/Pardus'ta önce şunu çalıştırın: sudo apt install python3-venv" >&2
        rm -rf .venv
        exit 1
    fi
fi

.venv/bin/python -m pip install --upgrade pip
# Geliştiricide tam PySide6 (lrelease gibi araçlar için) + Linwas düzenlenebilir kurulum.
.venv/bin/python -m pip install "PySide6>=6.8,<7"
.venv/bin/python -m pip install -e ".[dev]"

PATH="$ROOT/.venv/bin:$PATH" sh scripts/compile-translations.sh .venv/bin/python

echo
echo "Kurulum tamam. Çalıştırmak için: ./scripts/run-dev.sh"
