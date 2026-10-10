"""Uygulama giriş noktası.

Komut satırı seçenekleri:
  --version      Sürümü yazdırır.
  --self-check   Pencere açmadan temel kontrolleri yapar (CI'da paket testi için).
  --app-folder KİMLİK [DOSYALAR]  Program klasörünü açar; bırakılan kısayolları ekler.
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
    if len(argv) > 2 and argv[1] == "--app-folder":
        # Program klasörü açılır penceresi; ana pencereden bağımsız, hafif süreç
        from linwas.ui.app_folder_popup import run

        return run(argv[2], argv[3:])

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
    from linwas.core import logging_setup

    logging_setup.setup(app_settings.load().debug_log)

    # "Linwas ile aç": .deb ya da .exe/.msi verildiyse risk analizi penceresi açılır
    deb = next((a for a in argv[1:] if a.endswith(".deb") and os.path.isfile(a)), None)
    exe = next(
        (a for a in argv[1:] if a.lower().endswith((".exe", ".msi")) and os.path.isfile(a)),
        None,
    )
    background = "--background" in argv[1:]
    if deb:
        message = "deb:" + os.path.abspath(deb)
    elif exe:
        message = "exe:" + os.path.abspath(exe)
    else:
        message = "background" if background else "show"

    # Tek kopya: Linwas zaten çalışıyorsa (ör. arka planda) iletiyi ona gönderip çık
    from linwas.ui.single_instance import SingleInstance

    instance = SingleInstance()
    if instance.send_to_running(message):
        return 0
    instance.listen()

    window = MainWindow(background=background and not (deb or exe))
    instance.message_received.connect(window.on_instance_message)
    if not window.is_background:
        window.show()
    if deb:
        window.open_deb(os.path.abspath(deb))
    if exe:
        window.open_exe(os.path.abspath(exe))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
