#!/bin/sh
# Linwas'ı kaynak koddan çalıştırır. Önce scripts/dev-setup.sh bir kez çalıştırılmalı.
# Çevirileri her çalıştırmada yeniden derler; böylece .ts değişiklikleri hemen görünür.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

if [ ! -x .venv/bin/python ]; then
    echo "Önce kurulum gerekli: ./scripts/dev-setup.sh" >&2
    exit 1
fi

PATH="$ROOT/.venv/bin:$PATH" sh scripts/compile-translations.sh .venv/bin/python >/dev/null
exec .venv/bin/python -m linwas "$@"
