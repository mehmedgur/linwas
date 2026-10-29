# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Arka plan işi: bir işlevi iş parçacığında çalıştırır, sonucu sinyalle ana parçacığa verir."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThread, Signal


class Job(QThread):
    done = Signal(object)

    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.done.emit(self._fn())
        except Exception:
            self.done.emit(None)


# Çalışan işler: sahibi (sayfa/kart) önce yok edilse bile iş parçacığı bitene kadar yaşar;
# "QThread: Destroyed while thread is still running" çökmesini önler.
_ACTIVE: set[Job] = set()


class Jobs:
    """İşleri referansta tutar (QThread çalışırken silinmesin)."""

    def __init__(self) -> None:
        self._jobs: list[Job] = []

    def run(self, fn: Callable[[], object], slot: Callable[[object], None]) -> Job:
        job = Job(fn)
        job.done.connect(slot)
        job.finished.connect(lambda: self._release(job))
        self._jobs.append(job)
        _ACTIVE.add(job)
        job.start()
        return job

    def _release(self, job: Job) -> None:
        # "finished" iş parçacığı tamamen kapanmadan gelir: silmeden önce bitmesini bekle
        job.wait()
        _ACTIVE.discard(job)
        if job in self._jobs:
            self._jobs.remove(job)
