"""Tests for db.py against a fresh in-memory SQLite DB.

Run with: pytest -q
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

import db as dbmod


@pytest.fixture()
def fresh_db():
    """Point db.py at a fresh in-memory SQLite DB for each test.

    StaticPool ensures every connection shares the same underlying DB
    (in-memory SQLite is per-connection by default).
    """
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON;")
        cur.close()

    dbmod.set_engine(engine)
    schema = Path(__file__).parent.parent / "schema.sql"
    dbmod.init_db(schema)
    yield engine
    engine.dispose()


def test_kids_seeded(fresh_db):
    kids = dbmod.list_kids()
    assert [k["name"] for k in kids] == ["Cillian", "Fionn"]


def test_tasks_seeded(fresh_db):
    tasks = dbmod.list_tasks()
    labels = [t["label"] for t in tasks]
    assert labels == [
        "Brush teeth",
        "Dressed before breakfast",
        "Plates away after meals",
        "Be kind & respectful",
    ]


def test_init_db_is_idempotent(fresh_db):
    dbmod.init_db(Path(__file__).parent.parent / "schema.sql")
    assert len(dbmod.list_kids()) == 2
    assert len(dbmod.list_tasks()) == 4


def test_tick_and_get_day(fresh_db):
    cillian = dbmod.list_kids()[0]["id"]
    brush = dbmod.list_tasks()[0]["id"]
    today = date(2026, 4, 14)

    day = dbmod.get_day(cillian, today)
    assert day == {"completions": {}, "ninja": None}

    dbmod.tick_task(cillian, brush, today)
    day = dbmod.get_day(cillian, today)
    assert brush in day["completions"]
    assert day["completions"][brush] is not None


def test_tick_is_idempotent(fresh_db):
    kid = dbmod.list_kids()[0]["id"]
    task = dbmod.list_tasks()[0]["id"]
    today = date(2026, 4, 14)

    dbmod.tick_task(kid, task, today)
    dbmod.tick_task(kid, task, today)
    day = dbmod.get_day(kid, today)
    assert len(day["completions"]) == 1


def test_untick_removes_row(fresh_db):
    kid = dbmod.list_kids()[0]["id"]
    task = dbmod.list_tasks()[0]["id"]
    today = date(2026, 4, 14)

    dbmod.tick_task(kid, task, today)
    dbmod.untick_task(kid, task, today)
    day = dbmod.get_day(kid, today)
    assert day["completions"] == {}


def test_untick_is_idempotent(fresh_db):
    kid = dbmod.list_kids()[0]["id"]
    task = dbmod.list_tasks()[0]["id"]
    today = date(2026, 4, 14)

    dbmod.untick_task(kid, task, today)
    assert dbmod.get_day(kid, today)["completions"] == {}


def test_get_day_isolates_kids_and_dates(fresh_db):
    cillian, fionn = [k["id"] for k in dbmod.list_kids()]
    task = dbmod.list_tasks()[0]["id"]
    d1 = date(2026, 4, 14)
    d2 = date(2026, 4, 15)

    dbmod.tick_task(cillian, task, d1)

    assert dbmod.get_day(cillian, d1)["completions"] != {}
    assert dbmod.get_day(cillian, d2)["completions"] == {}
    assert dbmod.get_day(fionn, d1)["completions"] == {}
