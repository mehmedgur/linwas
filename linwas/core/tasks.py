# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Görev kuyruğu: adımlar, görevler ve kuyruk yönetimi.

Qt'ye bağımlı değildir. Arayüz katmanı bu modülü bir QThread içinde kullanır
ve ilerleme olaylarını Qt sinyallerine dönüştürür.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum

from linwas.core.whitelist import OPERATIONS, RiskLevel, ValidationError, validate


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskStep:
    """Kuyruktaki tek bir işlem adımı."""

    op_id: str
    params: dict[str, str]
    # İngilizce; UI katmanında çevrilir
    label: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            spec = OPERATIONS.get(self.op_id)
            self.label = spec.label if spec else self.op_id

    @property
    def risk(self) -> RiskLevel:
        spec = OPERATIONS.get(self.op_id)
        return spec.risk if spec else RiskLevel.HIGH


@dataclass
class Task:
    """Birlikte kuyruğa giren ve tek polkit onayıyla uygulanan adım grubu."""

    label: str
    steps: list[TaskStep]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: TaskStatus = TaskStatus.PENDING

    @property
    def risk_level(self) -> RiskLevel:
        """En yüksek risk düzeyini döner."""
        risks = [s.risk for s in self.steps]
        if RiskLevel.HIGH in risks:
            return RiskLevel.HIGH
        if RiskLevel.MEDIUM in risks:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def validate_steps(self) -> None:
        """Tüm adımların whitelist'e uygun olduğunu doğrular.

        Herhangi bir adım geçersizse ValidationError fırlatır.
        """
        for i, step in enumerate(self.steps):
            try:
                validate(step.op_id, step.params)
            except ValidationError as exc:
                raise ValidationError(f"Adım {i} ({step.op_id!r}) geçersiz: {exc}") from exc


@dataclass
class TaskProgress:
    """Tek bir ilerleme olayı; kuyruk uygularken yayınlanır."""

    task_id: str
    task_label: str
    step_index: int
    step_total: int
    step_label: str
    done: bool = False
    error: str | None = None
    message: str = ""  # helper'ın gönderdiği çıktı satırı (ayrıntılar için)


ProgressCallback = Callable[[TaskProgress], None]


def _make_progress_collector(
    buf: list[TaskProgress],
    cb: ProgressCallback | None,
) -> ProgressCallback:
    def _handler(p: TaskProgress) -> None:
        buf.append(p)
        if cb:
            cb(p)

    return _handler


class QueueError(Exception):
    """Kuyruk işlemi hatası."""


class TaskQueue:
    """Görev kuyruğu.

    Thread-safe değildir; arayüz katmanı erişimi serileştirmelidir.
    """

    def __init__(self) -> None:
        self._tasks: list[Task] = []

    # --- Kuyruk yönetimi ---

    def add(self, task: Task) -> None:
        """Görevi kuyruğun sonuna ekler. Adımlar önceden doğrulanır."""
        task.validate_steps()
        self._tasks.append(task)

    def remove(self, task_id: str) -> None:
        """Kuyruktaki görevi kaldırır. Görev yoksa QueueError fırlatır."""
        for i, t in enumerate(self._tasks):
            if t.id == task_id:
                if t.status == TaskStatus.RUNNING:
                    raise QueueError(f"Çalışan görev kaldırılamaz: {task_id!r}")
                del self._tasks[i]
                return
        raise QueueError(f"Görev bulunamadı: {task_id!r}")

    def clear(self) -> None:
        """Bekleyen tüm görevleri kaldırır. Çalışan görev varsa hata fırlatır."""
        running = [t for t in self._tasks if t.status == TaskStatus.RUNNING]
        if running:
            raise QueueError("Çalışan görev varken kuyruk temizlenemez")
        self._tasks.clear()

    @property
    def pending(self) -> list[Task]:
        return [t for t in self._tasks if t.status == TaskStatus.PENDING]

    @property
    def all_tasks(self) -> list[Task]:
        return list(self._tasks)

    def __len__(self) -> int:
        return len(self._tasks)

    # --- Uygulama ---

    def apply(
        self,
        executor: Callable[[Task, ProgressCallback], None] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> Iterator[TaskProgress]:
        """Bekleyen tüm görevleri sırayla uygular; her adım için ilerleme yayınlar.

        `executor`: görevi çalıştıran işlev (privilege.run veya test stub'ı).
        Verilmezse doğrudan kuyruktaki görevleri DONE olarak işaretler (test modu).
        """
        for task in list(self.pending):
            task.status = TaskStatus.RUNNING
            total = len(task.steps)
            collected: list[TaskProgress] = []

            # Döngü içinde iç işlev tanımlamak yerine burada lambda yerine
            # dışarıda tanımlı fabrika işlevi kullanılır; B023 önlenir.
            _collect = _make_progress_collector(collected, on_progress)

            try:
                if executor is not None:
                    executor(task, _collect)
                else:
                    # Stub: her adımı tamamlandı say
                    for i, step in enumerate(task.steps):
                        _collect(
                            TaskProgress(
                                task_id=task.id,
                                task_label=task.label,
                                step_index=i,
                                step_total=total,
                                step_label=step.label,
                            )
                        )
                task.status = TaskStatus.DONE
            except Exception as exc:
                task.status = TaskStatus.FAILED
                _collect(
                    TaskProgress(
                        task_id=task.id,
                        task_label=task.label,
                        step_index=0,
                        step_total=total,
                        step_label="",
                        done=True,
                        error=str(exc),
                    )
                )

            yield from collected
