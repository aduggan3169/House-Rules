"""Tests for db.py against a fresh in-memory SQLite DB.

Run with: pytest -q
"""

from __future__ import annotations

from datetime import date, timedelta
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


# Convenience helpers used across tests. -------------------------------------

def _tick_all(kid_id: int, day: date) -> None:
    for t in dbmod.list_tasks():
        dbmod.tick_task(kid_id, t["id"], day)


# Phase 1 tests --------------------------------------------------------------

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


# Phase 3 tests --------------------------------------------------------------

def test_week_start_returns_monday():
    # 2026-04-14 is a Tuesday.
    assert dbmod.week_start(date(2026, 4, 14)) == date(2026, 4, 13)
    # 2026-04-13 is a Monday.
    assert dbmod.week_start(date(2026, 4, 13)) == date(2026, 4, 13)
    # 2026-04-19 is a Sunday.
    assert dbmod.week_start(date(2026, 4, 19)) == date(2026, 4, 13)


def test_set_and_clear_ninja_mode(fresh_db):
    kid = dbmod.list_kids()[0]["id"]
    today = date(2026, 4, 14)

    assert dbmod.get_day(kid, today)["ninja"] is None

    dbmod.set_ninja_mode(kid, today, maintained=True, note="Lunch at Nana's")
    ninja = dbmod.get_day(kid, today)["ninja"]
    assert ninja == {"maintained": True, "note": "Lunch at Nana's"}

    # Upsert should update in place.
    dbmod.set_ninja_mode(kid, today, maintained=False, note=None)
    ninja = dbmod.get_day(kid, today)["ninja"]
    assert ninja == {"maintained": False, "note": None}

    dbmod.clear_ninja_mode(kid, today)
    assert dbmod.get_day(kid, today)["ninja"] is None

    # Clearing a row that doesn't exist must be idempotent.
    dbmod.clear_ninja_mode(kid, today)


def test_daily_screen_earned(fresh_db):
    kid = dbmod.list_kids()[0]["id"]
    today = date(2026, 4, 14)

    assert dbmod.daily_screen_earned(kid, today) is False

    # Tick all but the last.
    for t in dbmod.list_tasks()[:-1]:
        dbmod.tick_task(kid, t["id"], today)
    assert dbmod.daily_screen_earned(kid, today) is False

    # Tick the last one.
    last = dbmod.list_tasks()[-1]
    dbmod.tick_task(kid, last["id"], today)
    assert dbmod.daily_screen_earned(kid, today) is True


def test_week_days_complete_and_week_complete(fresh_db):
    kid = dbmod.list_kids()[0]["id"]
    mon = date(2026, 4, 13)  # Monday

    assert dbmod.week_days_complete(kid, mon) == 0
    assert dbmod.week_complete(kid, mon) is False

    # Tick all tasks for Mon, Tue, Wed.
    for offset in range(3):
        _tick_all(kid, mon + timedelta(days=offset))
    assert dbmod.week_days_complete(kid, mon) == 3
    assert dbmod.week_complete(kid, mon) is False

    # Fill in Thu..Sun.
    for offset in range(3, 7):
        _tick_all(kid, mon + timedelta(days=offset))
    assert dbmod.week_days_complete(kid, mon) == 7
    assert dbmod.week_complete(kid, mon) is True


def test_ninja_streak_intact(fresh_db):
    kid = dbmod.list_kids()[0]["id"]
    mon = date(2026, 4, 13)

    # No ninja days in the week: not eligible.
    assert dbmod.ninja_streak_intact(kid, mon) is False

    # Single maintained ninja day: eligible.
    dbmod.set_ninja_mode(kid, mon + timedelta(days=2), True, "Dinner out")
    assert dbmod.ninja_streak_intact(kid, mon) is True

    # A second, broken ninja day in the same week breaks the streak.
    dbmod.set_ninja_mode(kid, mon + timedelta(days=5), False, "Meltdown")
    assert dbmod.ninja_streak_intact(kid, mon) is False

    # Clearing the broken day restores eligibility.
    dbmod.clear_ninja_mode(kid, mon + timedelta(days=5))
    assert dbmod.ninja_streak_intact(kid, mon) is True

    # A ninja day in the *following* week doesn't count.
    next_mon = mon + timedelta(days=7)
    assert dbmod.ninja_streak_intact(kid, next_mon) is False
    dbmod.set_ninja_mode(kid, next_mon + timedelta(days=1), True, None)
    assert dbmod.ninja_streak_intact(kid, next_mon) is True
    # Original week unchanged.
    assert dbmod.ninja_streak_intact(kid, mon) is True


def test_claim_reward_idempotency(fresh_db):
    kid = dbmod.list_kids()[0]["id"]
    today = date(2026, 4, 14)

    assert dbmod.reward_claimed(kid, dbmod.REWARD_DAILY_SCREEN, today) is False

    assert dbmod.claim_reward(kid, dbmod.REWARD_DAILY_SCREEN, today) is True
    assert dbmod.reward_claimed(kid, dbmod.REWARD_DAILY_SCREEN, today) is True

    # Second claim for the same (kid, type, period) returns False.
    assert dbmod.claim_reward(kid, dbmod.REWARD_DAILY_SCREEN, today) is False


def test_claim_reward_scopes(fresh_db):
    """Claims are scoped by kid, type, and period_start independently."""
    cillian, fionn = [k["id"] for k in dbmod.list_kids()]
    today = date(2026, 4, 14)
    other = date(2026, 4, 15)
    mon = dbmod.week_start(today)

    assert dbmod.claim_reward(cillian, dbmod.REWARD_DAILY_SCREEN, today)
    assert dbmod.claim_reward(fionn, dbmod.REWARD_DAILY_SCREEN, today)
    assert dbmod.claim_reward(cillian, dbmod.REWARD_DAILY_SCREEN, other)
    assert dbmod.claim_reward(cillian, dbmod.REWARD_WEEKLY_TREAT, mon)
    assert dbmod.claim_reward(cillian, dbmod.REWARD_NINJA_TREAT, mon)

    # And the matching reward_claimed checks.
    assert dbmod.reward_claimed(fionn, dbmod.REWARD_DAILY_SCREEN, today)
    assert not dbmod.reward_claimed(fionn, dbmod.REWARD_WEEKLY_TREAT, mon)
