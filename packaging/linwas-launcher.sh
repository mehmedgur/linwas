#!/bin/sh
# Linwas başlatıcısı: pakete gömülü Python ile çalışır.
# -I (izole mod): kullanıcının Python ayarları ve paketleri Linwas'ı etkilemez.
exec /opt/linwas/runtime/bin/python3 -I -m linwas "$@"
