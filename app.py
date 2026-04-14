"""Streamlit UI for the House Rules app.

Phase 2 will flesh this out. For now, this is a minimal smoke-test page
so we can confirm the wiring from app.py -> db.py works end-to-end.
"""

from datetime import date

import streamlit as st

import db

st.set_page_config(page_title="House Rules", page_icon="🏡", layout="centered")

# Ensure schema exists on every start (cheap, idempotent).
db.init_db()

st.title("🏡 House Rules")
st.caption("Scaffold running. UI comes in Phase 2.")

kids = db.list_kids()
tasks = db.list_tasks()

st.subheader("Kids")
st.write(kids)

st.subheader("Tasks")
st.write(tasks)

st.subheader(f"Today — {date.today().isoformat()}")
for kid in kids:
    d = db.get_day(kid["id"], date.today())
    st.write(f"**{kid['name']}** — {len(d['completions'])} / {len(tasks)} done")
