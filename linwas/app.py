"""Uygulama giriş noktası.

Komut satırı seçenekleri:
  --version      Sürümü yazdırır.
  --self-check   Pencere açmadan temel kontrolleri yapar (CI'da paket testi için).
"""

from __future__ import annotations

import os
import sys

from linwas import __version__


def _self_check() -> int:
    """PySide6 yükleniyor mu, çeviri bulunuyor mu, pencere oluşturulabiliyor mu?"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import __version__ as pyside_version
    from PySide6.QtWidgets import QApplication

    from linwas.translations import install_translator, qm_path, selected_language
    from linwas.ui.main_window import MainWindow

    app = QApplication([sys.argv[0]])
    lang = selected_language()
    translator = install_translator(app, lang)
    window = MainWindow()
    window.show()
    app.processEvents()

    print(f"linwas {__version__}")
    print(f"python {sys.version.split()[0]}")
    print(f"pyside6 {pyside_version}")
    print(f"language {lang}: {'loaded' if translator or lang == 'en' else 'MISSING'}")
    print(f"window title: {window.windowTitle()}")
    ok = lang == "en" or translator is not None
    if not ok:
        print(f"translation file not found: {qm_path(lang)}", file=sys.stderr)
    window.close()
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--version" in argv[1:]:
        print(__version__)
        return 0
    if "--self-check" in argv[1:]:
        return _self_check()

    from PySide6.QtWidgets import QApplication

    from linwas.translations import install_translator, selected_language
    from linwas.ui.main_window import MainWindow

    app = QApplication(argv)
    app.setApplicationName("Linwas")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("linwas")
    # LINWAS_LANG ortam değişkeni (geliştirme/test) ayarlardaki dili ezer
    from linwas.core import app_settings

    lang = selected_language() if "LINWAS_LANG" in os.environ else app_settings.load().language
    install_translator(app, lang)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
