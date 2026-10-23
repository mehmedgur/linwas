"""Uygulama giriş noktası.

Komut satırı seçenekleri:
  --version      Sürümü yazdırır.
  --self-check   Pencere açmadan temel kontrolleri yapar (CI'da paket testi için).
  --edition=eco  Eco sürümü teması (varsayılan: linwas; LINWAS_EDITION ortam değişkeni de olur).
"""

from __future__ import annotations

import os
import sys

from linwas import __version__


def _edition(argv: list[str]) -> str:
    """Sürümü komut satırından ya da ortamdan okur; bilinmeyen değerde 'linwas'."""
    value = os.environ.get("LINWAS_EDITION", "")
    for arg in argv[1:]:
        if arg.startswith("--edition="):
            value = arg.split("=", 1)[1]
    return value if value in ("linwas", "eco") else "linwas"


def _self_check(argv: list[str]) -> int:
    """PySide6 yükleniyor mu, çeviri bulunuyor mu, pencere oluşturulabiliyor mu?"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import __version__ as pyside_version
    from PySide6.QtWidgets import QApplication

    from linwas.translations import install_translator, qm_path, selected_language
    from linwas.ui.main_window import MainWindow
    from linwas.ui.theme.manager import ThemeManager

    app = QApplication([sys.argv[0]])
    lang = selected_language()
    translator = install_translator(app, lang)
    themes = ThemeManager(app, _edition(argv))
    themes.apply()
    window = MainWindow()
    window.show()
    app.processEvents()

    print(f"linwas {__version__}")
    print(f"python {sys.version.split()[0]}")
    print(f"pyside6 {pyside_version}")
    print(f"theme {themes.edition}/{themes.mode}")
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
        return _self_check(argv)

    from PySide6.QtWidgets import QApplication

    from linwas.translations import install_translator, selected_language
    from linwas.ui.main_window import MainWindow
    from linwas.ui.theme.manager import ThemeManager

    app = QApplication(argv)
    app.setApplicationName("Linwas")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("linwas")
    install_translator(app, selected_language())
    ThemeManager(app, _edition(argv)).apply()

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
