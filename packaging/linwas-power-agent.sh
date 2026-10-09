#!/bin/sh
# Linwas güç planlarının masaüstü tarafı (oturum açılınca XDG autostart ile başlar).
exec /opt/linwas/runtime/bin/python3 -I -m linwas.core.power_agent
