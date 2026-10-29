# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Programlar › Windows programları: Wine ile kurulan programlar ve ortamlar."""

from __future__ import annotations

import html

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import wine
from linwas.ui.widgets.card import Card
from linwas.ui.wine_runner import WineRunner


def tr(text: str) -> str:
    return QCoreApplication.translate("WindowsAppsView", text)


def _clear(layout: QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()


class WindowsAppsView(QWidget):
    """Kısayollar (aç / kaldır) ve ayrı ortamlar (sil)."""

    open_exe_requested = Signal()  # ".exe aç" düğmesi → sayfa dosya seçtirir

    def __init__(self, runner: WineRunner, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = runner
        runner.finished.connect(self.reload)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(12)

        top = QHBoxLayout()
        intro = QLabel(
            tr(
                "Windows programs run with Wine. Prefer a Linux alternative when there is one; "
                "it is faster and gets updates automatically."
            ),
            content,
        )
        intro.setObjectName("Secondary")
        intro.setWordWrap(True)
        top.addWidget(intro, 1)
        open_btn = QPushButton(tr("Open a Windows program…"), content)
        open_btn.clicked.connect(self.open_exe_requested)
        top.addWidget(open_btn, 0, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(top)

        self._apps_card = Card(content)
        outer.addWidget(self._apps_card)
        self._envs_card = Card(content)
        outer.addWidget(self._envs_card)
        outer.addStretch(1)
        scroll.setWidget(content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        self.reload()
        super().showEvent(event)  # type: ignore[arg-type]

    def reload(self) -> None:
        envs = {e.id: e for e in wine.list_envs()}
        shortcuts = wine.list_shortcuts()
        self._fill_apps(shortcuts, envs)
        self._fill_envs(list(envs.values()), shortcuts)

    def _fill_apps(self, shortcuts: list[wine.WineShortcut], envs: dict) -> None:
        layout = self._apps_card.layout
        _clear(layout)
        title = QLabel(tr("Installed Windows programs"), self._apps_card)
        title.setObjectName("H2")
        layout.addWidget(title)
        if not wine.wine_available():
            layout.addWidget(QLabel(tr("Wine is not installed."), self._apps_card))
            return
        if not shortcuts:
            empty = QLabel(
                tr("No Windows programs yet. Open a setup file (.exe or .msi) to install one."),
                self._apps_card,
            )
            empty.setObjectName("Secondary")
            empty.setWordWrap(True)
            layout.addWidget(empty)
            return
        for sc in shortcuts:
            row = QHBoxLayout()
            env = envs.get(sc.env_id)
            where = (
                tr("shared environment")
                if sc.env_id == wine.SHARED_ID
                else (env.name if env else sc.env_id)
            )
            name = QLabel(
                f"<b>{html.escape(sc.name)}</b>  ·  {html.escape(where)}", self._apps_card
            )
            row.addWidget(name, 1)
            run = QPushButton(tr("Open"), self._apps_card)
            run.clicked.connect(lambda _=False, s=sc: self._runner.run_shortcut(s))
            row.addWidget(run)
            remove = QPushButton(tr("Remove"), self._apps_card)
            remove.clicked.connect(lambda _=False, s=sc: self._remove_app(s))
            row.addWidget(remove)
            layout.addLayout(row)

    def _fill_envs(self, envs: list[wine.WineEnv], shortcuts: list[wine.WineShortcut]) -> None:
        layout = self._envs_card.layout
        _clear(layout)
        title = QLabel(tr("Environments"), self._envs_card)
        title.setObjectName("H2")
        layout.addWidget(title)
        if not envs:
            empty = QLabel(tr("No environments yet."), self._envs_card)
            empty.setObjectName("Secondary")
            layout.addWidget(empty)
            return
        reasons = {
            "risk": tr("risky file"),
            "user": tr("your choice"),
            "retry": tr("did not work in the shared environment"),
        }
        for env in envs:
            row = QHBoxLayout()
            count = sum(1 for s in shortcuts if s.env_id == env.id)
            if env.shared:
                text = tr("Shared environment — {n} program(s)").format(n=count)
            else:
                text = tr("{name} — separate ({why})").format(
                    name=env.name, why=reasons.get(env.reason, env.reason)
                )
            row.addWidget(QLabel(html.escape(text), self._envs_card), 1)
            if env.shared:
                btn = QPushButton(tr("Add or remove programs"), self._envs_card)
                btn.clicked.connect(lambda _=False, e=env: self._runner.run_uninstaller(e))
            else:
                btn = QPushButton(tr("Delete"), self._envs_card)
                btn.clicked.connect(lambda _=False, e=env: self._delete_env(e))
            row.addWidget(btn)
            layout.addLayout(row)

    def _remove_app(self, sc: wine.WineShortcut) -> None:
        if sc.env_id == wine.SHARED_ID:
            # Ortak ortamda yalnızca program kaldırılır: Wine'ın kaldırma penceresi
            QMessageBox.information(
                self,
                tr("Remove {name}").format(name=sc.name),
                tr("Wine's program list will open. Select {name} and click Remove.").format(
                    name=sc.name
                ),
            )
            env = next((e for e in wine.list_envs() if e.shared), None)
            if env:
                self._runner.run_uninstaller(env)
            return
        env = next((e for e in wine.list_envs() if e.id == sc.env_id), None)
        if env:
            self._delete_env(env)

    def _delete_env(self, env: wine.WineEnv) -> None:
        answer = QMessageBox.question(
            self,
            tr("Delete environment"),
            tr(
                'Delete the separate environment "{name}"? All programs and files in it '
                "will be removed. This can't be undone."
            ).format(name=env.name),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not wine.remove_env(env.id):
            QMessageBox.warning(self, tr("Delete environment"), tr("It could not be deleted."))
        self.reload()
