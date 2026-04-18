# House Rules App — Build Plan

A daily house rules tracker for Cillian & Fionn. Local-first Streamlit app, SQLite-backed, with a clean migration path to Streamlit Community Cloud + Supabase. Parents tick on behalf of the kids; a PIN gates admin actions.

---

## 1. Goals & constraints

- **Primary goal:** A working local app that two parents can access from any device on the home WiFi, tick off daily tasks per kid, and see rewards unlock.
- **Non-goal (for now):** Kid-facing UX, mobile-native app, cloud hosting, multi-family support.
- **Quality bars:**
  - UI never touches storage — all reads/writes through `db.py`.
  - Schema changes drive migrations, not ad-hoc SQL in the app.
  - Zero secrets in the repo; `.db` and `.env` gitignored.
- **Migration contract:** swapping SQLite for Supabase Postgres should touch only `db.py` (engine construction) and `.env` (connection string). `schema.sql` must be valid on both dialects.

---

## 2. Architecture at a glance

```
House-Rules/
├── app.py              # Streamlit UI, no DB calls
├── db.py               # All persistence; SQLAlchemy-backed
├── schema.sql          # DDL, portable across SQLite + Postgres
├── requirements.txt
├── .env                # DB connection string, parent PIN hash (gitignored)
├── .env.example        # Committed template
├── .gitignore
├── data/
│   └── house_rules.db  # SQLite file (gitignored)
└── PLAN.md
```

Data flow: `app.py → db.py → SQLAlchemy engine → SQLite (local) or Postgres (later)`. The UI layer imports functions like `db.get_day(kid_id, date)` and `db.tick_task(...)`, never raw SQL or ORM sessions.

---

## 3. Phased build order

- **Phase 0** — Repo hygiene: `.gitignore`, `.env.example`, `requirements.txt`, module skeletons. ✅ done.
- **Phase 1** — Schema + `db.py` skeleton: `list_kids`, `list_tasks`, `get_day`, `tick_task`, `untick_task`, pytest suite. ✅ done.
- **Phase 2** — Minimal UI loop: two columns, checkboxes, progress bars, day picker, LAN-accessible.
- **Phase 3** — Rewards + Ninja Mode: daily/weekly eligibility, ledger, confetti, Ninja toggle + note.
- **Phase 4** — PIN gate + admin panel: bcrypt PIN, sidebar unlock, reset/edit/override.
- **Phase 5** — Polish: weekly summary heatmap, per-kid theming, toasts, history view. ✅ done.
- **Phase 6** — (Later) Migration to Supabase + Streamlit Community Cloud.

See repo history and commit messages for per-phase detail.

---

## 4. Open questions (parked until they bite)

- **Timezone.** Naive local time is fine for one household in Ireland.
- **History depth.** Schema supports unlimited; UI surfaces only what's useful.
- **Ninja granularity.** One row per kid per day for now; extend if multiple events per day become real.
- **PIN reset.** Escape hatch is editing `.env` directly.
