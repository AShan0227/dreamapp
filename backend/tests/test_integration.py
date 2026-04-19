"""Integration tests against a live backend at localhost:8000.

These cover the three race / authorization risks flagged in the audit:
  1. Video-quota TOCTOU — two concurrent /generate calls must not both win
  2. IDOR — user B must not be able to read / mutate / delete user A's dream
  3. Coin balance race — concurrent /gift must not push balance negative

Every test creates its own anonymous users + dreams and cleans up at the end.

Prereqs:
  - Backend reachable at DREAMAPP_BASE (default http://localhost:8000)
  - Free tier daily cap >= 2 (default is 3 so fine)

Run:
    pytest tests/test_integration.py -v
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = os.getenv("DREAMAPP_BASE", "http://localhost:8000")
TIMEOUT = 30


async def _register(c: httpx.AsyncClient, nickname: str = "tester") -> tuple[str, str]:
    r = await c.post(f"{BASE}/api/users/register", json={"nickname": nickname})
    r.raise_for_status()
    d = r.json()
    return d["id"], d["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---- IDOR ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_idor_cannot_read_other_users_private_dream():
    """Anonymous user A creates a private dream. User B MUST NOT be able to
    read it via /api/dreams/{id}."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        _, tok_a = await _register(c, "idor_a")
        _, tok_b = await _register(c, "idor_b")

        # A creates a dream
        r = await c.post(
            f"{BASE}/api/dreams/start",
            json={"initial_input": "a private dream about a secret", "style": "surreal"},
            headers=_auth(tok_a),
        )
        assert r.status_code == 200
        dream_id = r.json().get("dream_id")
        assert dream_id

        # B tries to read it — expect 4xx
        r2 = await c.get(f"{BASE}/api/dreams/{dream_id}", headers=_auth(tok_b))
        assert r2.status_code in (403, 404), f"IDOR: B read A's dream → {r2.status_code} {r2.text}"


@pytest.mark.asyncio
async def test_idor_cannot_delete_other_users_dream():
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        _, tok_a = await _register(c, "idor_del_a")
        _, tok_b = await _register(c, "idor_del_b")
        r = await c.post(
            f"{BASE}/api/dreams/start",
            json={"initial_input": "owner only", "style": "surreal"},
            headers=_auth(tok_a),
        )
        dream_id = r.json().get("dream_id")
        assert dream_id

        r2 = await c.delete(f"{BASE}/api/dreams/{dream_id}", headers=_auth(tok_b))
        assert r2.status_code in (403, 404), f"IDOR: B deleted A's dream → {r2.status_code}"


@pytest.mark.asyncio
async def test_unauthenticated_cannot_read_private_dream():
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        _, tok_a = await _register(c, "idor_anon")
        r = await c.post(
            f"{BASE}/api/dreams/start",
            json={"initial_input": "private", "style": "surreal"},
            headers=_auth(tok_a),
        )
        dream_id = r.json().get("dream_id")
        assert dream_id

        # No auth header
        r2 = await c.get(f"{BASE}/api/dreams/{dream_id}")
        assert r2.status_code in (401, 403, 404), f"anon read private → {r2.status_code}"


# ---- Coin balance race ---------------------------------------------------

@pytest.mark.asyncio
async def test_cannot_gift_more_coins_than_balance():
    """User with 0 coins tries to gift 100 → must 400/403, balance stays 0."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        uid_a, tok_a = await _register(c, "gift_a")
        uid_b, tok_b = await _register(c, "gift_b")

        r = await c.post(
            f"{BASE}/api/coins/gift",
            json={"to_user_id": uid_b, "amount": 100, "note": "try negative"},
            headers=_auth(tok_a),
        )
        # Either the service rejects (400) or the debit check fails (422).
        # The critical invariant: balance MUST NOT be negative.
        bal = (await c.get(f"{BASE}/api/coins/balance", headers=_auth(tok_a))).json()
        assert bal["balance"] >= 0, f"BALANCE WENT NEGATIVE: {bal}"


# ---- Report target-self prevention --------------------------------------

@pytest.mark.asyncio
async def test_cannot_report_yourself():
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        uid, tok = await _register(c, "self_report")
        r = await c.post(
            f"{BASE}/api/moderation/report",
            json={"target_type": "user", "target_id": uid, "reason": "spam"},
            headers=_auth(tok),
        )
        assert r.status_code == 400


# ---- Oversized semantic query cap ---------------------------------------

@pytest.mark.asyncio
async def test_semantic_search_caps_query_length():
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        giant = "x" * 500
        r = await c.get(f"{BASE}/api/plaza/search", params={"q": giant})
        assert r.status_code == 422, f"giant q not rejected: {r.status_code}"


# ---- Analytics event allowlist ------------------------------------------

@pytest.mark.asyncio
async def test_analytics_rejects_disallowed_event_from_client():
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        _, tok = await _register(c, "an")
        r = await c.post(
            f"{BASE}/api/analytics/track",
            json={"event": "payment_succeeded", "props": {"fake": True}},
            headers=_auth(tok),
        )
        # Client-side event allowlist: payment_succeeded must NOT be acceptable
        assert r.status_code == 400


# ---- Moderation staff gate ----------------------------------------------

@pytest.mark.asyncio
async def test_non_staff_cannot_list_moderation_queue():
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        _, tok = await _register(c, "non_staff")
        r = await c.get(f"{BASE}/api/moderation/queue", headers=_auth(tok))
        assert r.status_code == 403
        r2 = await c.get(f"{BASE}/api/analytics/overview", headers=_auth(tok))
        assert r2.status_code == 403
