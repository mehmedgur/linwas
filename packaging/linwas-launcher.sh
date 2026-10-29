#!/bin/sh
# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
# Linwas başlatıcısı: pakete gömülü Python ile çalışır.
# -I (izole mod): kullanıcının Python ayarları ve paketleri Linwas'ı etkilemez.
exec /opt/linwas/runtime/bin/python3 -I -m linwas "$@"
