"""Authentication for the House Rules app.

Currently just a single bcrypt PIN, loaded from PARENT_PIN_HASH in .env.
Gates access to admin actions (reset day, edit tasks, revoke claims);
day-to-day ticking is not gated.

In Phase 6 this module is the obvious place to swap in Streamlit's
built-in Google auth with an email whitelist. Keep the public surface
(pin_is_configured / verify_pin) small so that swap is a one-line
change in app.py.
"""

from __future__ import annotations

import os

import bcrypt
from dotenv import load_dotenv

load_dotenv()


def pin_is_configured() -> bool:
    """True iff PARENT_PIN_HASH is set in the environment."""
    return bool(os.environ.get("PARENT_PIN_HASH"))


def verify_pin(pin: str) -> bool:
    """Return True iff `pin` matches the PARENT_PIN_HASH bcrypt hash."""
    hashed = os.environ.get("PARENT_PIN_HASH")
    if not hashed or not pin:
        return False
    try:
        return bcrypt.checkpw(pin.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed hash or non-string input — treat as failed auth.
        return False
