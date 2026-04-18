"""Streamlit UI for the House Rules app — Phase 5 (mobile-first polish).

Phase 5 adds:
- Kid-friendly, mobile-first CSS theme (big touch targets, rounded cards,
  gradient progress bar, playful buttons).
- Top-level Today / History tabs; per-kid nested tabs inside each, so a phone
  user gets a full-width view per kid with a single tap.
- Main-area day selector with a "📅 Today" reset button (sidebar reserved
  for Refresh and Admin, which parents rarely need).
- Per-kid colour-coded names using Streamlit's colour markdown.
- History view: week navigator + styled heatmap + weekly rewards ledger.

Still deferred:
- Cloud migration (Phase 6): Supabase Postgres + Streamlit Community Cloud.
"""

from __future__ import annotations

APP_VERSION = "1.0.0"

from datetime import date, timedelta

import pandas as pd
import streamlit as st

import auth
import db

st.set_page_config(page_title="House Rules", page_icon="🏡", layout="centered")

db.init_db()


# --------------------------------------------------------------------------- #
# CSS — kid-friendly + mobile-first
# --------------------------------------------------------------------------- #

_CSS = """
<style>
/* ----- Type + rhythm ----- */
html, body, .stApp, [class*="st-"] {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display",
                 "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
}

/* Reclaim vertical space on phones */
.stApp [data-testid="stMainBlockContainer"],
.stApp .block-container,
section.main > div.block-container {
    padding-top: 1.25rem !important;
    padding-bottom: 3rem !important;
    max-width: 720px !important;
}

/* ----- Title — soft gradient ----- */
h1 {
    font-size: 2rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.02em;
    background: linear-gradient(135deg, #6366f1, #ec4899, #f59e0b);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0.5rem !important;
}
h2 { font-size: 1.5rem !important; font-weight: 700 !important; }
h3 { font-size: 1.3rem !important; font-weight: 700 !important; margin: 0.5rem 0 0.75rem !important; }

/* ----- Checkboxes — big, soft, tappable ----- */
[data-testid="stCheckbox"] {
    background: #fafafa;
    border: 2px solid #e5e7eb;
    border-radius: 18px;
    padding: 14px 18px;
    margin: 8px 0;
    transition: all 0.2s ease;
}
[data-testid="stCheckbox"]:hover {
    border-color: #c7d2fe;
    background: #f5f3ff;
}
[data-testid="stCheckbox"] label {
    font-size: 1.15rem !important;
    font-weight: 500 !important;
    color: #1f2937 !important;
    cursor: pointer !important;
    width: 100%;
}
[data-testid="stCheckbox"] label > div[data-baseweb="checkbox"] > div:first-child {
    transform: scale(1.4);
    margin-right: 6px;
}
/* Green-wash on check. :has() is supported in all modern mobile browsers. */
[data-testid="stCheckbox"]:has(input:checked) {
    background: linear-gradient(135deg, #ecfdf5, #d1fae5);
    border-color: #6ee7b7;
}
[data-testid="stCheckbox"]:has(input:checked) label p {
    text-decoration: line-through;
    text-decoration-color: #10b981;
    text-decoration-thickness: 2px;
    color: #065f46 !important;
}

/* ----- Progress bar — chunky, animated gradient ----- */
[data-testid="stProgress"] > div > div {
    height: 16px !important;
    border-radius: 999px;
    background: #e5e7eb;
    overflow: hidden;
}
[data-testid="stProgress"] > div > div > div > div {
    background: linear-gradient(90deg, #60a5fa, #a78bfa, #34d399) !important;
    border-radius: 999px;
    background-size: 200% 100%;
    animation: hr-shimmer 3s ease-in-out infinite;
}
@keyframes hr-shimmer {
    0%, 100% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
}

/* ----- Buttons — rounded pills; primary pops ----- */
[data-testid="stButton"] > button,
[data-testid="stFormSubmitButton"] > button {
    border-radius: 999px !important;
    font-weight: 600 !important;
    padding: 0.55rem 1.2rem !important;
    border: 2px solid #e5e7eb !important;
    transition: all 0.15s ease !important;
}
[data-testid="stButton"] > button:hover:not(:disabled),
[data-testid="stFormSubmitButton"] > button:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.08);
}
[data-testid="stButton"] > button[kind="primary"],
[data-testid="stFormSubmitButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #6366f1, #a855f7) !important;
    border: none !important;
    color: white !important;
    font-size: 1.1rem !important;
    padding: 0.85rem 1.5rem !important;
    box-shadow: 0 4px 14px rgba(99, 102, 241, 0.35) !important;
}
[data-testid="stButton"] > button[kind="primary"]:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(99, 102, 241, 0.45) !important;
}

/* ----- Toggle ----- */
[data-testid="stToggle"] label {
    font-size: 1.05rem !important;
    font-weight: 500 !important;
}

/* ----- Alert boxes (success/info/warning) ----- */
[data-testid="stAlert"] {
    border-radius: 14px !important;
    font-weight: 500;
    padding: 0.9rem 1rem !important;
}

/* ----- Tabs — large, touch-friendly, coloured selection ----- */
[data-testid="stTabs"] [role="tablist"] {
    gap: 0.35rem;
    border-bottom: 2px solid #f1f5f9;
    overflow-x: auto;
    scrollbar-width: none;
}
[data-testid="stTabs"] [role="tablist"]::-webkit-scrollbar { display: none; }
[data-testid="stTabs"] [role="tab"] {
    font-size: 1.02rem !important;
    font-weight: 600 !important;
    padding: 0.7rem 1.1rem !important;
    border-radius: 12px 12px 0 0 !important;
    white-space: nowrap !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    background: #eef2ff !important;
    color: #4338ca !important;
}

/* ----- Metric cards ----- */
[data-testid="stMetric"] {
    background: #f8fafc;
    border-radius: 14px;
    padding: 0.75rem 1rem;
    border: 1px solid #f1f5f9;
}
[data-testid="stMetricValue"] {
    font-size: 1.75rem !important;
    font-weight: 700 !important;
}

/* ----- Dataframe / heatmap ----- */
[data-testid="stDataFrame"] {
    border-radius: 12px;
    overflow: hidden;
    font-size: 1rem;
}

/* ----- Date input, selectbox, text input — rounded ----- */
[data-testid="stDateInput"] input,
[data-testid="stTextInput"] input,
[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
    border-radius: 14px !important;
    font-size: 1.05rem !important;
}

/* ===== Mobile tweaks ===== */
@media (max-width: 640px) {
    h1 { font-size: 1.65rem !important; }
    h3 { font-size: 1.2rem !important; }

    .stApp [data-testid="stMainBlockContainer"],
    .stApp .block-container {
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
    }

    [data-testid="stCheckbox"] {
        padding: 16px 18px;
    }
    [data-testid="stCheckbox"] label {
        font-size: 1.2rem !important;
    }

    [data-testid="stButton"] > button[kind="primary"],
    [data-testid="stFormSubmitButton"] > button[kind="primary"] {
        width: 100%;
        font-size: 1.15rem !important;
    }

    [data-testid="stMetricValue"] {
        font-size: 1.35rem !important;
    }
}
</style>
"""

st.markdown(_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Theming
# --------------------------------------------------------------------------- #

# Per-kid accent. `md_color` maps to Streamlit's colour-markdown palette:
# blue, green, orange, red, violet, gray, rainbow.
KID_THEMES: dict[str, dict] = {
    "Cillian": {"emoji": "🔵", "color": "#3b82f6", "md_color": "blue"},
    "Fionn": {"emoji": "🟢", "color": "#10b981", "md_color": "green"},
}
_DEFAULT_THEME = {"emoji": "⚪", "color": "#64748b", "md_color": "gray"}


def _theme_for(name: str) -> dict:
    return KID_THEMES.get(name, _DEFAULT_THEME)


def _tab_label(kid: dict) -> str:
    """Emoji + name, used for per-kid nested tab titles."""
    return f"{_theme_for(kid['name'])['emoji']} {kid['name']}"


_REWARD_LABELS = {
    db.REWARD_DAILY_SCREEN: "Daily screen time",
    db.REWARD_WEEKLY_TREAT: "Weekly treat",
    db.REWARD_NINJA_TREAT: "Ninja treat",
}


# --------------------------------------------------------------------------- #
# Sidebar — Refresh + Admin only. Day picker is in the main area.
# --------------------------------------------------------------------------- #

with st.sidebar:
    st.header("🏡 House Rules")

    st.caption(
        "Ticks save immediately. If another parent is ticking on their phone, "
        "tap Refresh to pull the latest."
    )

    if st.button("🔄 Refresh", use_container_width=True):
        for k in list(st.session_state.keys()):
            if k.startswith(("tick_", "ninja_")):
                del st.session_state[k]
        st.rerun()

    st.divider()

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

    st.divider()
    st.caption(f"v{APP_VERSION}")


# --------------------------------------------------------------------------- #
# Main header + day selector
# --------------------------------------------------------------------------- #

st.title("🏡 House Rules")

kids = db.list_kids()
tasks = db.list_tasks()

if not kids:
    st.error("No kids found in the database. Check schema.sql seed rows.")
    st.stop()

# Main-area day selector. Sidebar is inconvenient on a phone, so this is the
# primary control for switching days. `selected_day` lives in session_state
# so the "Today" quick-reset works cleanly.
day_col, today_col = st.columns([3, 2])
with day_col:
    selected_day: date = st.date_input(
        "Day",
        value=st.session_state.get("selected_day", date.today()),
        key="selected_day",
        label_visibility="collapsed",
    )
with today_col:
    if st.button(
        "📅 Today",
        use_container_width=True,
        disabled=(selected_day == date.today()),
    ):
        st.session_state.pop("selected_day", None)
        st.rerun()

week_start_day = db.week_start(selected_day)


# --------------------------------------------------------------------------- #
# "Today" tab — per-kid renderers (nested tabs per kid)
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
        st.success("🎮 Screen time claimed — enjoy!")
    elif is_earned:
        if st.button(
            "🎮 Claim screen time",
            key=f"claim_daily_{kid['id']}_{day.isoformat()}",
            type="primary",
            use_container_width=True,
        ):
            db.claim_reward(kid["id"], db.REWARD_DAILY_SCREEN, day)
            st.toast(f"🎮 Screen time for {kid['name']}!")
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
                st.toast(f"🍭 Weekly treat for {kid['name']}!")
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
                st.toast(f"🥷 Ninja treat for {kid['name']}!")
                st.rerun()


def _render_kid_today(kid: dict, day: date, tasks: list[dict], week_start_day: date) -> None:
    theme = _theme_for(kid["name"])
    st.markdown(f"### {theme['emoji']} :{theme['md_color']}[{kid['name']}]")

    day_state = db.get_day(kid["id"], day)
    completions = day_state["completions"]
    ninja = day_state["ninja"]
    is_earned = db.daily_screen_earned(kid["id"], day) if tasks else False

    _render_tasks(kid, day, tasks, completions)
    st.write("")  # small gap
    _render_daily_reward(kid, day, is_earned)
    _render_ninja_controls(kid, day, ninja)
    st.divider()
    _render_weekly_summary(kid, week_start_day)


def _render_today_tab(
    kids: list[dict], tasks: list[dict], day: date, week_start_day: date
) -> None:
    st.caption(f"**{day.strftime('%A, %d %B %Y')}**")

    if not tasks:
        st.warning("No active tasks. Unlock Admin → Manage tasks to add some.")
        return

    # Balloons once per (kid, day) on the transition from incomplete to
    # complete. Runs for all kids so the celebration fires regardless of
    # which nested tab is active.
    for kid in kids:
        flag_key = f"celebrated_{kid['id']}_{day.isoformat()}"
        currently_complete = db.daily_screen_earned(kid["id"], day)
        if flag_key not in st.session_state:
            st.session_state[flag_key] = currently_complete
        elif currently_complete and not st.session_state[flag_key]:
            st.balloons()
            st.session_state[flag_key] = True
        elif not currently_complete:
            st.session_state[flag_key] = False

    kid_tabs = st.tabs([_tab_label(k) for k in kids])
    for tab, kid in zip(kid_tabs, kids):
        with tab:
            _render_kid_today(kid, day, tasks, week_start_day)


# --------------------------------------------------------------------------- #
# "History" tab — weekly heatmap per kid (nested tabs per kid)
# --------------------------------------------------------------------------- #

def _heatmap_styler(summary: list[dict]) -> pd.io.formats.style.Styler:
    """Build a two-row DataFrame (Tasks, Ninja) styled as a heatmap."""
    day_labels = [s["day"].strftime("%a %d") for s in summary]
    task_values = [f"{s['done']}/{s['total']}" for s in summary]
    ninja_values = []
    for s in summary:
        if s["ninja"] is None:
            ninja_values.append("")
        elif s["ninja"]["maintained"]:
            ninja_values.append("🥷")
        else:
            ninja_values.append("💥")

    df = pd.DataFrame(
        [task_values, ninja_values],
        index=["Tasks", "Ninja"],
        columns=day_labels,
    )

    def _color_tasks(val: str) -> str:
        if "/" not in str(val):
            return ""
        try:
            done_s, total_s = val.split("/")
            done, total = int(done_s), int(total_s)
        except ValueError:
            return ""
        if total == 0:
            return ""
        pct = done / total
        if pct >= 1:
            return "background-color: #d1fae5; color: #065f46; font-weight: 700"
        if pct == 0:
            return "background-color: #fee2e2; color: #991b1b"
        return "background-color: #fef3c7; color: #92400e"

    styler = df.style
    try:
        styler = styler.map(_color_tasks, subset=pd.IndexSlice[["Tasks"], :])
    except AttributeError:  # pragma: no cover - older pandas
        styler = styler.applymap(_color_tasks, subset=pd.IndexSlice[["Tasks"], :])
    return styler


def _render_kid_history(kid: dict, shown_week: date) -> None:
    theme = _theme_for(kid["name"])
    st.markdown(f"### {theme['emoji']} :{theme['md_color']}[{kid['name']}]")

    summary = db.get_week_summary(kid["id"], shown_week)
    total_tasks = summary[0]["total"] if summary else 0

    days_complete = sum(1 for s in summary if s["all_done"])
    ninja_on = sum(1 for s in summary if s["ninja"] is not None)
    ninja_broken = sum(1 for s in summary if s["ninja"] and not s["ninja"]["maintained"])

    m1, m2, m3 = st.columns(3)
    m1.metric("Days done", f"{days_complete}/7")
    m2.metric("Ninja days", ninja_on)
    m3.metric("Ninja broken", ninja_broken)

    if total_tasks == 0:
        st.caption("_No active tasks configured, so there's nothing to count._")
    else:
        st.dataframe(_heatmap_styler(summary), use_container_width=True)

    notes = [(s["day"], s["ninja"]["note"]) for s in summary if s["ninja"] and s["ninja"]["note"]]
    if notes:
        with st.expander("🥷 Ninja notes"):
            for d, note in notes:
                st.markdown(f"- **{d.strftime('%a %d %b')}** — {note}")

    week_end = shown_week + timedelta(days=7)
    claims = db.list_reward_claims(kid["id"], shown_week, week_end)
    if claims:
        badges = [f"✅ {_REWARD_LABELS.get(c['reward_type'], c['reward_type'])}" for c in claims]
        st.caption("  ·  ".join(badges))
    else:
        st.caption("_No rewards claimed this week._")


def _render_history_tab(kids: list[dict], current_week_start: date) -> None:
    if "history_week" not in st.session_state:
        st.session_state["history_week"] = current_week_start

    shown = st.session_state["history_week"]
    today_week = db.week_start(date.today())
    next_disabled = shown + timedelta(days=7) > today_week

    # Week navigator — compact on phone.
    nav_prev, nav_label, nav_next = st.columns([1, 3, 1])
    with nav_prev:
        if st.button("←", use_container_width=True, key="hist_prev"):
            st.session_state["history_week"] = shown - timedelta(days=7)
            st.rerun()
    with nav_label:
        week_end = shown + timedelta(days=6)
        st.markdown(
            f"<div style='text-align:center;font-weight:600;padding-top:0.5rem'>"
            f"Week of {shown.strftime('%a %d %b')} → {week_end.strftime('%a %d %b')}"
            f"</div>",
            unsafe_allow_html=True,
        )
    with nav_next:
        if st.button("→", use_container_width=True, key="hist_next", disabled=next_disabled):
            st.session_state["history_week"] = shown + timedelta(days=7)
            st.rerun()

    if shown != today_week:
        if st.button("Jump to this week", key="hist_today", use_container_width=True):
            st.session_state["history_week"] = today_week
            st.rerun()

    st.divider()

    kid_tabs = st.tabs([_tab_label(k) for k in kids])
    for tab, kid in zip(kid_tabs, kids):
        with tab:
            _render_kid_history(kid, st.session_state["history_week"])


# --------------------------------------------------------------------------- #
# Admin panel (PIN-gated)
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Layout: top-level tabs + admin
# --------------------------------------------------------------------------- #

tab_today, tab_history = st.tabs(["📆 Today", "📈 History"])

with tab_today:
    _render_today_tab(kids, tasks, selected_day, week_start_day)

with tab_history:
    _render_history_tab(kids, week_start_day)


if st.session_state.get("admin"):
    st.divider()
    with st.expander("⚙️ Admin", expanded=True):
        _render_admin(kids, selected_day, week_start_day)
