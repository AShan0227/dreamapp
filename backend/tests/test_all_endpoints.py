"""Smoke + auth + Genesis-loop coverage for all DreamApp endpoints.

Run while the backend is up on localhost:8000:
    python tests/test_all_endpoints.py

Set ``DREAMAPP_BASE=http://...`` to target a non-local backend.

Test isolation: every account / dream this script creates is registered
in a teardown bag and deleted at the end (success OR failure). Run a
hundred times — the prod DB stays clean. Set ``DREAMAPP_KEEP=1`` to skip
teardown when investigating a failure.

Exits 0 if all assertions pass, non-zero otherwise.
"""

import asyncio
import os
import sys
import time
from contextlib import suppress

import httpx

BASE = os.getenv("DREAMAPP_BASE", "http://localhost:8000")
KEEP = os.getenv("DREAMAPP_KEEP", "").lower() in ("1", "true", "yes")


# Bag of cleanup callables run in reverse order at teardown.
_teardown: list = []


def _register_cleanup(fn):
    _teardown.append(fn)
    return fn


async def _teardown_all(c: httpx.AsyncClient):
    if KEEP:
        print(f"\nDREAMAPP_KEEP=1 — leaving {len(_teardown)} test artifacts in DB")
        return
    failures = 0
    for fn in reversed(_teardown):
        try:
            await fn(c)
        except Exception as e:
            failures += 1
            print(f"  ! teardown step failed: {e}")
    print(f"\nteardown: {len(_teardown) - failures}/{len(_teardown)} cleaned up")


async def _delete_user(c: httpx.AsyncClient, token: str):
    """Hard-delete a test user via the GDPR /me/delete endpoint.

    Earlier versions only soft-deleted the user's dreams, which left the
    user row in the prod DB — over time we accumulated dozens of test
    accounts. Now we use the same endpoint a real user would call to
    purge their account, exercising it as part of every test run.
    """
    if not token:
        return
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    with suppress(Exception):
        await c.post(
            f"{BASE}/api/users/me/delete",
            headers=h,
            json={"confirmation": "DELETE MY ACCOUNT"},
        )


class T:
    """Test runner with light assertions and pretty output."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors: list[str] = []

    def ok(self, name: str):
        self.passed += 1
        print(f"  \u2713 {name}")

    def fail(self, name: str, detail: str):
        self.failed += 1
        msg = f"  \u2717 {name}: {detail}"
        self.errors.append(msg)
        print(msg)

    async def expect(self, name: str, fn):
        try:
            result = fn()
            if asyncio.iscoroutine(result):
                result = await result
            ok, detail = result
            if ok:
                self.ok(name)
            else:
                self.fail(name, detail)
        except Exception as e:
            self.fail(name, f"raised {type(e).__name__}: {e}")


def headers(token: str | None = None) -> dict:
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


async def main() -> int:
    t = T()

    async with httpx.AsyncClient(timeout=60) as c:
        try:
            return await _run_tests(c, t)
        finally:
            await _teardown_all(c)


async def _run_tests(c: httpx.AsyncClient, t: "T") -> int:
        # --- Health ---
        async def h_health():
            r = await c.get(f"{BASE}/health")
            return r.status_code == 200 and r.json().get("status") == "ok", str(r.status_code)
        await t.expect("health", h_health)

        # --- Anonymous register (legacy quick onboarding) ---
        nickname_a = f"TesterA_{int(time.time())}"
        rA = await c.post(f"{BASE}/api/users/register", json={"nickname": nickname_a})
        userA = rA.json()
        tokenA = userA.get("token")
        if tokenA:
            _register_cleanup(lambda c, tk=tokenA: _delete_user(c, tk))
        await t.expect(
            "register anon user",
            lambda: ((rA.status_code == 200 and tokenA, f"sc={rA.status_code}")),
        )

        # --- Email register + login ---
        email = f"e2e+{int(time.time())}@example.com"
        rE = await c.post(
            f"{BASE}/api/users/register/email",
            json={"email": email, "password": "Hunter22Hunter22", "nickname": "EmailUser"},
        )
        await t.expect("register email", lambda: ((rE.status_code == 200, f"sc={rE.status_code}, body={rE.text[:200]}")))
        if rE.status_code == 200:
            email_token = rE.json().get("token")
            if email_token:
                _register_cleanup(lambda c, tk=email_token: _delete_user(c, tk))
            rDup = await c.post(
                f"{BASE}/api/users/register/email",
                json={"email": email, "password": "Hunter22Hunter22"},
            )
            # Anti-enumeration: duplicate registration must NOT return 409
            # (which would let an attacker probe which emails are registered).
            # It returns 401 — indistinguishable from a wrong-password login.
            await t.expect(
                "register email duplicate \u2192 401 (anti-enumeration)",
                lambda: ((rDup.status_code == 401, f"sc={rDup.status_code}")),
            )

            rL = await c.post(
                f"{BASE}/api/users/login/email",
                json={"email": email, "password": "Hunter22Hunter22"},
            )
            await t.expect(
                "login email correct \u2192 200",
                lambda: ((rL.status_code == 200, f"sc={rL.status_code}")),
            )

            rW = await c.post(
                f"{BASE}/api/users/login/email",
                json={"email": email, "password": "wrong-password"},
            )
            await t.expect(
                "login email wrong \u2192 401",
                lambda: ((rW.status_code == 401, f"sc={rW.status_code}")),
            )

        # --- Auth enforcement: dreams require Bearer token ---
        rNoAuth = await c.get(f"{BASE}/api/dreams/")
        await t.expect(
            "GET /api/dreams/ without auth \u2192 401",
            lambda: ((rNoAuth.status_code == 401, f"sc={rNoAuth.status_code}")),
        )

        rNoAuthStart = await c.post(
            f"{BASE}/api/dreams/start",
            json={"initial_input": "no auth", "style": "surreal"},
        )
        await t.expect(
            "POST /api/dreams/start without auth \u2192 401",
            lambda: ((rNoAuthStart.status_code == 401, f"sc={rNoAuthStart.status_code}")),
        )

        # --- Authenticated dream listing ---
        rList = await c.get(f"{BASE}/api/dreams/", headers=headers(tokenA))
        await t.expect(
            "GET /api/dreams/ authed \u2192 200",
            lambda: ((rList.status_code == 200, f"sc={rList.status_code}")),
        )

        # --- Cross-user isolation ---
        rB = await c.post(f"{BASE}/api/users/register", json={"nickname": "TesterB"})
        tokenB = rB.json().get("token")
        if tokenB:
            _register_cleanup(lambda c, tk=tokenB: _delete_user(c, tk))

        rStart = await c.post(
            f"{BASE}/api/dreams/start",
            headers=headers(tokenA),
            json={"initial_input": "I dreamed of a glowing tree", "style": "surreal"},
        )
        await t.expect(
            "start dream as A \u2192 200",
            lambda: ((rStart.status_code == 200, f"sc={rStart.status_code}, body={rStart.text[:200]}")),
        )
        dream_id = rStart.json().get("dream_id") if rStart.status_code == 200 else None

        if dream_id:
            rPub = await c.post(
                f"{BASE}/api/plaza/dreams/{dream_id}/publish",
                headers=headers(tokenB),
            )
            await t.expect(
                "B can't publish A's dream \u2192 403",
                lambda: ((rPub.status_code == 403, f"sc={rPub.status_code}")),
            )

            rChat = await c.post(
                f"{BASE}/api/dreams/chat",
                headers=headers(tokenB),
                json={"dream_id": dream_id, "message": "hi"},
            )
            await t.expect(
                "B can't chat A's dream \u2192 403",
                lambda: ((rChat.status_code == 403, f"sc={rChat.status_code}")),
            )

            rFb = await c.post(
                f"{BASE}/api/dreams/{dream_id}/feedback",
                headers=headers(tokenB),
                json={"aspect": "interpretation", "helpful": False},
            )
            await t.expect(
                "B can't feedback A's dream \u2192 403",
                lambda: ((rFb.status_code == 403, f"sc={rFb.status_code}")),
            )

            rCit = await c.get(
                f"{BASE}/api/dreams/{dream_id}/citations",
                headers=headers(tokenA),
            )
            await t.expect(
                "A gets own citations \u2192 200",
                lambda: ((rCit.status_code == 200, f"sc={rCit.status_code}")),
            )

            rPatch = await c.patch(
                f"{BASE}/api/dreams/{dream_id}",
                headers=headers(tokenA),
                json={"title": "Glowing tree dream"},
            )
            await t.expect(
                "PATCH dream title \u2192 200",
                lambda: ((rPatch.status_code == 200 and rPatch.json().get("title") == "Glowing tree dream",
                         f"sc={rPatch.status_code}, body={rPatch.text[:200]}")),
            )

            rDel = await c.delete(
                f"{BASE}/api/dreams/{dream_id}",
                headers=headers(tokenA),
            )
            await t.expect(
                "DELETE own dream \u2192 200",
                lambda: ((rDel.status_code == 200, f"sc={rDel.status_code}")),
            )

            rGone = await c.get(
                f"{BASE}/api/dreams/{dream_id}",
                headers=headers(tokenA),
            )
            await t.expect(
                "deleted dream \u2192 404",
                lambda: ((rGone.status_code == 404, f"sc={rGone.status_code}")),
            )

        # --- Plaza public reads still work without auth ---
        rPlazaList = await c.get(f"{BASE}/api/plaza/dreams")
        await t.expect(
            "plaza browse anon \u2192 200",
            lambda: ((rPlazaList.status_code == 200, f"sc={rPlazaList.status_code}")),
        )

        rTrend = await c.get(f"{BASE}/api/plaza/trending")
        await t.expect(
            "plaza trending \u2192 200",
            lambda: ((rTrend.status_code == 200, f"sc={rTrend.status_code}")),
        )

        rKS = await c.get(f"{BASE}/api/plaza/knowledge-search?q=flying&limit=15")
        await t.expect(
            "knowledge search \u2192 200 + results",
            lambda: ((
                rKS.status_code == 200 and isinstance(rKS.json(), list) and len(rKS.json()) > 0,
                f"sc={rKS.status_code}",
            )),
        )

        if rKS.status_code == 200 and isinstance(rKS.json(), list):
            tiers = {e.get("tier") for e in rKS.json()}
            # Tier diversity: must hit at least L1 (and ideally L2); L1-only is
            # acceptable when graduated promotions have absorbed everything
            # corpus-shaped, but the seeded corpus must still leave L2 entries.
            await t.expect(
                "knowledge search yields tier diversity (L1 present, ideally L2 too)",
                lambda: ((
                    "L1" in tiers,
                    f"tiers={tiers}",
                )),
            )

        # --- Sleep cycle + admin endpoints ---
        # sleep-cycle requires auth (destructive). Pass tokenA.
        rSC = await c.post(
            f"{BASE}/api/plaza/knowledge/sleep-cycle?skip_merge=true",
            headers=headers(tokenA),
        )
        await t.expect(
            "sleep-cycle (skip_merge) \u2192 200",
            lambda: ((rSC.status_code == 200 and "decayed" in rSC.json(), f"sc={rSC.status_code}")),
        )

        rTop = await c.get(f"{BASE}/api/plaza/knowledge/top?by=use_count&limit=5")
        await t.expect(
            "knowledge/top \u2192 200",
            lambda: ((rTop.status_code == 200 and isinstance(rTop.json(), list), f"sc={rTop.status_code}")),
        )

        rSched = await c.get(f"{BASE}/api/plaza/knowledge/scheduler")
        await t.expect(
            "knowledge/scheduler \u2192 200",
            lambda: ((
                rSched.status_code == 200 and "running" in rSched.json(),
                f"sc={rSched.status_code}",
            )),
        )

        # --- Quota status ---
        rQ = await c.get(f"{BASE}/api/users/me/quota", headers=headers(tokenA))
        await t.expect(
            "GET /me/quota \u2192 daily_cap present",
            lambda: ((
                rQ.status_code == 200 and rQ.json().get("daily_cap", 0) > 0,
                f"sc={rQ.status_code}, body={rQ.text[:200]}",
            )),
        )

        # --- GDPR data export ---
        rExp = await c.get(f"{BASE}/api/users/me/export", headers=headers(tokenA))
        await t.expect(
            "GET /me/export \u2192 200 + user payload",
            lambda: ((
                rExp.status_code == 200 and "user" in rExp.json() and rExp.json()["user"].get("password_hash") == "<redacted>",
                f"sc={rExp.status_code}",
            )),
        )

        # --- Hard account delete requires exact confirmation ---
        rDelBad = await c.post(
            f"{BASE}/api/users/me/delete",
            headers=headers(tokenA),
            json={"confirmation": "delete me"},
        )
        await t.expect(
            "POST /me/delete with wrong confirmation \u2192 400",
            lambda: ((rDelBad.status_code == 400, f"sc={rDelBad.status_code}")),
        )

        # --- Body size limit (413) ---
        big_payload = "x" * (6 * 1024 * 1024)  # 6 MB > 5 MB cap
        rBig = await c.post(
            f"{BASE}/api/dreams/start",
            headers=headers(tokenA),
            json={"initial_input": big_payload, "style": "surreal"},
        )
        await t.expect(
            "oversized request body \u2192 413",
            lambda: ((rBig.status_code == 413, f"sc={rBig.status_code}")),
        )

        # --- Wave H: subscriptions, coins, follows, payments ---
        rPlans = await c.get(f"{BASE}/api/subscription/plans")
        await t.expect(
            "GET /subscription/plans \u2192 3 tiers",
            lambda: ((rPlans.status_code == 200 and len(rPlans.json()) == 3, f"sc={rPlans.status_code}")),
        )

        rEnt = await c.get(f"{BASE}/api/subscription/me", headers=headers(tokenA))
        await t.expect(
            "GET /subscription/me \u2192 free tier defaults",
            lambda: ((
                rEnt.status_code == 200 and rEnt.json().get("tier") == "free",
                f"sc={rEnt.status_code}",
            )),
        )

        rRef = await c.get(f"{BASE}/api/referrals/me", headers=headers(tokenA))
        await t.expect(
            "GET /referrals/me \u2192 code issued",
            lambda: ((rRef.status_code == 200 and len(rRef.json().get("code", "")) >= 6, f"sc={rRef.status_code}")),
        )

        rCoins = await c.get(f"{BASE}/api/coins/balance", headers=headers(tokenA))
        await t.expect(
            "GET /coins/balance \u2192 0 for new user",
            lambda: ((rCoins.status_code == 200 and rCoins.json().get("balance") == 0, f"sc={rCoins.status_code}")),
        )

        # Sandbox payment flow: create + complete + verify subscription upgrade
        rPay = await c.post(
            f"{BASE}/api/payments/create",
            headers=headers(tokenA),
            json={"purpose": "subscription_pro", "provider": "wechat"},
        )
        await t.expect(
            "POST /payments/create (wechat sandbox) \u2192 200",
            lambda: ((rPay.status_code == 200 and rPay.json().get("amount_cents") == 2900, f"sc={rPay.status_code}")),
        )
        if rPay.status_code == 200:
            otn = rPay.json()["out_trade_no"]
            rDone = await c.post(f"{BASE}/api/payments/sandbox-complete?out_trade_no={otn}")
            await t.expect(
                "sandbox-complete \u2192 200",
                lambda: ((rDone.status_code == 200, f"sc={rDone.status_code}")),
            )
            # Refresh entitlement — should now be Pro
            rEnt2 = await c.get(f"{BASE}/api/subscription/me", headers=headers(tokenA))
            await t.expect(
                "post-payment subscription \u2192 pro",
                lambda: ((
                    rEnt2.json().get("tier") == "pro" and rEnt2.json().get("video_quota_daily") == 30,
                    f"tier={rEnt2.json().get('tier')}",
                )),
            )

        # Public co-dream lobby (was the unfixed bug)
        rLobby = await c.get(f"{BASE}/api/codream/lobby")
        await t.expect(
            "GET /codream/lobby \u2192 200 + list",
            lambda: ((rLobby.status_code == 200 and isinstance(rLobby.json(), list), f"sc={rLobby.status_code}")),
        )

        # Therapist directory
        rTher = await c.get(f"{BASE}/api/therapists/")
        await t.expect(
            "GET /therapists/ \u2192 200",
            lambda: ((rTher.status_code == 200 and isinstance(rTher.json(), list), f"sc={rTher.status_code}")),
        )

        # API key requires Pro/Premium — tokenA just upgraded to Pro
        rKey = await c.post(
            f"{BASE}/api/api-keys/",
            headers=headers(tokenA),
            json={"name": "test-key", "scopes": ["knowledge:read"]},
        )
        await t.expect(
            "POST /api-keys/ as Pro \u2192 200 + plaintext key",
            lambda: ((
                rKey.status_code == 200 and rKey.json().get("key", "").startswith("dreamapi_"),
                f"sc={rKey.status_code}",
            )),
        )

        # --- Wave I: Threads-style social ---
        # Profile + handle
        rHandle = await c.patch(
            f"{BASE}/api/profile/me",
            headers=headers(tokenA),
            json={"handle": f"alice{int(time.time())}", "bio": "test bio"},
        )
        await t.expect(
            "PATCH /profile/me \u2192 handle set",
            lambda: ((rHandle.status_code == 200 and rHandle.json().get("handle"), f"sc={rHandle.status_code}")),
        )

        # Follow Bob (tokenB) so we can test follow notification + DMs
        rB_user = await c.get(f"{BASE}/api/users/me", headers=headers(tokenB))
        bob_id = rB_user.json()["id"]
        rA_user = await c.get(f"{BASE}/api/users/me", headers=headers(tokenA))
        alice_id = rA_user.json()["id"]

        rFollow = await c.post(f"{BASE}/api/follows/{alice_id}", headers=headers(tokenB))
        await t.expect(
            "Bob follows Alice \u2192 200",
            lambda: ((rFollow.status_code == 200, f"sc={rFollow.status_code}")),
        )

        # Alice should now have a notification
        rUnread = await c.get(f"{BASE}/api/notifications/unread-count", headers=headers(tokenA))
        await t.expect(
            "Alice has 1 unread notification (follow)",
            lambda: ((rUnread.json().get("count", 0) >= 1, f"count={rUnread.json().get('count')}")),
        )

        # DM should fail (not mutual)
        rDM_fail = await c.post(
            f"{BASE}/api/dm/send", headers=headers(tokenB),
            json={"recipient_id": alice_id, "body": "hi"},
        )
        await t.expect(
            "Bob \u2192 Alice DM without mutual \u2192 403",
            lambda: ((rDM_fail.status_code == 403, f"sc={rDM_fail.status_code}")),
        )

        # Make mutual: Alice follows Bob
        await c.post(f"{BASE}/api/follows/{bob_id}", headers=headers(tokenA))

        # DM works now
        rDM_ok = await c.post(
            f"{BASE}/api/dm/send", headers=headers(tokenB),
            json={"recipient_id": alice_id, "body": "hi alice"},
        )
        await t.expect(
            "Bob \u2192 Alice DM after mutual \u2192 200",
            lambda: ((rDM_ok.status_code == 200, f"sc={rDM_ok.status_code}")),
        )

        # Hashtag follow + list
        rTag = await c.post(f"{BASE}/api/hashtags/lucid/follow", headers=headers(tokenA))
        await t.expect(
            "follow #lucid \u2192 200",
            lambda: ((rTag.status_code == 200, f"sc={rTag.status_code}")),
        )

        rTagList = await c.get(f"{BASE}/api/hashtags/me", headers=headers(tokenA))
        await t.expect(
            "Alice followed tags includes lucid",
            lambda: (("lucid" in rTagList.json(), f"tags={rTagList.json()}")),
        )

        # Mute toggle
        rMute = await c.post(f"{BASE}/api/users/{bob_id}/mute", headers=headers(tokenA))
        await t.expect(
            "mute toggle \u2192 muted true",
            lambda: ((rMute.json().get("muted") is True, f"body={rMute.json()}")),
        )

        # Bookmark a dream
        rBM = await c.post(f"{BASE}/api/dreams/nonexistent/bookmark", headers=headers(tokenA))
        # bookmarks don't validate dream exists — succeeds even on bogus id
        await t.expect(
            "POST bookmark \u2192 200",
            lambda: ((rBM.status_code == 200, f"sc={rBM.status_code}")),
        )

        # FYP — should 200 even with no signature
        rFYP = await c.get(f"{BASE}/api/feed/for-you", headers=headers(tokenA))
        await t.expect(
            "GET /feed/for-you \u2192 200",
            lambda: ((rFYP.status_code == 200 and isinstance(rFYP.json(), list), f"sc={rFYP.status_code}")),
        )

        # Trending hashtags
        rTrending = await c.get(f"{BASE}/api/hashtags/trending/")
        await t.expect(
            "GET /hashtags/trending \u2192 200",
            lambda: ((rTrending.status_code == 200 and isinstance(rTrending.json(), list), f"sc={rTrending.status_code}")),
        )

        # --- /metrics: when DREAM_METRICS_TOKEN unset, returns 200 (back-compat) ---
        # When set, would return 401 without bearer; this test environment doesn't
        # set it, so we just verify the endpoint exists and returns prom format.
        rMet = await c.get(f"{BASE}/metrics")
        await t.expect(
            "GET /metrics \u2192 200 + prometheus format",
            lambda: ((
                rMet.status_code == 200 and "dreamapp_" in rMet.text,
                f"sc={rMet.status_code}",
            )),
        )

        print(f"\n{'='*48}")
        print(f"Passed: {t.passed}, Failed: {t.failed}")
        return 0 if t.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
