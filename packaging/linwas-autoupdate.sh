#!/bin/sh
# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
# Linwas otomatik güncelleme: linwas-autoupdate.service bu dosyayı root olarak çalıştırır.
# Parametre almaz; yalnızca /etc/linwas/autoupdate.json ayarını okur.
exec /opt/linwas/runtime/bin/python3 -I -m linwas.core.autoupdate
