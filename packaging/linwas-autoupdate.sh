#!/bin/sh
# Linwas otomatik güncelleme: linwas-autoupdate.service bu dosyayı root olarak çalıştırır.
# Parametre almaz; yalnızca /etc/linwas/autoupdate.json ayarını okur.
exec /opt/linwas/runtime/bin/python3 -I -m linwas.core.autoupdate
