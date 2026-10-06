"""Geri alma kaydı testleri."""

import pytest

from linwas.core.rollback import (
    FileBackup,
    RollbackRecord,
    list_records,
    load_record,
    save_record,
    undo_ops,
)


@pytest.fixture
def rollback_dir(tmp_path):
    return tmp_path / "rollback"


def make_record(**kwargs):
    defaults = dict(task_label="Test görevi")
    defaults.update(kwargs)
    return RollbackRecord(**defaults)


class TestRollbackRecordSerialization:
    def test_round_trip_empty(self):
        r = make_record()
        r2 = RollbackRecord.from_json(r.to_json())
        assert r2.id == r.id
        assert r2.task_label == r.task_label
        assert r2.file_backups == []
        assert r2.packages_to_install == []
        assert r2.packages_to_remove == []

    def test_round_trip_with_backups(self):
        backup = FileBackup("/etc/linwas/config.conf", "/var/lib/linwas/rollback/x/config.conf")
        r = make_record(
            file_backups=[backup],
            packages_to_install=["vlc"],
            packages_to_remove=["old-pkg"],
        )
        r2 = RollbackRecord.from_json(r.to_json())
        assert len(r2.file_backups) == 1
        assert r2.file_backups[0].original_path == "/etc/linwas/config.conf"
        assert r2.packages_to_install == ["vlc"]
        assert r2.packages_to_remove == ["old-pkg"]


class TestSaveLoad:
    def test_save_creates_file(self, rollback_dir):
        r = make_record()
        path = save_record(r, base_dir=rollback_dir)
        assert path.exists()

    def test_load_returns_record(self, rollback_dir):
        r = make_record(task_label="Yüklenen görev")
        save_record(r, base_dir=rollback_dir)
        r2 = load_record(r.id, base_dir=rollback_dir)
        assert r2.task_label == "Yüklenen görev"

    def test_load_missing_raises(self, rollback_dir):
        with pytest.raises(FileNotFoundError):
            load_record("nonexistent", base_dir=rollback_dir)


class TestListRecords:
    def test_empty_dir_returns_empty(self, rollback_dir):
        assert list_records(base_dir=rollback_dir) == []

    def test_lists_saved_records(self, rollback_dir):
        save_record(make_record(task_label="A"), base_dir=rollback_dir)
        save_record(make_record(task_label="B"), base_dir=rollback_dir)
        records = list_records(base_dir=rollback_dir)
        assert len(records) == 2

    def test_skips_corrupted(self, rollback_dir):
        r = make_record()
        path = save_record(r, base_dir=rollback_dir)
        path.write_text("bozuk json")
        # Bozuk kayıt atlanır, hata fırlatılmaz
        records = list_records(base_dir=rollback_dir)
        assert records == []


class TestUndoOps:
    def test_undo_installed_packages(self):
        r = make_record(packages_to_install=["vlc", "ffmpeg"])
        ops = undo_ops(r)
        remove_ops = [(op, p) for op, p in ops if op == "package.remove"]
        names = {p["name"] for _, p in remove_ops}
        assert names == {"vlc", "ffmpeg"}

    def test_undo_removed_packages(self):
        r = make_record(packages_to_remove=["old-pkg"])
        ops = undo_ops(r)
        install_ops = [(op, p) for op, p in ops if op == "package.install"]
        assert any(p["name"] == "old-pkg" for _, p in install_ops)

    def test_undo_file_backups(self):
        backup = FileBackup("/etc/linwas/config.conf", "/var/lib/linwas/rollback/x/config.conf")
        r = make_record(file_backups=[backup])
        ops = undo_ops(r)
        file_ops = [(op, p) for op, p in ops if op == "file.write_text"]
        assert any(p["path"] == "/etc/linwas/config.conf" for _, p in file_ops)

    def test_empty_record_no_ops(self):
        r = make_record()
        assert undo_ops(r) == []
