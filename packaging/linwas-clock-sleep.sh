#!/bin/sh
# Linwas: uykudan / hazırda beklemeden uyanınca saati düzelt (systemd-suspend.service bu klasördeki
# programları "pre|post <eylem>" ile çalıştırır). Windows ile çift açılışta anakart saati (RTC) yerel
# saattedir; çekirdek uyanınca onu UTC sanar ve saat, saat dilimi farkı kadar kayar. Burada RTC doğru
# ölçekle yeniden okunur (internet yokken de düzelir), ardından chrony ağdan eşitler.
[ "$1" = "post" ] || exit 0
PATH=/usr/sbin:/usr/bin:/sbin:/bin
if [ "$(timedatectl show -p LocalRTC --value 2>/dev/null)" = "yes" ]; then
    hwclock --hctosys --localtime >/dev/null 2>&1 || true
fi
if command -v chronyc >/dev/null 2>&1; then
    chronyc -a makestep >/dev/null 2>&1 || true
fi
exit 0
