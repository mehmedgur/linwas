# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Donanım bilgisi eklentisi (yerleşik).

Okuma işlevleri `probe` modülünde (Qt'siz); bileşen kartları ve ayrıntı pencereleri `widgets`
modülünde (yalnızca arayüz katmanı içe aktarır). Donanım ve yazıcılar sayfası, sistem raporu ve
AI bağlamı bilgiyi bu eklentiden okur (kararlar.md › Donanım ve yazıcılar yenilemesi).
"""

from __future__ import annotations

from typing import Any

from linwas.core.plugins import PluginBase, PluginMeta

PLUGIN_ID = "linwas.hardware_info"


class HardwareInfoPlugin(PluginBase):
    """Sayfası yok; bilgi ve arayüz parçaları sağlar."""

    required = True  # Donanım sayfası, sistem raporu ve AI bağlamı buna dayanıyor

    @property
    def meta(self) -> PluginMeta:
        from linwas import __version__

        return PluginMeta(id=PLUGIN_ID, name="Hardware information", version=__version__)

    def ai_context(self) -> dict[str, Any]:
        from linwas.plugins.hardware_info import probe

        try:
            return {"hardware": probe.summary_dict()}
        except Exception:  # okuma hatası AI'ı durdurmasın
            return {}
