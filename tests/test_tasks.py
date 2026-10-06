"""Görev kuyruğu testleri."""

import pytest

from linwas.core.tasks import QueueError, Task, TaskProgress, TaskQueue, TaskStatus, TaskStep
from linwas.core.whitelist import ValidationError


def make_task(label="Test görevi", op="package.install", pkg="vlc"):
    return Task(label=label, steps=[TaskStep(op_id=op, params={"name": pkg})])


class TestTaskStep:
    def test_label_defaults_from_spec(self):
        step = TaskStep(op_id="package.install", params={"name": "vlc"})
        assert step.label == "Install package"

    def test_custom_label(self):
        step = TaskStep(op_id="package.install", params={"name": "vlc"}, label="VLC kur")
        assert step.label == "VLC kur"

    def test_risk_from_spec(self):
        from linwas.core.whitelist import RiskLevel

        step = TaskStep(op_id="package.install", params={"name": "vlc"})
        assert step.risk == RiskLevel.LOW

    def test_risk_high_for_unknown(self):
        from linwas.core.whitelist import RiskLevel

        step = TaskStep(op_id="unknown.op", params={})
        assert step.risk == RiskLevel.HIGH


class TestTask:
    def test_validate_steps_ok(self):
        task = make_task()
        task.validate_steps()  # hata fırlatmamalı

    def test_validate_steps_bad_op(self):
        task = Task(
            label="Hatalı görev",
            steps=[TaskStep(op_id="evil.op", params={})],
        )
        with pytest.raises(ValidationError):
            task.validate_steps()

    def test_validate_steps_bad_params(self):
        task = Task(
            label="Hatalı param",
            steps=[TaskStep(op_id="package.install", params={"name": "VLC with spaces"})],
        )
        with pytest.raises(ValidationError):
            task.validate_steps()

    def test_risk_level_high_wins(self):
        from linwas.core.whitelist import RiskLevel

        task = Task(
            label="Karma risk",
            steps=[
                TaskStep(op_id="package.install", params={"name": "vlc"}),
                TaskStep(op_id="deb.install", params={"path": "/tmp/app.deb"}),
            ],
        )
        assert task.risk_level == RiskLevel.HIGH

    def test_risk_level_low_all(self):
        from linwas.core.whitelist import RiskLevel

        task = make_task()
        assert task.risk_level == RiskLevel.LOW


class TestTaskQueue:
    def test_add_and_len(self):
        q = TaskQueue()
        q.add(make_task())
        assert len(q) == 1

    def test_add_invalid_raises(self):
        q = TaskQueue()
        with pytest.raises(ValidationError):
            q.add(Task(label="x", steps=[TaskStep(op_id="evil.op", params={})]))

    def test_remove(self):
        q = TaskQueue()
        task = make_task()
        q.add(task)
        q.remove(task.id)
        assert len(q) == 0

    def test_remove_missing_raises(self):
        q = TaskQueue()
        with pytest.raises(QueueError):
            q.remove("nonexistent-id")

    def test_pending_excludes_done(self):
        q = TaskQueue()
        task = make_task()
        q.add(task)
        list(q.apply())  # stub executor → DONE
        assert task.status == TaskStatus.DONE
        assert task not in q.pending

    def test_apply_stub_yields_progress(self):
        q = TaskQueue()
        task = make_task()
        q.add(task)
        events = list(q.apply())
        assert len(events) >= 1
        assert all(isinstance(e, TaskProgress) for e in events)

    def test_apply_sets_done_status(self):
        q = TaskQueue()
        task = make_task()
        q.add(task)
        list(q.apply())
        assert task.status == TaskStatus.DONE

    def test_apply_callback(self):
        q = TaskQueue()
        q.add(make_task())
        received = []
        list(q.apply(on_progress=received.append))
        assert len(received) >= 1

    def test_apply_executor_error(self):
        def bad_executor(task, cb):
            raise RuntimeError("simüle hata")

        q = TaskQueue()
        task = make_task()
        q.add(task)
        events = list(q.apply(executor=bad_executor))
        assert task.status == TaskStatus.FAILED
        errors = [e for e in events if e.error]
        assert len(errors) == 1
        assert "simüle hata" in errors[0].error

    def test_clear_removes_pending(self):
        q = TaskQueue()
        q.add(make_task())
        q.add(make_task())
        q.clear()
        assert len(q) == 0
