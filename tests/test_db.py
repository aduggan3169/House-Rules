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

    for t in dbmod.list_tasks()[:-1]:
        dbmod.tick_task(kid, t["id"], today)
    assert dbmod.daily_screen_earned(kid, today) is False

    last = dbmod.list_tasks()[-1]
    dbmod.tick_task(kid, last["id"], today)
    assert dbmod.daily_screen_earned(kid, today) is True


def test_week_days_complete_and_week_complete(fresh_db):
    kid = dbmod.list_kids()[0]["id"]
    mon = date(2026, 4, 13)

    assert dbmod.week_days_complete(kid, mon) == 0
    assert dbmod.week_complete(kid, mon) is False

    for offset in range(3):
        _tick_all(kid, mon + timedelta(days=offset))
    assert dbmod.week_days_complete(kid, mon) == 3
    assert dbmod.week_complete(kid, mon) is False

    for offset in range(3, 7):
        _tick_all(kid, mon + timedelta(days=offset))
    assert dbmod.week_days_complete(kid, mon) == 7
    assert dbmod.week_complete(kid, mon) is True


def test_ninja_streak_intact(fresh_db):
    kid = dbmod.list_kids()[0]["id"]
    mon = date(2026, 4, 13)

    assert dbmod.ninja_streak_intact(kid, mon) is False

    dbmod.set_ninja_mode(kid, mon + timedelta(days=2), True, "Dinner out")
    assert dbmod.ninja_streak_intact(kid, mon) is True

    dbmod.set_ninja_mode(kid, mon + timedelta(days=5), False, "Meltdown")
    assert dbmod.ninja_streak_intact(kid, mon) is False

    dbmod.clear_ninja_mode(kid, mon + timedelta(days=5))
    assert dbmod.ninja_streak_intact(kid, mon) is True

    next_mon = mon + timedelta(days=7)
    assert dbmod.ninja_streak_intact(kid, next_mon) is False
    dbmod.set_ninja_mode(kid, next_mon + timedelta(days=1), True, None)
    assert dbmod.ninja_streak_intact(kid, next_mon) is True
    assert dbmod.ninja_streak_intact(kid, mon) is True


def test_claim_reward_idempotency(fresh_db):
    kid = dbmod.list_kids()[0]["id"]
    today = date(2026, 4, 14)

    assert dbmod.reward_claimed(kid, dbmod.REWARD_DAILY_SCREEN, today) is False

    assert dbmod.claim_reward(kid, dbmod.REWARD_DAILY_SCREEN, today) is True
    assert dbmod.reward_claimed(kid, dbmod.REWARD_DAILY_SCREEN, today) is True

    assert dbmod.claim_reward(kid, dbmod.REWARD_DAILY_SCREEN, today) is False


def test_claim_reward_scopes(fresh_db):
    cillian, fionn = [k["id"] for k in dbmod.list_kids()]
    today = date(2026, 4, 14)
    other = date(2026, 4, 15)
    mon = dbmod.week_start(today)

    assert dbmod.claim_reward(cillian, dbmod.REWARD_DAILY_SCREEN, today)
    assert dbmod.claim_reward(fionn, dbmod.REWARD_DAILY_SCREEN, today)
    assert dbmod.claim_reward(cillian, dbmod.REWARD_DAILY_SCREEN, other)
    assert dbmod.claim_reward(cillian, dbmod.REWARD_WEEKLY_TREAT, mon)
    assert dbmod.claim_reward(cillian, dbmod.REWARD_NINJA_TREAT, mon)

    assert dbmod.reward_claimed(fionn, dbmod.REWARD_DAILY_SCREEN, today)
    assert not dbmod.reward_claimed(fionn, dbmod.REWARD_WEEKLY_TREAT, mon)


# Phase 4 tests --------------------------------------------------------------

def test_reset_day_clears_completions_and_ninja(fresh_db):
    kid = dbmod.list_kids()[0]["id"]
    other_kid = dbmod.list_kids()[1]["id"]
    today = date(2026, 4, 14)
    other_day = date(2026, 4, 15)

    _tick_all(kid, today)
    _tick_all(kid, other_day)
    _tick_all(other_kid, today)
    dbmod.set_ninja_mode(kid, today, True, "Lunch")
    dbmod.set_ninja_mode(kid, other_day, True, "Dinner")

    dbmod.reset_day(kid, today)

    # The target day is wiped for the target kid.
    assert dbmod.get_day(kid, today) == {"completions": {}, "ninja": None}

    # Other days and other kids are untouched.
    assert dbmod.get_day(kid, other_day)["completions"]
    assert dbmod.get_day(kid, other_day)["ninja"] is not None
    assert dbmod.get_day(other_kid, today)["completions"]

    # Idempotent.
    dbmod.reset_day(kid, today)


def test_revoke_reward(fresh_db):
    kid = dbmod.list_kids()[0]["id"]
    today = date(2026, 4, 14)

    assert dbmod.revoke_reward(kid, dbmod.REWARD_DAILY_SCREEN, today) is False

    dbmod.claim_reward(kid, dbmod.REWARD_DAILY_SCREEN, today)
    assert dbmod.reward_claimed(kid, dbmod.REWARD_DAILY_SCREEN, today)

    assert dbmod.revoke_reward(kid, dbmod.REWARD_DAILY_SCREEN, today) is True
    assert not dbmod.reward_claimed(kid, dbmod.REWARD_DAILY_SCREEN, today)

    # A fresh claim should be possible after revoking.
    assert dbmod.claim_reward(kid, dbmod.REWARD_DAILY_SCREEN, today) is True


def test_add_task_appends_at_end(fresh_db):
    before = dbmod.list_tasks()
    new_id = dbmod.add_task("Make the bed")
    after = dbmod.list_tasks()

    assert len(after) == len(before) + 1
    assert after[-1]["id"] == new_id
    assert after[-1]["label"] == "Make the bed"
    assert after[-1]["display_order"] > before[-1]["display_order"]
    assert after[-1]["active"] == 1


def test_rename_task(fresh_db):
    task = dbmod.list_tasks()[0]
    dbmod.rename_task(task["id"], "Cepillarse los dientes")
    assert dbmod.list_tasks()[0]["label"] == "Cepillarse los dientes"


def test_deactivate_and_reactivate_task(fresh_db):
    task = dbmod.list_tasks()[0]
    dbmod.deactivate_task(task["id"])

    # Excluded by default.
    assert task["id"] not in [t["id"] for t in dbmod.list_tasks()]
    # Included when asked.
    all_tasks = dbmod.list_tasks(include_inactive=True)
    deactivated = next(t for t in all_tasks if t["id"] == task["id"])
    assert deactivated["active"] == 0

    dbmod.reactivate_task(task["id"])
    assert task["id"] in [t["id"] for t in dbmod.list_tasks()]


def test_reorder_tasks(fresh_db):
    original = [t["id"] for t in dbmod.list_tasks()]
    assert len(original) == 4

    reversed_order = list(reversed(original))
    dbmod.reorder_tasks(reversed_order)

    assert [t["id"] for t in dbmod.list_tasks()] == reversed_order
