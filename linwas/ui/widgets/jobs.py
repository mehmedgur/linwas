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


class Jobs:
    """İşleri referansta tutar (QThread çalışırken silinmesin)."""

    def __init__(self) -> None:
        self._jobs: list[Job] = []

    def run(self, fn: Callable[[], object], slot: Callable[[object], None]) -> Job:
        job = Job(fn)
        job.done.connect(slot)
        job.finished.connect(lambda: self._jobs.remove(job))
        self._jobs.append(job)
        job.start()
        return job
