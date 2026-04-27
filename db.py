"""Persistence layer for the House Rules app.

All database access goes through this module. app.py must not import
SQLAlchemy directly. Functions take and return plain Python types
(dicts, lists, primitives) so the storage backend is swappable
(SQLite locally, Postgres/Supabase on the cloud) by changing only
DATABASE_URL.

Secrets (DATABASE_URL, etc.) are read from Streamlit's st.secrets
first (used by Streamlit Community Cloud) and fall back to .env /
os.environ for local development.
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


def _get_secret(key: str, default: str | None = None) -> str | None:
    """Read a secret from st.secrets (Streamlit Cloud) or os.environ (local).

    st.secrets is only available when running inside Streamlit, so we
    catch broadly to keep db.py importable during tests.
    """
    try:
        import streamlit as st  # noqa: F811

        if hasattr(st, "secrets") and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)

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
    url = url or _get_secret("DATABASE_URL", _DEFAULT_URL)
    is_postgres = url.startswith("postgresql") or url.startswith("postgres")

    if not is_postgres:
        db_path = url.split("sqlite:///", 1)[-1]
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # Supabase requires SSL. Pass it as a connect_arg so it works whether or
    # not ?sslmode=require is already appended to the connection string.
    connect_args = {"sslmode": "require"} if is_postgres else {}
    engine = create_engine(url, future=True, connect_args=connect_args)

    if not is_postgres:
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


def check_connection() -> tuple[bool, str]:
    """Ping the database. Returns (ok, error_message).

    Runs a trivial SELECT so we get a meaningful error early — before any
    user action — rather than a raw SQLAlchemy traceback mid-session.
    """
    try:
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


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
    """Apply schema DDL and ensure default tasks exist. Idempotent.

    Picks schema_postgres.sql when the engine points at Postgres,
    schema.sql for SQLite. An explicit `schema_path` overrides both
    (used by tests).
    """
    if schema_path is None:
        dialect = _engine.dialect.name
        filename = "schema_postgres.sql" if dialect == "postgresql" else "schema.sql"
        schema_path = Path(__file__).parent / filename
    else:
        schema_path = Path(schema_path)
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
    """True iff the week has at least one ninja day and all are maintained."""
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


# --------------------------------------------------------------------------- #
# Admin (PIN-gated in the UI; no auth enforcement at this layer)
# --------------------------------------------------------------------------- #

def reset_day(kid_id: int, day: date) -> None:
    """Delete all task completions and any ninja row for (kid, day). Idempotent."""
    with _engine.begin() as conn:
        conn.execute(
            text("DELETE FROM task_completions WHERE kid_id = :k AND day = :d"),
            {"k": kid_id, "d": day.isoformat()},
        )
        conn.execute(
            text("DELETE FROM ninja_mode_days WHERE kid_id = :k AND day = :d"),
            {"k": kid_id, "d": day.isoformat()},
        )


def revoke_reward(kid_id: int, reward_type: str, period_start: date) -> bool:
    """Delete a reward claim. Returns True iff a row was deleted."""
    with _engine.begin() as conn:
        result = conn.execute(
            text(
                "DELETE FROM rewards_claimed "
                "WHERE kid_id = :k AND reward_type = :t AND period_start = :d"
            ),
            {"k": kid_id, "t": reward_type, "d": period_start.isoformat()},
        )
    return result.rowcount > 0


def add_task(label: str) -> int:
    """Append a new active task at the end. Returns its id."""
    with _engine.begin() as conn:
        max_order = conn.execute(
            text("SELECT COALESCE(MAX(display_order), 0) FROM tasks")
        ).scalar_one()
        row = conn.execute(
            text(
                "INSERT INTO tasks (label, display_order, active) "
                "VALUES (:label, :order, 1) RETURNING id"
            ),
            {"label": label, "order": max_order + 1},
        ).first()
        return int(row[0])


def rename_task(task_id: int, new_label: str) -> None:
    with _engine.begin() as conn:
        conn.execute(
            text("UPDATE tasks SET label = :l WHERE id = :i"),
            {"l": new_label, "i": task_id},
        )


def deactivate_task(task_id: int) -> None:
    """Hide a task from the tick view. History is preserved."""
    with _engine.begin() as conn:
        conn.execute(
            text("UPDATE tasks SET active = 0 WHERE id = :i"),
            {"i": task_id},
        )


def reactivate_task(task_id: int) -> None:
    with _engine.begin() as conn:
        conn.execute(
            text("UPDATE tasks SET active = 1 WHERE id = :i"),
            {"i": task_id},
        )


def reorder_tasks(order: list[int]) -> None:
    """Reassign display_order from the given sequence of task ids.

    Position 0 in the list becomes display_order 1, position 1 becomes 2, etc.
    Task ids not present in `order` are left untouched.
    """
    with _engine.begin() as conn:
        for i, task_id in enumerate(order, start=1):
            conn.execute(
                text("UPDATE tasks SET display_order = :o WHERE id = :i"),
                {"o": i, "i": task_id},
            )


def delete_task(task_id: int) -> None:
    """Hard-delete a task and all its completion history.

    The FK on task_completions has ON DELETE CASCADE, so all completion
    rows for this task are removed automatically. Use deactivate_task
    instead if you want to preserve history.
    """
    with _engine.begin() as conn:
        conn.execute(
            text("DELETE FROM tasks WHERE id = :i"),
            {"i": task_id},
        )


def task_has_history(task_id: int) -> bool:
    """True iff any completion rows exist for this task."""
    with _engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM task_completions WHERE task_id = :i"),
            {"i": task_id},
        ).scalar_one()
    return count > 0


# --------------------------------------------------------------------------- #
# Aggregates for the history view
# --------------------------------------------------------------------------- #

def get_week_summary(kid_id: int, week_start_day: date) -> list[dict]:
    """Return 7 per-day dicts for the Mon..Sun week starting week_start_day.

    Each dict: {
        "day": date,
        "done": int,           # completions against currently-active tasks
        "total": int,          # count of currently-active tasks
        "all_done": bool,      # convenience: done == total and total > 0
        "ninja": dict | None,  # {"maintained": bool, "note": str | None} or None
    }

    Uses two window queries (completions, ninja) rather than 7 x get_day, so
    the history view stays snappy even with many weeks rendered.
    """
    tasks = list_tasks()
    active_ids = {t["id"] for t in tasks}
    total = len(tasks)
    week_end = week_start_day + timedelta(days=7)

    with _engine.connect() as conn:
        comp_rows = conn.execute(
            text(
                "SELECT day, task_id FROM task_completions "
                "WHERE kid_id = :k AND day >= :s AND day < :e"
            ),
            {
                "k": kid_id,
                "s": week_start_day.isoformat(),
                "e": week_end.isoformat(),
            },
        ).all()
        ninja_rows = conn.execute(
            text(
                "SELECT day, maintained, note FROM ninja_mode_days "
                "WHERE kid_id = :k AND day >= :s AND day < :e"
            ),
            {
                "k": kid_id,
                "s": week_start_day.isoformat(),
                "e": week_end.isoformat(),
            },
        ).mappings().all()

    # Only count completions against tasks that are still active. Completions
    # against deactivated tasks are preserved in the DB but excluded here so
    # the "done/total" denominator stays coherent with the current task list.
    done_by_day: dict[str, int] = {}
    for day_str, task_id in comp_rows:
        if task_id in active_ids:
            done_by_day[day_str] = done_by_day.get(day_str, 0) + 1

    ninja_by_day = {
        r["day"]: {"maintained": bool(r["maintained"]), "note": r["note"]}
        for r in ninja_rows
    }

    summary: list[dict] = []
    for i in range(7):
        d = week_start_day + timedelta(days=i)
        key = d.isoformat()
        done = done_by_day.get(key, 0)
        summary.append(
            {
                "day": d,
                "done": done,
                "total": total,
                "all_done": total > 0 and done == total,
                "ninja": ninja_by_day.get(key),
            }
        )
    return summary


def list_reward_claims(
    kid_id: int, period_start: date, period_end: date
) -> list[dict]:
    """List reward claims with period_start in [period_start, period_end).

    Used by the weekly history view to show which treats / screen days were
    claimed. Ordered by period_start then claimed_at.
    """
    with _engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT reward_type, period_start, claimed_at "
                "FROM rewards_claimed "
                "WHERE kid_id = :k AND period_start >= :s AND period_start < :e "
                "ORDER BY period_start, claimed_at"
            ),
            {
                "k": kid_id,
                "s": period_start.isoformat(),
                "e": period_end.isoformat(),
            },
        ).mappings().all()
    return [dict(r) for r in rows]
