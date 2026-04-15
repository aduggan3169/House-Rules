"""Streamlit UI for the House Rules app — Phase 4.

What's new vs Phase 3:
- Parent PIN gate in the sidebar (bcrypt-checked against PARENT_PIN_HASH)
- Admin panel (main page, PIN-gated) with three tabs:
    - Reset day: clear ticks and ninja for a kid/day
    - Revoke claim: delete a row from the rewards ledger
    - Manage tasks: add, rename, reorder, deactivate, reactivate

Still deferred:
- Weekly history heatmap and theming polish (Phase 5)
- Cloud migration (Phase 6)
"""

from __future__ import annotations

from datetime import date

import streamlit as st

import auth
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
        for k in list(st.session_state.keys()):
            if k.startswith(("tick_", "ninja_")):
                del st.session_state[k]
        st.rerun()

    st.divider()

    # Admin unlock / lock
    if not auth.pin_is_configured():
        st.caption("⚙️ Admin disabled. Set `PARENT_PIN_HASH` in `.env` to enable.")
    elif st.session_state.get("admin"):
        st.success("🔓 Admin unlocked")
        if st.button("Lock", use_container_width=True):
            st.session_state["admin"] = False
            st.rerun()
    else:
        with st.form("pin_form", clear_on_submit=True):
            pin = st.text_input("Parent PIN", type="password")
            submitted = st.form_submit_button("Unlock", use_container_width=True)
            if submitted:
                if auth.verify_pin(pin):
                    st.session_state["admin"] = True
                    st.rerun()
                else:
                    st.error("Incorrect PIN")


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
    st.error("No active tasks found. Use Admin → Manage tasks to add some.")
    # We don't st.stop here because unlocking admin still needs to be possible.


# Fire balloons once per (kid, day) on the transition from incomplete to
# complete. Seed the flag to "already celebrated" when the user opens a day
# that's already complete, so we don't spam confetti just for viewing it.
if tasks:
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
# Per-kid renderers
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
    on_key = f"ninja_on_{kid['id']}_{day.isoformat()}"
    if on_key not in st.session_state:
        st.session_state[on_key] = ninja is not None

    def _on_toggle(_kid_id: int = kid["id"], _day: date = day, _key: str = on_key) -> None:
        if st.session_state[_key]:
            db.set_ninja_mode(_kid_id, _day, maintained=True, note=None)
        else:
            db.clear_ninja_mode(_kid_id, _day)
            for suffix in ("maint_", "note_"):
                k = f"ninja_{suffix}{_kid_id}_{_day.isoformat()}"
                st.session_state.pop(k, None)

    st.toggle("🥷 Ninja Mode", key=on_key, on_change=_on_toggle)

    if not st.session_state[on_key]:
        return

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
    is_earned = db.daily_screen_earned(kid["id"], day) if tasks else False

    st.subheader(kid["name"])
    _render_tasks(kid, day, tasks, completions)
    st.divider()
    _render_daily_reward(kid, day, is_earned)
    _render_ninja_controls(kid, day, ninja)
    st.divider()
    _render_weekly_summary(kid, week_start_day)


if tasks:
    cols = st.columns(len(kids))
    for col, kid in zip(cols, kids):
        with col:
            _render_kid(kid, selected_day, tasks, week_start_day)


# --------------------------------------------------------------------------- #
# Admin panel (PIN-gated)
# --------------------------------------------------------------------------- #

_REWARD_LABELS = {
    db.REWARD_DAILY_SCREEN: "Daily screen time",
    db.REWARD_WEEKLY_TREAT: "Weekly treat",
    db.REWARD_NINJA_TREAT: "Ninja treat",
}


def _kid_name(kids: list[dict], kid_id: int) -> str:
    return next(k["name"] for k in kids if k["id"] == kid_id)


def _clear_day_widget_state(day: date) -> None:
    """Remove checkbox/ninja widget state for `day` so the UI re-reads the DB."""
    day_iso = day.isoformat()
    for k in list(st.session_state.keys()):
        if day_iso in k and k.startswith(("tick_", "ninja_")):
            del st.session_state[k]


def _render_reset_day(kids: list[dict], default_day: date) -> None:
    st.caption(
        "Clear every tick and any Ninja Mode row for a kid on a specific day. "
        "Reward claims on that day are not affected — use the Revoke tab for those."
    )

    kid_id = st.selectbox(
        "Kid",
        options=[k["id"] for k in kids],
        format_func=lambda i: _kid_name(kids, i),
        key="admin_reset_kid",
    )
    day = st.date_input("Day", value=default_day, key="admin_reset_day")

    if st.button("Reset this day", type="secondary", key="admin_reset_btn"):
        db.reset_day(kid_id, day)
        _clear_day_widget_state(day)
        st.toast(f"Reset {_kid_name(kids, kid_id)} for {day.isoformat()}")
        st.rerun()


def _render_revoke_claim(
    kids: list[dict], selected_day: date, week_start_day: date
) -> None:
    st.caption(
        "Delete a reward claim from the ledger. Eligibility recomputes "
        "automatically from ticks — this just lets you undo a mistaken press."
    )

    kid_id = st.selectbox(
        "Kid",
        options=[k["id"] for k in kids],
        format_func=lambda i: _kid_name(kids, i),
        key="admin_revoke_kid",
    )
    reward_type = st.selectbox(
        "Reward",
        options=list(_REWARD_LABELS.keys()),
        format_func=lambda t: _REWARD_LABELS[t],
        key="admin_revoke_type",
    )
    default_period = (
        selected_day if reward_type == db.REWARD_DAILY_SCREEN else week_start_day
    )
    period = st.date_input("Period start", value=default_period, key="admin_revoke_period")

    exists = db.reward_claimed(kid_id, reward_type, period)
    if exists:
        st.info("Claim exists and can be revoked.")
    else:
        st.caption("No claim recorded for this selection.")

    if st.button(
        "Revoke claim",
        type="secondary",
        disabled=not exists,
        key="admin_revoke_btn",
    ):
        if db.revoke_reward(kid_id, reward_type, period):
            st.toast("Claim revoked")
            st.rerun()


def _render_manage_tasks() -> None:
    st.caption(
        "Add, rename, reorder, or deactivate tasks. Deactivated tasks are hidden "
        "from the tick view but their history is preserved."
    )

    active = db.list_tasks(include_inactive=False)
    all_tasks = db.list_tasks(include_inactive=True)
    inactive = [t for t in all_tasks if not t["active"]]

    st.markdown("**Active tasks**")
    if not active:
        st.caption("_None. Add one below._")

    for idx, task in enumerate(active):
        cols = st.columns([6, 1, 1, 2])
        with cols[0]:
            rename_key = f"admin_rename_{task['id']}"
            if rename_key not in st.session_state:
                st.session_state[rename_key] = task["label"]
            new_label = st.text_input(
                f"Task {task['id']}",
                label_visibility="collapsed",
                key=rename_key,
            )
            if new_label.strip() and new_label != task["label"]:
                db.rename_task(task["id"], new_label.strip())
                st.rerun()
        with cols[1]:
            if st.button("↑", key=f"admin_up_{task['id']}", disabled=(idx == 0)):
                order = [t["id"] for t in active]
                order[idx - 1], order[idx] = order[idx], order[idx - 1]
                db.reorder_tasks(order)
                st.rerun()
        with cols[2]:
            if st.button(
                "↓",
                key=f"admin_down_{task['id']}",
                disabled=(idx == len(active) - 1),
            ):
                order = [t["id"] for t in active]
                order[idx], order[idx + 1] = order[idx + 1], order[idx]
                db.reorder_tasks(order)
                st.rerun()
        with cols[3]:
            if st.button(
                "Deactivate",
                key=f"admin_deact_{task['id']}",
                type="secondary",
                use_container_width=True,
            ):
                db.deactivate_task(task["id"])
                st.rerun()

    if inactive:
        st.markdown("**Inactive tasks**")
        for task in inactive:
            cols = st.columns([6, 2])
            with cols[0]:
                st.text(task["label"])
            with cols[1]:
                if st.button(
                    "Reactivate",
                    key=f"admin_react_{task['id']}",
                    use_container_width=True,
                ):
                    db.reactivate_task(task["id"])
                    st.rerun()

    st.markdown("**Add a new task**")
    with st.form("admin_add_task", clear_on_submit=True):
        new_label = st.text_input("Label", placeholder="e.g. Make the bed")
        submitted = st.form_submit_button("Add task")
        if submitted and new_label.strip():
            db.add_task(new_label.strip())
            st.rerun()


def _render_admin(
    kids: list[dict], selected_day: date, week_start_day: date
) -> None:
    tab_reset, tab_revoke, tab_tasks = st.tabs(
        ["Reset day", "Revoke claim", "Manage tasks"]
    )
    with tab_reset:
        _render_reset_day(kids, selected_day)
    with tab_revoke:
        _render_revoke_claim(kids, selected_day, week_start_day)
    with tab_tasks:
        _render_manage_tasks()


if st.session_state.get("admin"):
    st.divider()
    with st.expander("⚙️ Admin", expanded=True):
        _render_admin(kids, selected_day, week_start_day)
