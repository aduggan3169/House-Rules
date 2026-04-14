-- House Rules schema.
-- SQLite-compatible. For Postgres, swap INTEGER PRIMARY KEY for
-- GENERATED ALWAYS AS IDENTITY and DATE/TIMESTAMP types work as-is.

CREATE TABLE IF NOT EXISTS kids (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    display_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tasks (
    id            INTEGER PRIMARY KEY,
    label         TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0,
    active        INTEGER NOT NULL DEFAULT 1  -- SQLite boolean
);

CREATE TABLE IF NOT EXISTS task_completions (
    kid_id        INTEGER NOT NULL REFERENCES kids(id)  ON DELETE CASCADE,
    task_id       INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    day           DATE    NOT NULL,
    completed_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (kid_id, task_id, day)
);

CREATE TABLE IF NOT EXISTS ninja_mode_days (
    kid_id        INTEGER NOT NULL REFERENCES kids(id) ON DELETE CASCADE,
    day           DATE    NOT NULL,
    maintained    INTEGER NOT NULL DEFAULT 1,
    note          TEXT,
    PRIMARY KEY (kid_id, day)
);

CREATE TABLE IF NOT EXISTS rewards_claimed (
    id            INTEGER PRIMARY KEY,
    kid_id        INTEGER NOT NULL REFERENCES kids(id) ON DELETE CASCADE,
    reward_type   TEXT    NOT NULL,       -- 'daily_screen' | 'weekly_treat' | 'ninja_treat'
    period_start  DATE    NOT NULL,
    claimed_at    TIMESTAMP NOT NULL,
    UNIQUE (kid_id, reward_type, period_start)
);

CREATE INDEX IF NOT EXISTS idx_completions_kid_day ON task_completions(kid_id, day);
CREATE INDEX IF NOT EXISTS idx_ninja_kid_day       ON ninja_mode_days(kid_id, day);

-- Seed data (idempotent via INSERT OR IGNORE on UNIQUE columns).
INSERT OR IGNORE INTO kids (name, display_order) VALUES
    ('Cillian', 1),
    ('Fionn',   2);

-- Tasks are seeded by label uniqueness via a partial check in db.init_db,
-- since label isn't UNIQUE (we may want duplicates historically). See db.py.
