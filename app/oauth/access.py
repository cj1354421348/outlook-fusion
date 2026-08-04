"""access token 获取：解密 refresh_token → 按协议 scope 换 access_token。"""
from __future__ import annotations

import httpx

from app.config import logger, settings
from app.db.models import Account
from app.oauth.refresh import get_scope_for_protocol
from app.security.encryption import decrypt_token

_shared_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(timeout=30.0)
    return _shared_client


async def fetch_access_token(account: Account, protocol: str | None = None) -> str:
    """返回指定协议的 access_token（每次经 refresh_token 换取，短命，不入库）。"""
    plain = decrypt_token(account.refresh_token)
    scope = get_scope_for_protocol(protocol)
    payload = {
        "client_id": account.client_id,
        "grant_type": "refresh_token",
        "refresh_token": plain,
        "scope": scope,
    }
    token_url = f"{settings.AUTHORITY}/oauth2/v2.0/token"
    try:
        resp = await _get_client().post(token_url, data=payload)
    except httpx.HTTPError as exc:
        logger.error("access token network error for %s: %s", account.email, exc)
        raise RuntimeError(f"获取 access token 网络错误: {exc}") from exc

    if resp.status_code != 200:
        logger.warning(
            "access token failed for %s (scope=%s, status=%d): %s",
            account.email, scope, resp.status_code, resp.text[:200],
        )
        raise RuntimeError(f"获取 access token 失败 (HTTP {resp.status_code})")

    data = resp.json()
    access_token = data.get("access_token")
    if not access_token:
        raise RuntimeError("响应中缺少 access_token")
    return access_token