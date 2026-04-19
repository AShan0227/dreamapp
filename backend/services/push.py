"""Push + WeChat template-message delivery.

Three channels:
  - FCM (Firebase Cloud Messaging) — Android + iOS via Firebase
  - APNs (Apple Push) — optional, direct if not using Firebase
  - WeChat template message — for mini-program / official account users

All channels return bool (delivered vs not). None of them raise; failures
are logged and counted. Call sites use fire-and-forget.

Provider selection via env:
  DREAM_PUSH_PROVIDER   "" | "fcm" | "wechat" | "all" (default "")
  When "all", tries FCM first, falls back / parallels with WeChat if both
  configured.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger("dreamapp.push")


# ---------------- FCM ------------------------------------------------------

_FCM_TOKEN_CACHE: dict[str, tuple[str, float]] = {}  # project_id → (token, exp)


async def _get_fcm_token() -> Optional[str]:
    """Get an OAuth2 access token from a service-account JSON.

    Required env:
      DREAM_FCM_SERVICE_ACCOUNT_JSON — full JSON string of the service
        account (downloaded from Firebase console)
    """
    import json
    import time
    sa_json = os.getenv("DREAM_FCM_SERVICE_ACCOUNT_JSON", "")
    if not sa_json:
        return None
    try:
        sa = json.loads(sa_json)
    except json.JSONDecodeError:
        log.error("DREAM_FCM_SERVICE_ACCOUNT_JSON is not valid JSON")
        return None
    project_id = sa.get("project_id")
    if not project_id:
        return None

    # Cache
    cached = _FCM_TOKEN_CACHE.get(project_id)
    if cached and cached[1] > time.time() + 60:
        return cached[0]

    # Build JWT signed with the SA private key
    try:
        import base64
        import json as _json
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        header = {"alg": "RS256", "typ": "JWT", "kid": sa["private_key_id"]}
        now = int(time.time())
        claims = {
            "iss": sa["client_email"],
            "scope": "https://www.googleapis.com/auth/firebase.messaging",
            "aud": "https://oauth2.googleapis.com/token",
            "iat": now,
            "exp": now + 3600,
        }
        def _b64(d: bytes) -> str:
            return base64.urlsafe_b64encode(d).rstrip(b"=").decode()
        head_b64 = _b64(_json.dumps(header, separators=(",", ":")).encode())
        claims_b64 = _b64(_json.dumps(claims, separators=(",", ":")).encode())
        signing_input = f"{head_b64}.{claims_b64}".encode()
        priv = serialization.load_pem_private_key(sa["private_key"].encode(), password=None)
        sig = priv.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        jwt = f"{head_b64}.{claims_b64}.{_b64(sig)}"
    except Exception as e:
        log.exception("Failed to build FCM JWT: %s", e)
        return None

    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://oauth2.googleapis.com/token",
                data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": jwt},
            )
            data = r.json()
            token = data.get("access_token")
            if not token:
                log.error("FCM token exchange failed: %s", data)
                return None
            _FCM_TOKEN_CACHE[project_id] = (token, now + 3600)
            return token
    except Exception as e:
        log.exception("FCM token exchange error: %s", e)
        return None


async def send_fcm(device_token: str, title: str, body: str, data: Optional[dict] = None) -> bool:
    """Send to a single device token via FCM HTTP v1."""
    import json
    import httpx
    tok = await _get_fcm_token()
    if not tok:
        return False
    sa_json = os.getenv("DREAM_FCM_SERVICE_ACCOUNT_JSON", "")
    try:
        project_id = json.loads(sa_json).get("project_id")
    except json.JSONDecodeError:
        return False
    if not project_id:
        return False

    payload = {
        "message": {
            "token": device_token,
            "notification": {"title": title, "body": body},
            "data": {k: str(v) for k, v in (data or {}).items()},
        }
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
                headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                json=payload,
            )
            if r.status_code == 200:
                return True
            log.error("FCM rejected: %s %s", r.status_code, r.text[:200])
            return False
    except Exception as e:
        log.exception("FCM send error: %s", e)
        return False


# ---------------- WeChat template message ---------------------------------

_WECHAT_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


async def _get_wechat_access_token() -> Optional[str]:
    """Fetch + cache a WeChat mp/official-account access token.

    Required env:
      DREAM_WECHAT_MP_APPID      mini-program or official account appid
      DREAM_WECHAT_MP_SECRET     secret for the same
    """
    import time
    import httpx
    appid = os.getenv("DREAM_WECHAT_MP_APPID", "")
    secret = os.getenv("DREAM_WECHAT_MP_SECRET", "")
    if not appid or not secret:
        return None
    cached = _WECHAT_TOKEN_CACHE.get(appid)
    if cached and cached[1] > time.time() + 60:
        return cached[0]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.weixin.qq.com/cgi-bin/token",
                params={"grant_type": "client_credential", "appid": appid, "secret": secret},
            )
            data = r.json()
            tok = data.get("access_token")
            if not tok:
                log.error("WeChat token fetch failed: %s", data)
                return None
            expires = int(time.time()) + int(data.get("expires_in", 7200))
            _WECHAT_TOKEN_CACHE[appid] = (tok, expires)
            return tok
    except Exception as e:
        log.exception("WeChat token error: %s", e)
        return None


async def send_wechat_template(
    openid: str,
    template_id: str,
    data: dict,
    page: Optional[str] = None,
) -> bool:
    """Send a subscribe / template message.

    template_id + data shape depends on your WeChat template registration.
    `data` example: {"thing1": {"value": "新梦境"}, "thing2": {"value": "你收到一条评论"}}
    """
    import httpx
    tok = await _get_wechat_access_token()
    if not tok:
        return False
    body = {"touser": openid, "template_id": template_id, "data": data}
    if page:
        body["page"] = page
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://api.weixin.qq.com/cgi-bin/message/subscribe/send",
                params={"access_token": tok},
                json=body,
            )
            data_resp = r.json()
            if data_resp.get("errcode") == 0:
                return True
            log.error("WeChat template rejected: %s", data_resp)
            return False
    except Exception as e:
        log.exception("WeChat template error: %s", e)
        return False


# ---------------- Unified dispatch ----------------------------------------

# Template ID map — set via env so ops can change without deploy
WECHAT_TEMPLATE_IDS = {
    "comment": os.getenv("DREAM_WECHAT_TEMPLATE_COMMENT", ""),
    "reaction": os.getenv("DREAM_WECHAT_TEMPLATE_REACTION", ""),
    "follow": os.getenv("DREAM_WECHAT_TEMPLATE_FOLLOW", ""),
    "mention": os.getenv("DREAM_WECHAT_TEMPLATE_MENTION", ""),
    "dm": os.getenv("DREAM_WECHAT_TEMPLATE_DM", ""),
    "video_ready": os.getenv("DREAM_WECHAT_TEMPLATE_VIDEO_READY", ""),
    "payment_success": os.getenv("DREAM_WECHAT_TEMPLATE_PAYMENT", ""),
}


async def dispatch(
    user_push_token: Optional[str],
    user_wechat_openid: Optional[str],
    kind: str,
    title: str,
    body: str,
    *,
    data: Optional[dict] = None,
    wechat_template_data: Optional[dict] = None,
    wechat_page: Optional[str] = None,
) -> dict:
    """Best-effort dispatch across whatever channels the user has.

    Returns {"fcm": bool, "wechat": bool} so callers can log channel health.
    """
    provider = os.getenv("DREAM_PUSH_PROVIDER", "").lower()
    result = {"fcm": False, "wechat": False}

    if provider in ("", "noop"):
        log.info("[PUSH noop] kind=%s title=%s", kind, title)
        return result

    if provider in ("fcm", "all") and user_push_token:
        result["fcm"] = await send_fcm(user_push_token, title, body, data)
    if provider in ("wechat", "all") and user_wechat_openid:
        tpl_id = WECHAT_TEMPLATE_IDS.get(kind, "")
        if tpl_id and wechat_template_data:
            result["wechat"] = await send_wechat_template(
                user_wechat_openid, tpl_id, wechat_template_data, page=wechat_page,
            )
    return result
