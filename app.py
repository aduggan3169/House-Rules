"""Streamlit UI for the House Rules app — Phase 3.

What's new vs Phase 2:
- Daily screen-time reward with claim button and confetti
- Weekly progress (X/7 days) with weekly-treat claim button
- Ninja Mode toggle per kid per day, with maintained toggle + note
- Ninja weekly treat, claimable when the streak is intact
- Balloons fire on transition from incomplete → complete, and on each claim

Still deferred:
- PIN gate / parent admin panel (Phase 4)
- Weekly history heatmap and polish (Phase 5)
"""

from __future__ import annotations

from datetime import date

import streamlit as st

import db

st.set_page_config(page_title="House Rules", page_icon="🏡", layout="wide")

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
        # Wipe widget state so every checkbox/toggle re-seeds from the DB.
        for k in list(st.session_state.keys()):
            if k.startswith(("tick_", "ninja_")):
                del st.session_state[k]
        st.rerun()


# --------------------------------------------------------------------------- #
# Main header
# --------------------------------------------------------------------------- #

st.title("🏡 House Rules")
st.caption(f"**{selected_day.strftime('%A, %d %B %Y')}**")

kids = db.list_kids()
tasks = db.list_tasks()
week_start_day = db.week_start(selected_day)

if not kids:
    st.error("No kids found in the database. Check schema.sql seed rows.")
    st.stop()
if not tasks:
    st.error("No active tasks found. Check schema.sql seed rows.")
    st.stop()


# Fire balloons once per (kid, day) on the transition from incomplete to
# complete. Seed the flag to "already celebrated" when the user opens a day
# that's already complete, so we don't spam confetti just for viewing it.
for kid in kids:
    flag_key = f"celebrated_{kid['id']}_{selected_day.isoformat()}"
    currently_complete = db.daily_screen_earned(kid["id"], selected_day)
    if flag_key not in st.session_state:
        st.session_state[flag_key] = currently_complete
    elif currently_complete and not st.session_state[flag_key]:
        st.balloons()
        st.session_state[flag_key] = True
    elif not currently_complete:
        st.session_state[flag_key] = False


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #

def _render_tasks(kid: dict, day: date, tasks: list[dict], completions: dict) -> None:
    total = len(tasks)
    done = len(completions)
    st.progress(done / total if total else 0.0, text=f"{done} / {total} done today")

    for task in tasks:
        key = f"tick_{kid['id']}_{task['id']}_{day.isoformat()}"
        if key not in st.session_state:
            st.session_state[key] = task["id"] in completions

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


def _render_daily_reward(kid: dict, day: date, is_earned: bool) -> None:
    claimed = db.reward_claimed(kid["id"], db.REWARD_DAILY_SCREEN, day)

    if claimed:
        st.success("🎮 Screen time claimed")
    elif is_earned:
        if st.button(
            "🎮 Claim screen time",
            key=f"claim_daily_{kid['id']}_{day.isoformat()}",
            type="primary",
            use_container_width=True,
        ):
            db.claim_reward(kid["id"], db.REWARD_DAILY_SCREEN, day)
            st.balloons()
            st.rerun()
    else:
        st.caption("🎮 Complete all tasks to earn screen time")


def _render_ninja_controls(kid: dict, day: date, ninja: dict | None) -> None:
    """Ninja Mode: toggle + maintained flag + optional note."""
    on_key = f"ninja_on_{kid['id']}_{day.isoformat()}"
    if on_key not in st.session_state:
        st.session_state[on_key] = ninja is not None

    def _on_toggle(_kid_id: int = kid["id"], _day: date = day, _key: str = on_key) -> None:
        if st.session_state[_key]:
            db.set_ninja_mode(_kid_id, _day, maintained=True, note=None)
        else:
            db.clear_ninja_mode(_kid_id, _day)
            # Clear dependent widget state so the next activation starts clean.
            for suffix in ("maint_", "note_"):
                k = f"ninja_{suffix}{_kid_id}_{_day.isoformat()}"
                st.session_state.pop(k, None)

    st.toggle("🥷 Ninja Mode", key=on_key, on_change=_on_toggle)

    if not st.session_state[on_key]:
        return

    # Only render the detail controls when Ninja Mode is active.
    maint_key = f"ninja_maint_{kid['id']}_{day.isoformat()}"
    note_key = f"ninja_note_{kid['id']}_{day.isoformat()}"
    if maint_key not in st.session_state:
        st.session_state[maint_key] = bool(ninja["maintained"]) if ninja else True
    if note_key not in st.session_state:
        st.session_state[note_key] = (ninja or {}).get("note") or ""

    def _on_detail_change(
        _kid_id: int = kid["id"],
        _day: date = day,
        _mk: str = maint_key,
        _nk: str = note_key,
    ) -> None:
        db.set_ninja_mode(
            _kid_id,
            _day,
            maintained=st.session_state[_mk],
            note=(st.session_state[_nk] or None),
        )

    st.toggle("Maintained", key=maint_key, on_change=_on_detail_change)
    st.text_input(
        "Note",
        key=note_key,
        placeholder="e.g. Sunday lunch at Nana's",
        on_change=_on_detail_change,
    )


def _render_weekly_summary(kid: dict, week_start_day: date) -> None:
    days_done = db.week_days_complete(kid["id"], week_start_day)
    st.markdown(f"**🍭 Weekly treat** — {days_done}/7 days complete")

    if days_done == 7:
        claimed = db.reward_claimed(kid["id"], db.REWARD_WEEKLY_TREAT, week_start_day)
        if claimed:
            st.success("🍭 Weekly treat claimed")
        else:
            if st.button(
                "🍭 Claim weekly treat",
                key=f"claim_weekly_{kid['id']}_{week_start_day.isoformat()}",
                type="primary",
                use_container_width=True,
            ):
                db.claim_reward(kid["id"], db.REWARD_WEEKLY_TREAT, week_start_day)
                st.balloons()
                st.rerun()

    if db.ninja_streak_intact(kid["id"], week_start_day):
        claimed = db.reward_claimed(kid["id"], db.REWARD_NINJA_TREAT, week_start_day)
        if claimed:
            st.success("🥷 Ninja treat claimed")
        else:
            if st.button(
                "🥷 Claim ninja treat",
                key=f"claim_ninja_{kid['id']}_{week_start_day.isoformat()}",
                type="primary",
                use_container_width=True,
            ):
                db.claim_reward(kid["id"], db.REWARD_NINJA_TREAT, week_start_day)
                st.balloons()
                st.rerun()


def _render_kid(kid: dict, day: date, tasks: list[dict], week_start_day: date) -> None:
    day_state = db.get_day(kid["id"], day)
    completions = day_state["completions"]
    ninja = day_state["ninja"]
    is_earned = db.daily_screen_earned(kid["id"], day)

    st.subheader(kid["name"])
    _render_tasks(kid, day, tasks, completions)
    st.divider()
    _render_daily_reward(kid, day, is_earned)
    _render_ninja_controls(kid, day, ninja)
    st.divider()
    _render_weekly_summary(kid, week_start_day)


cols = st.columns(len(kids))
for col, kid in zip(cols, kids):
    with col:
        _render_kid(kid, selected_day, tasks, week_start_day)
