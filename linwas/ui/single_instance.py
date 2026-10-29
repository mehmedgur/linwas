# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Tek kopya: Linwas zaten çalışıyorsa ikinci başlatma iletisini ona iletir ve kapanır.

Kullanıcıya özel yerel soket (QLocalServer, ad: linwas-<uid>). İletiler: "show",
"background", "deb:<yol>", "exe:<yol>".
"""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def _name() -> str:
    return f"linwas-{os.getuid()}"


class SingleInstance(QObject):
    message_received = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._server: QLocalServer | None = None

    def send_to_running(self, message: str) -> bool:
        """Çalışan kopya varsa iletiyi gönderir ve True döner."""
        socket = QLocalSocket()
        socket.connectToServer(_name())
        if not socket.waitForConnected(500):
            return False
        socket.write(message.encode("utf-8"))
        socket.flush()
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        return True

    def listen(self) -> bool:
        server = QLocalServer(self)
        # Önceki kopya çökmüşse kalan soket dosyası temizlenir
        QLocalServer.removeServer(_name())
        if not server.listen(_name()):
            return False
        server.newConnection.connect(self._on_connection)
        self._server = server
        return True

    def _on_connection(self) -> None:
        if self._server is None:
            return
        socket = self._server.nextPendingConnection()
        if socket is None:
            return

        def read() -> None:
            data = bytes(socket.readAll()).decode("utf-8", errors="replace").strip()
            if data:
                self.message_received.emit(data)

        socket.readyRead.connect(read)
        socket.disconnected.connect(socket.deleteLater)
