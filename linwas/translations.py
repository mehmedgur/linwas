"""Çeviri yükleme.

Arayüz metinleri kodda İngilizce yazılır; Türkçe karşılıkları `linwas/i18n/linwas_tr.ts`
dosyasındadır ve derlenmiş `.qm` dosyası çalışma anında yüklenir. Varsayılan dil Türkçe'dir;
`LINWAS_LANG=en` ile İngilizce açılır (ileride Ayarlar sayfasından seçilecek).
"""

from __future__ import annotations

import os
from pathlib import Path

I18N_DIR = Path(__file__).resolve().parent / "i18n"
DEFAULT_LANGUAGE = "tr"
SUPPORTED_LANGUAGES = ("tr", "en")


def selected_language(env: dict[str, str] | None = None) -> str:
    """Kullanılacak dili döndürür ('tr' ya da 'en')."""
    env = dict(os.environ) if env is None else env
    lang = env.get("LINWAS_LANG", DEFAULT_LANGUAGE).strip().lower()
    return lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def qm_path(lang: str) -> Path:
    """Dilin derlenmiş çeviri dosyasının yolu."""
    return I18N_DIR / f"linwas_{lang}.qm"


def install_translator(app, lang: str):  # noqa: ANN001 - Qt türleri burada içe aktarılmaz
    """Uygulamaya çeviriyi yükler. Başarılıysa QTranslator nesnesini, değilse None döner.

    İngilizce kaynak dil olduğu için 'en' seçiliyse çeviri yüklenmez.
    """
    if lang == "en":
        return None
    from PySide6.QtCore import QTranslator

    translator = QTranslator(app)
    if translator.load(str(qm_path(lang))):
        app.installTranslator(translator)
        return translator
    return None
