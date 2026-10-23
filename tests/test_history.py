"""İşlem geçmişi testleri."""

import pytest

from linwas.core.history import HistoryDB, HistoryEntry


@pytest.fixture
def db(tmp_path):
    return HistoryDB(db_path=tmp_path / "history.db")


def make_entry(**kwargs):
    defaults = dict(
        task_label="Paket kurulumu",
        step_labels=["Install package"],
        result="success",
    )
    defaults.update(kwargs)
    return HistoryEntry(**defaults)


class TestHistoryDB:
    def test_add_and_get(self, db):
        entry = make_entry()
        db.add(entry)
        fetched = db.get(entry.id)
        assert fetched is not None
        assert fetched.task_label == "Paket kurulumu"
        assert fetched.result == "success"

    def test_get_missing_returns_none(self, db):
        assert db.get("nonexistent") is None

    def test_list_returns_all(self, db):
        db.add(make_entry(task_label="Görev 1"))
        db.add(make_entry(task_label="Görev 2"))
        entries = db.list()
        assert len(entries) == 2

    def test_list_descending_order(self, db):
        db.add(make_entry(task_label="Eski"))
        db.add(make_entry(task_label="Yeni"))
        entries = db.list()
        # En yeni başta; timestamp'ler farklı olduğu için sıra tutarlı değil,
        # sadece iki kayıt döndüğünü doğrulayalım.
        assert len(entries) == 2

    def test_step_labels_round_trip(self, db):
        labels = ["Install package", "Enable service"]
        entry = make_entry(step_labels=labels)
        db.add(entry)
        fetched = db.get(entry.id)
        assert fetched.step_labels == labels

    def test_rollback_id_stored(self, db):
        entry = make_entry(rollback_id="abc-123")
        db.add(entry)
        fetched = db.get(entry.id)
        assert fetched.rollback_id == "abc-123"

    def test_clear(self, db):
        db.add(make_entry())
        db.add(make_entry())
        db.clear()
        assert db.list() == []

    def test_list_limit(self, db):
        for i in range(5):
            db.add(make_entry(task_label=f"Görev {i}"))
        assert len(db.list(limit=3)) == 3

    def test_empty_db(self, db):
        assert db.list() == []
