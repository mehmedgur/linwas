# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""İlk açılış: kısa tanıtım + kurulum sihirbazı.

Adımlar: tanıtım → sistem taraması → Windows'tan taşıma → ilk tam yedek (Timeshift)
→ isteğe bağlı AI anahtarı. Seçilen işler sihirbaz bitince kuyruğa/sayfaya aktarılır.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from linwas.backend import touchpad, troubleshoot
from linwas.backend.backups import timeshift_available
from linwas.core.tasks import Task, TaskStep


def tr(text: str) -> str:
    return QCoreApplication.translate("OnboardingWizard", text)


class _ScanWorker(QThread):
    done = Signal(object)

    def run(self) -> None:
        try:
            self.done.emit(troubleshoot.run_all())
        except Exception:
            self.done.emit([])


def _page(title: str, text: str) -> tuple[QWizardPage, QVBoxLayout]:
    page = QWizardPage()
    page.setTitle(title)
    layout = QVBoxLayout(page)
    lbl = QLabel(text, page)
    lbl.setWordWrap(True)
    layout.addWidget(lbl)
    return page, layout


class OnboardingWizard(QWizard):
    """Bitince `tasks` (kuyruğa eklenecek) ve `open_page` (açılacak sayfa) okunur."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Welcome to Linwas"))
        self.setMinimumSize(560, 420)
        self.setButtonText(QWizard.WizardButton.NextButton, tr("Next"))
        self.setButtonText(QWizard.WizardButton.BackButton, tr("Back"))
        self.setButtonText(QWizard.WizardButton.FinishButton, tr("Finish"))
        self.setButtonText(QWizard.WizardButton.CancelButton, tr("Skip"))
        self.tasks: list[Task] = []
        self.open_page = ""
        self._scan: _ScanWorker | None = None

        # 1. Tanıtım
        page, _ = _page(
            tr("Welcome!"),
            tr(
                "Linwas helps you use Linux without the terminal.\n\n"
                "• System: updates, drivers, Wi-Fi, backups and more\n"
                "• Interface: make the desktop look like Windows\n"
                "• Software: install and remove programs\n"
                "• Troubleshooting: find and fix common problems\n"
                "• AI Question: ask anything (optional)\n\n"
                "Changes are collected in a queue at the bottom. Nothing runs until you "
                "press Apply and enter your password once."
            ),
        )
        self.addPage(page)

        # 2. Sistem taraması
        page, layout = _page(
            tr("Quick system check"),
            tr("Linwas checks your computer for common problems."),
        )
        self._scan_lbl = QLabel(tr("Checking…"), page)
        self._scan_lbl.setWordWrap(True)
        layout.addWidget(self._scan_lbl)
        self._scan_page = page
        self.addPage(page)

        # 3. Windows'tan taşıma
        page, layout = _page(
            tr("Coming from Windows?"),
            tr(
                "Linwas can bring your documents, bookmarks and settings from a Windows "
                "partition or an external disk."
            ),
        )
        self._migrate = QCheckBox(tr("Open “Transfer” after this"), page)
        layout.addWidget(self._migrate)
        # Dokunmatik yüzeyde Windows gibi sağ tık (GNOME varsayılanı iki parmak)
        self._corner_click = None
        if touchpad.should_offer():
            self._corner_click = QCheckBox(
                tr("Right-click by pressing the bottom-right corner of the touchpad, like Windows"),
                page,
            )
            self._corner_click.setChecked(True)
            layout.addWidget(self._corner_click)
            hint = QLabel(
                tr(
                    "Otherwise right-click needs a two-finger click. You can change this later "
                    "in Troubleshooting."
                ),
                page,
            )
            hint.setObjectName("Secondary")
            hint.setWordWrap(True)
            layout.addWidget(hint)
        self.addPage(page)

        # 4. İlk tam yedek
        has_ts = timeshift_available()
        page, layout = _page(
            tr("Full system backup"),
            tr(
                "A full backup (Timeshift snapshot) lets you return the whole system to "
                "today's state if something goes wrong. It can take a few minutes."
            )
            if has_ts
            else tr(
                "Timeshift makes full system backups so you can undo big changes. It is not "
                "installed yet."
            ),
        )
        self._backup = QCheckBox(
            tr("Take the first full backup") if has_ts else tr("Install Timeshift"), page
        )
        self._backup.setChecked(True)
        self._has_ts = has_ts
        layout.addWidget(self._backup)
        self.addPage(page)

        # 5. AI (isteğe bağlı)
        page, layout = _page(
            tr("AI assistant (optional)"),
            tr(
                "With a free Gemini key (or ChatGPT / DeepSeek) you can ask questions and get "
                "help with errors. You can also do this later in AI Question › AI settings."
            ),
        )
        ai_btn = QPushButton(tr("Add an API key now"), page)
        ai_btn.clicked.connect(self._open_ai_settings)
        layout.addWidget(ai_btn)
        layout.addStretch(1)
        self.addPage(page)

        self.currentIdChanged.connect(self._on_page)

    def _on_page(self, _id: int) -> None:
        if self.currentPage() is self._scan_page and self._scan is None:
            self._scan = _ScanWorker()
            self._scan.done.connect(self._on_scan)
            self._scan.start()

    def _on_scan(self, results: list) -> None:
        problems = [r for r in results if not r.ok]
        if not problems:
            self._scan_lbl.setText(tr("✓ No problems found."))
        else:
            self._scan_lbl.setText(
                tr("⚠ {n} problem(s) found. You'll find the fixes in Troubleshooting.").format(
                    n=len(problems)
                )
            )
            self.open_page = self.open_page or "troubleshoot"

    def _open_ai_settings(self) -> None:
        from linwas.ui.pages.settings_ai import AISettingsDialog

        AISettingsDialog(self).exec()

    def accept(self) -> None:  # noqa: D102
        if self._backup.isChecked():
            if self._has_ts:
                step = TaskStep(op_id="snapshot.timeshift_create", params={})
                self.tasks.append(Task(label=tr("First full backup (Timeshift)"), steps=[step]))
            else:
                step = TaskStep(op_id="package.install", params={"name": "timeshift"})
                self.tasks.append(Task(label=tr("Install Timeshift"), steps=[step]))
        if self._migrate.isChecked():
            self.open_page = "migrate"
        if self._corner_click is not None and self._corner_click.isChecked():
            touchpad.set_corner_right_click(True)  # kullanıcı ayarı; anında geçerli
        super().accept()
