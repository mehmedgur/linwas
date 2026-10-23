#!/bin/sh
# Etkin güç planını değiştirir: pkexec bu dosyayı root olarak çalıştırır
# (polkit eylemi: org.linwas.power.switch; etkin oturumda şifre sorulmaz).
# Tek parametre: plan kimliği; /etc/linwas/power.json'daki planlarla doğrulanır.
[ "$#" -eq 1 ] || exit 2
exec /opt/linwas/runtime/bin/python3 -I -m linwas.core.power_apply --switch "$1"
