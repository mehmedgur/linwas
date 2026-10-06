#!/bin/sh
# Linwas root helper: pkexec bu dosyayı root olarak çalıştırır
# (polkit eylemi: org.linwas.helper.run, bkz. org.linwas.helper.policy).
# Yalnızca izin listesindeki işlemleri JSON satırlarıyla kabul eder.
exec /opt/linwas/runtime/bin/python3 -I -m linwas.core.helper
