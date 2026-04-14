"""Streamlit UI for the House Rules app — Phase 2.

Minimal working tick loop:
- Day picker (sidebar, defaults to today)
- Two columns, one per kid
- Checkboxes for each active task, pre-populated from the DB
- Progress bar per kid
- Refresh button to pull in ticks made by the other parent on another device

No rewards, no Ninja Mode, no PIN gate yet — those land in Phase 3 / 4.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

import db

st.set_page_config(page_title="House Rules", page_icon="🏡", layout="wide")

# Idempotent; cheap enough to call on every script run.
db.init_db()


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #

with st.sidebar:
    st.header("🏡 House Rules")
    selected_day: date = st.date_input("Day", value=date.today())

    st.caption(
        "Tick boxes as each rule is done. Ticks save immediately. "
        "If another parent has made changes on their device, click Refresh."
    )

    if st.button("🔄 Refresh", use_container_width=True):
        # Wipe our checkbox widget state so the next render re-seeds from DB.
        for k in list(st.session_state.keys()):
            if k.startswith("tick_"):
                del st.session_state[k]
        st.rerun()


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

st.title("🏡 House Rules")
st.caption(f"**{selected_day.strftime('%A, %d %B %Y')}**")

kids = db.list_kids()
tasks = db.list_tasks()

if not kids:
    st.error("No kids found in the database. Check schema.sql seed rows.")
    st.stop()
if not tasks:
    st.error("No active tasks found. Check schema.sql seed rows.")
    st.stop()


def _render_kid(kid: dict, day: date, tasks: list[dict]) -> None:
    """Render one kid's column: name, progress bar, and task checkboxes."""
    day_state = db.get_day(kid["id"], day)
    completions: dict[int, str] = day_state["completions"]

    done = len(completions)
    total = len(tasks)

    st.subheader(kid["name"])
    st.progress(done / total if total else 0.0, text=f"{done} / {total} done")

    for task in tasks:
        is_done = task["id"] in completions
        key = f"tick_{kid['id']}_{task['id']}_{day.isoformat()}"

        # Seed session_state from DB only on first render of this key.
        # Afterwards Streamlit owns the widget state and will feed our
        # on_change callback with the user's toggles.
        if key not in st.session_state:
            st.session_state[key] = is_done

        # Bind identifiers at function-creation time via default args, so the
        # callback uses *this* iteration's values rather than whatever the
        # loop variables end up pointing to.
        def _on_change(
            _kid_id: int = kid["id"],
            _task_id: int = task["id"],
            _day: date = day,
            _key: str = key,
        ) -> None:
            if st.session_state[_key]:
                db.tick_task(_kid_id, _task_id, _day)
            else:
                db.untick_task(_kid_id, _task_id, _day)

        st.checkbox(task["label"], key=key, on_change=_on_change)


cols = st.columns(len(kids))
for col, kid in zip(cols, kids):
    with col:
        _render_kid(kid, selected_day, tasks)
