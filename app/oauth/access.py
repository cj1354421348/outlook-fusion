"""access token 获取与进程内 TTL 缓存：解密 refresh_token → 按协议 scope 换 access_token。"""
from __future__ import annotations

import time
import httpx

from app.config import logger, settings
from app.db.models import Account
from app.oauth.refresh import get_scope_for_protocol
from app.security.encryption import decrypt_token

_shared_client: httpx.AsyncClient | None = None

# (access_token, expires_at_timestamp)
_access_token_cache: dict[str, tuple[str, float]] = {}


def _get_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(timeout=30.0)
    return _shared_client


def invalidate_access_token(email: str) -> None:
    """在 refresh token 更新或 IMAP/Graph 鉴权失败时，清空该账户所有 scope 的缓存。"""
    prefix = f"{email.lower()}:"
    keys_to_del = [k for k in _access_token_cache if k.startswith(prefix)]
    for k in keys_to_del:
        _access_token_cache.pop(k, None)


async def fetch_access_token(
    account: Account,
    protocol: str | None = None,
    force_refresh: bool = False,
) -> str:
    """返回指定协议的 access_token（带内存 TTL 缓存，避免重复网络调用微软接口）。"""
    scope = get_scope_for_protocol(protocol)
    cache_key = f"{account.email.lower()}:{scope}"
    now = time.time()

    # 1. 检查内存缓存是否有效（预留 300 秒缓冲区）
    if not force_refresh and cache_key in _access_token_cache:
        token, expires_at = _access_token_cache[cache_key]
        if now < expires_at:
            return token

    # 2. 缓存未命中或过期，向微软交换新 access_token
    plain = decrypt_token(account.refresh_token)
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
        # 清除旧缓存
        _access_token_cache.pop(cache_key, None)
        raise RuntimeError(f"获取 access token 失败 (HTTP {resp.status_code})")

    data = resp.json()
    access_token = data.get("access_token")
    if not access_token:
        raise RuntimeError("响应中缺少 access_token")

    # 默认 3600 秒，预留 300 秒安全缓冲
    expires_in = int(data.get("expires_in", 3600))
    ttl = max(60, expires_in - 300)
    _access_token_cache[cache_key] = (access_token, now + ttl)

    return access_token