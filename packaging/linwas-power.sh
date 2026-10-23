#!/bin/sh
# Linwas güç planları servisi: linwas-power.service bu dosyayı root olarak çalıştırır.
# Parametre almaz; yalnızca /etc/linwas/power.json ayarını okur.
exec /opt/linwas/runtime/bin/python3 -I -m linwas.core.power_apply
