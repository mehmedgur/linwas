"""Aylık token kullanım sayacı testleri."""

import pytest

from linwas.ai.usage import UsageDB


@pytest.fixture
def db(tmp_path):
    return UsageDB(db_path=tmp_path / "usage.db")


def test_record_and_get(db):
    db.record("chatgpt", 100, 50)
    usage = db.get("chatgpt")
    assert usage.input_tokens == 100
    assert usage.output_tokens == 50
    assert usage.total == 150


def test_record_accumulates(db):
    db.record("chatgpt", 100, 50)
    db.record("chatgpt", 200, 100)
    usage = db.get("chatgpt")
    assert usage.total == 450


def test_different_providers_isolated(db):
    db.record("chatgpt", 100, 0)
    db.record("gemini", 50, 0)
    assert db.get("chatgpt").total == 100
    assert db.get("gemini").total == 50


def test_no_usage_returns_zero(db):
    usage = db.get("unknown_provider")
    assert usage.total == 0


def test_set_limit(db):
    db.set_limit("chatgpt", 10000)
    usage = db.get("chatgpt")
    assert usage.limit == 10000
    assert not usage.limit_reached


def test_limit_reached(db):
    db.set_limit("chatgpt", 100)
    db.record("chatgpt", 60, 50)
    usage = db.get("chatgpt")
    assert usage.limit_reached


def test_unlimited(db):
    db.set_limit("chatgpt", 0)
    db.record("chatgpt", 999999, 0)
    usage = db.get("chatgpt")
    assert not usage.limit_reached


def test_all_months(db):
    db.record("chatgpt", 100, 50)
    months = db.all_months("chatgpt")
    assert len(months) == 1
    assert months[0].total == 150
