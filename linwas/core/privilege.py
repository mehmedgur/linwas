"""Root helper istemcisi: görevleri pkexec aracılığıyla root olarak çalıştırır.

Geliştirme modu: pkexec python3 -m linwas.core.helper
Kurulu paket:    pkexec /usr/lib/linwas/linwas-helper
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from linwas.core.tasks import Task, TaskProgress

# Kurulu helper yolu (packaging/linwas-launcher.sh benzeri bir sarmalayıcı olur)
_INSTALLED_HELPER = Path("/usr/lib/linwas/linwas-helper")


class HelperError(Exception):
    """Root helper iletişim veya çalıştırma hatası."""


@dataclass
class HelperResponse:
    seq: int
    status: str  # "ok" | "error"
    message: str
    progress: float


def _helper_cmd() -> list[str]:
    """Helper'ı başlatacak komutu döner (kurulu veya geliştirme modu)."""
    if _INSTALLED_HELPER.exists():
        return ["pkexec", str(_INSTALLED_HELPER)]
    # Geliştirme modu: mevcut Python yorumlayıcısıyla modül olarak çalıştır
    return ["pkexec", sys.executable, "-m", "linwas.core.helper"]


def run_task(
    task: Task,
    on_progress: Callable[[TaskProgress], None] | None = None,
) -> list[HelperResponse]:
    """Görevi root helper aracılığıyla çalıştırır; yanıtların listesini döner.

    Herhangi bir adım başarısız olursa HelperError fırlatır.
    """
    if not shutil.which("pkexec"):
        raise HelperError("pkexec bulunamadı; polkit kurulu olmalı")

    cmd = _helper_cmd()
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise HelperError(f"Helper başlatılamadı: {exc}") from exc

    assert proc.stdin is not None
    assert proc.stdout is not None

    # Tüm adımları helper'a gönder
    for i, step in enumerate(task.steps):
        request = json.dumps(
            {"seq": i, "op_id": step.op_id, "params": step.params},
            ensure_ascii=False,
        )
        proc.stdin.write(request + "\n")
    proc.stdin.close()

    responses: list[HelperResponse] = []
    total = len(task.steps)

    for raw_line in proc.stdout:
        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        resp = HelperResponse(
            seq=obj.get("seq", 0),
            status=obj.get("status", "error"),
            message=obj.get("message", ""),
            progress=obj.get("progress", 0.0),
        )
        responses.append(resp)

        if on_progress:
            seq = resp.seq
            step_label = task.steps[seq].label if seq < len(task.steps) else ""
            on_progress(
                TaskProgress(
                    task_id=task.id,
                    task_label=task.label,
                    step_index=seq,
                    step_total=total,
                    step_label=step_label,
                    done=(resp.status == "ok" and resp.progress >= 1.0),
                    error=resp.message if resp.status == "error" else None,
                    message=resp.message if resp.status == "ok" else "",
                )
            )

    proc.wait()

    if proc.returncode != 0:
        stderr = proc.stderr.read() if proc.stderr else ""
        last_error = next(
            (r.message for r in reversed(responses) if r.status == "error"),
            stderr.strip() or "Bilinmeyen hata",
        )
        raise HelperError(f"Helper başarısız (kod {proc.returncode}): {last_error}")

    return responses


def iter_task(
    task: Task,
) -> Iterator[TaskProgress]:
    """Görevi çalıştırır ve her ilerleme olayını üretir (generator)."""
    events: list[TaskProgress] = []

    def _collect(p: TaskProgress) -> None:
        events.append(p)

    try:
        run_task(task, on_progress=_collect)
    except HelperError as exc:
        total = len(task.steps)
        events.append(
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

    yield from events
