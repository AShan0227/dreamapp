"""Quota service — pure-Python tz handling tests.

Regression test for the bug that fired on 2026-04-24:
  asyncpg refused to write a tz-AWARE datetime into the tz-NAIVE
  `users.video_quota_date` column with:
    "can't subtract offset-naive and offset-aware datetimes"

Result: every authenticated user's first /api/dreams/{id}/generate that
day returned 500 — payment-flow / video-gen completely broken.

Root cause: `_today_utc()` returned `datetime(..., tzinfo=timezone.utc)`
even though the column is `Column(DateTime, ...)` (naive). asyncpg can't
silently coerce. The fix forces both sides to NAIVE-UTC.

Pin both invariants here so the bug never returns:
  1. _today_utc() returns a naive datetime.
  2. _quota_day() also returns naive — even when given tz-aware input
     (legacy rows written before this fix).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.quota import _today_utc, _quota_day  # noqa: E402


def test_today_utc_is_naive():
    """The DB column is naive — `_today_utc()` MUST be naive too,
    otherwise asyncpg refuses the write."""
    d = _today_utc()
    assert d.tzinfo is None, (
        f"_today_utc() returned tz-aware datetime ({d.tzinfo!r}). "
        "users.video_quota_date is a naive DateTime column; mixing tz-aware "
        "values triggers asyncpg DataError on every video-gen request."
    )


def test_today_utc_is_midnight():
    d = _today_utc()
    assert d.hour == 0 and d.minute == 0 and d.second == 0


def test_quota_day_strips_naive_input():
    naive = datetime(2026, 4, 24, 13, 37, 5)
    out = _quota_day(naive)
    assert out is not None
    assert out.tzinfo is None
    assert out.hour == 0 and out.minute == 0


def test_quota_day_normalizes_tz_aware_input_to_naive():
    """Legacy rows written before the fix are tz-aware. _quota_day must
    NORMALIZE them to naive so subsequent comparisons (`last != today`)
    don't crash."""
    aware = datetime(2026, 4, 24, 13, 37, 5, tzinfo=timezone.utc)
    out = _quota_day(aware)
    assert out is not None
    assert out.tzinfo is None, (
        f"_quota_day(tz-aware) must return naive; got {out.tzinfo!r}. "
        "If aware leaks through, comparisons like `last_quota_day != today` "
        "raise the same TypeError that caused the original outage."
    )
    assert out.year == 2026 and out.month == 4 and out.day == 24


def test_quota_day_passes_through_none():
    assert _quota_day(None) is None


def test_today_and_quota_day_are_comparable():
    """The whole point: comparing today's reset boundary to the user's
    last_quota_day must not raise TypeError."""
    today = _today_utc()
    yesterday = _quota_day(datetime(2026, 4, 23))
    assert yesterday is not None
    assert yesterday < today    # would raise TypeError if mixed tz-ness
    assert today != yesterday
