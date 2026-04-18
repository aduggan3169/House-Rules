"""Authentication for the House Rules app.

Currently a single bcrypt PIN, loaded from PARENT_PIN_HASH. Gates
access to admin actions (reset day, edit tasks, revoke claims);
day-to-day ticking is not gated.

Secrets are read from Streamlit's st.secrets first (Streamlit
Community Cloud) and fall back to .env / os.environ for local dev.
"""

from __future__ import annotations

import os

import bcrypt
from dotenv import load_dotenv

load_dotenv()


def _get_secret(key: str) -> str | None:
    """Read from st.secrets (cloud) or os.environ (local)."""
    try:
        import streamlit as st

        if hasattr(st, "secrets") and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key)


def pin_is_configured() -> bool:
    """True iff PARENT_PIN_HASH is set."""
    return bool(_get_secret("PARENT_PIN_HASH"))


def verify_pin(pin: str) -> bool:
    """Return True iff `pin` matches the PARENT_PIN_HASH bcrypt hash."""
    hashed = _get_secret("PARENT_PIN_HASH")
    if not hashed or not pin:
        return False
    try:
        return bcrypt.checkpw(pin.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
