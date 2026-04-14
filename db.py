"""Persistence layer for the House Rules app.

All database access goes through this module. app.py must not import
SQLAlchemy directly. Functions take and return plain Python types
(dicts, lists, primitives) so the storage backend is swappable
(SQLite now, Postgres/Supabase later) by changing only DATABASE_URL
and, if needed, the tiny engine-construction block at the top.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

load_dotenv()

# Default to a local SQLite file if DATABASE_URL is unset (dev convenience).
_DEFAULT_URL = "sqlite:///./data/house_rules.db"

_DEFAULT_TASKS: list[tuple[str, int]] = [
    ("Brush teeth", 1),
    ("Dressed before breakfast", 2),
    ("Plates away after meals", 3),
    ("Be kind & respectful", 4),
]

# Reward type constants — kept here so app.py doesn't invent strings.
REWARD_DAILY_SCREEN = "daily_screen"
REWARD_WEEKLY_TREAT = "weekly_treat"
REWARD_NINJA_TREAT = "ninja_treat"


def _make_engine(url: str | None = None) -> Engine:
    """Create an Engine. For SQLite, ensure the parent dir exists and
    enable foreign keys (off by default in SQLite)."""
    url = url or os.environ.get("DATABASE_URL", _DEFAULT_URL)
    if url.startswith("sqlite"):
        db_path = url.split("sqlite:///", 1)[-1]
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, future=True)

    if url.startswith("sqlite"):
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys = ON;")
            cur.close()

    return engine


# Module-level engine. Tests can swap it via set_engine().
_engine: Engine = _make_engine()


def set_engine(engine: Engine) -> None:
    """Override the module-level engine (used by tests)."""
    global _engine
    _engine = engine


def get_engine() -> Engine:
    return _engine


# --------------------------------------------------------------------------- #
# Date helpers
# --------------------------------------------------------------------------- #

def week_start(day: date) -> date:
    """Return the Monday of the week containing `day` (weekday()==0)."""
    return day - timedelta(days=day.weekday())


# --------------------------------------------------------------------------- #
# Schema / seed
# --------------------------------------------------------------------------- #

def init_db(schema_path: str | Path | None = None) -> None:
    """Apply schema.sql and ensure default tasks exist. Idempotent."""
    schema_path = Path(schema_path or Path(__file__).parent / "schema.sql")
    sql = schema_path.read_text()
    with _engine.begin() as conn:
        for stmt in _split_sql(sql):
            if stmt.strip():
                conn.execute(text(stmt))
        _seed_default_tasks(conn)


def _split_sql(sql: str) -> Iterable[str]:
    for chunk in sql.split(";"):
        yield chunk


def _seed_default_tasks(conn) -> None:
    count = conn.execute(text("SELECT COUNT(*) FROM tasks")).scalar_one()
    if count == 0:
        for label, order in _DEFAULT_TASKS:
            conn.execute(
                text(
                    "INSERT INTO tasks (label, display_order, active) "
                    "VALUES (:label, :order, 1)"
                ),
                {"label": label, "order": order},
            )


# --------------------------------------------------------------------------- #
# Roster
# --------------------------------------------------------------------------- #

def list_kids() -> list[dict]:
    with _engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, name, display_order "
                "FROM kids ORDER BY display_order, id"
            )
        ).mappings().all()
    return [dict(r) for r in rows]


def list_tasks(include_inactive: bool = False) -> list[dict]:
    q = "SELECT id, label, display_order, active FROM tasks"
    if not include_inactive:
        q += " WHERE active = 1"
    q += " ORDER BY display_order, id"
    with _engine.connect() as conn:
        rows = conn.execute(text(q)).mappings().all()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Daily state
# --------------------------------------------------------------------------- #

def get_day(kid_id: int, day: date) -> dict:
    """Return {'completions': {task_id: completed_at}, 'ninja': {...} | None}."""
    with _engine.connect() as conn:
        comp_rows = conn.execute(
            text(
                "SELECT task_id, completed_at FROM task_completions "
                "WHERE kid_id = :kid AND day = :day"
            ),
            {"kid": kid_id, "day": day.isoformat()},
        ).mappings().all()
        ninja_row = conn.execute(
            text(
                "SELECT maintained, note FROM ninja_mode_days "
                "WHERE kid_id = :kid AND day = :day"
            ),
            {"kid": kid_id, "day": day.isoformat()},
        ).mappings().first()

    completions = {r["task_id"]: r["completed_at"] for r in comp_rows}
    ninja = None
    if ninja_row is not None:
        ninja = {
            "maintained": bool(ninja_row["maintained"]),
            "note": ninja_row["note"],
        }
    return {"completions": completions, "ninja": ninja}


def tick_task(kid_id: int, task_id: int, day: date) -> None:
    """Mark a task complete for a kid on a given day. Idempotent."""
    with _engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO task_completions (kid_id, task_id, day, completed_at) "
                "VALUES (:kid, :task, :day, :ts) "
                "ON CONFLICT (kid_id, task_id, day) DO NOTHING"
            ),
            {
                "kid": kid_id,
                "task": task_id,
                "day": day.isoformat(),
                "ts": datetime.now().isoformat(timespec="seconds"),
            },
        )


def untick_task(kid_id: int, task_id: int, day: date) -> None:
    """Remove a completion row. Idempotent."""
    with _engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM task_completions "
                "WHERE kid_id = :kid AND task_id = :task AND day = :day"
            ),
            {"kid": kid_id, "task": task_id, "day": day.isoformat()},
        )


# --------------------------------------------------------------------------- #
# Ninja Mode
# --------------------------------------------------------------------------- #

def set_ninja_mode(
    kid_id: int,
    day: date,
    maintained: bool,
    note: str | None = None,
) -> None:
    """Upsert a ninja-mode row for a given kid on a given day."""
    with _engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ninja_mode_days (kid_id, day, maintained, note) "
                "VALUES (:kid, :day, :m, :note) "
                "ON CONFLICT (kid_id, day) DO UPDATE SET "
                "  maintained = excluded.maintained, "
                "  note = excluded.note"
            ),
            {
                "kid": kid_id,
                "day": day.isoformat(),
                "m": 1 if maintained else 0,
                "note": note,
            },
        )


def clear_ninja_mode(kid_id: int, day: date) -> None:
    """Remove the ninja-mode row for a given kid on a given day. Idempotent."""
    with _engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM ninja_mode_days "
                "WHERE kid_id = :kid AND day = :day"
            ),
            {"kid": kid_id, "day": day.isoformat()},
        )


# --------------------------------------------------------------------------- #
# Derived eligibility (pure functions over tick tables)
# --------------------------------------------------------------------------- #

def daily_screen_earned(kid_id: int, day: date) -> bool:
    """True iff every active task has been ticked for this kid on this day."""
    tasks = list_tasks()
    if not tasks:
        return False
    state = get_day(kid_id, day)
    return all(t["id"] in state["completions"] for t in tasks)


def week_days_complete(kid_id: int, week_start_day: date) -> int:
    """Count of days in the Mon..Sun week where all active tasks were ticked."""
    return sum(
        1
        for i in range(7)
        if daily_screen_earned(kid_id, week_start_day + timedelta(days=i))
    )


def week_complete(kid_id: int, week_start_day: date) -> bool:
    """True iff every day of the week has all active tasks ticked."""
    return week_days_complete(kid_id, week_start_day) == 7


def ninja_streak_intact(kid_id: int, week_start_day: date) -> bool:
    """True iff the week has at least one ninja day and all are maintained.

    A week with no ninja days returns False — there's no bonus to earn if
    Ninja Mode was never activated.
    """
    week_end = week_start_day + timedelta(days=7)
    with _engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT maintained FROM ninja_mode_days "
                "WHERE kid_id = :kid AND day >= :start AND day < :end"
            ),
            {
                "kid": kid_id,
                "start": week_start_day.isoformat(),
                "end": week_end.isoformat(),
            },
        ).all()
    if not rows:
        return False
    return all(r[0] == 1 for r in rows)


# --------------------------------------------------------------------------- #
# Rewards ledger
# --------------------------------------------------------------------------- #

def reward_claimed(kid_id: int, reward_type: str, period_start: date) -> bool:
    with _engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT 1 FROM rewards_claimed "
                "WHERE kid_id = :k AND reward_type = :t AND period_start = :d"
            ),
            {"k": kid_id, "t": reward_type, "d": period_start.isoformat()},
        ).first()
    return row is not None


def claim_reward(kid_id: int, reward_type: str, period_start: date) -> bool:
    """Record a reward claim. Returns False if already claimed."""
    if reward_claimed(kid_id, reward_type, period_start):
        return False
    with _engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO rewards_claimed "
                "(kid_id, reward_type, period_start, claimed_at) "
                "VALUES (:k, :t, :d, :ts)"
            ),
            {
                "k": kid_id,
                "t": reward_type,
                "d": period_start.isoformat(),
                "ts": datetime.now().isoformat(timespec="seconds"),
            },
        )
    return True
