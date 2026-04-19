"""Password hashing utilities. bcrypt + a tight wrapper for safety."""

from __future__ import annotations

import bcrypt


def hash_password(plain: str) -> str:
    if not plain:
        raise ValueError("Empty password")
    if len(plain.encode("utf-8")) > 72:
        # bcrypt hard-limits at 72 bytes. Refuse rather than silently truncate.
        raise ValueError("Password too long (max 72 bytes)")
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed or not plain:
        return False
    if len(plain.encode("utf-8")) > 72:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
