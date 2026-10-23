#!/usr/bin/env bash
# docs/tasarim/ altındaki token dosyalarını paketin içine kopyalar (tek doğru kaynak: docs).
# tokens.json ya da tokens-eco.json değişince çalıştır; tests/test_theme.py farkı yakalar.
set -euo pipefail
cd "$(dirname "$0")/.."
cp docs/tasarim/tokens.json docs/tasarim/tokens-eco.json linwas/resources/tokens/
echo "Token dosyaları linwas/resources/tokens/ altına kopyalandı."
