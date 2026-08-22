"""OAuth2 核心：refresh token 交换 + 协议探测。手写，无 msal。"""

from __future__ import annotations

import httpx
from fastapi import HTTPException

from app.accounts.repository import AccountRepository
from app.config import logger, settings
from app.db.models import Account
from app.security.encryption import decrypt_token, encrypt_token

# 协议常量
PROTOCOL_GRAPH = "graph"
PROTOCOL_IMAP = "imap"

# scope 到 protocol 的映射
SCOPE_MAP = {
    settings.GRAPH_SCOPE: PROTOCOL_GRAPH,
    settings.IMAP_SCOPE: PROTOCOL_IMAP,
}

_shared_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(timeout=30.0)
    return _shared_client


async def _refresh(
    client_id: str,
    refresh_token: str,
    scope: str,
) -> tuple[bool, str | None, str | None]:
    """刷新 token 一次。返回 (success, new_refresh_token, error)。"""
    token_url = f"{settings.AUTHORITY}/oauth2/v2.0/token"
    payload = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": scope,
    }
    try:
        client = _get_client()
        resp = await client.post(token_url, data=payload)
        if resp.status_code == 200:
            data = resp.json()
            new_token = data.get("refresh_token")
            return True, new_token or refresh_token, None
        else:
            error_text = resp.text[:200]
            logger.warning("token refresh failed (scope=%s, status=%d): %s", scope, resp.status_code, error_text)
            return False, None, error_text
    except Exception as e:
        logger.error("token refresh network error: %s", e)
        return False, None, str(e)


async def detect_protocol(account: Account) -> str:
    """通过刷新 token 探测协议：先试 GRAPH scope，再试 IMAP scope。"""
    plain_token = decrypt_token(account.refresh_token)

    for scope in [settings.GRAPH_SCOPE, settings.IMAP_SCOPE]:
        ok, new_token, _ = await _refresh(account.client_id, plain_token, scope)
        if ok:
            protocol = SCOPE_MAP[scope]
            logger.info("detected protocol %s for %s", protocol, account.email)
            # 回写新 token
            if new_token and new_token != plain_token:
                encrypted = encrypt_token(new_token)
                account.refresh_token = encrypted
            account.email_protocol = protocol
            account.last_refreshed_at = None  # 由 repo.update_refresh_token 更新
            return protocol

    # 两种 scope 都失败
    raise HTTPException(status_code=401, detail=f"无法探测 {account.email} 的协议")


async def refresh_token_for_account(repo: AccountRepository, account: Account) -> None:
    """刷新单个账户 token，自动选协议。探测后按已知协议刷新。"""
    if not account.email_protocol or account.email_protocol == "auto":
        protocol = await detect_protocol(account)
        await repo.update_protocol(account.email, protocol)
        account.email_protocol = protocol

    plain_token = decrypt_token(account.refresh_token)
    scope = get_scope_for_protocol(account.email_protocol)

    ok, new_token, error = await _refresh(account.client_id, plain_token, scope)
    if not ok:
        await repo.record_token_failure(account.email, status_code=401, error_message=error)
        raise HTTPException(status_code=401, detail=f"token 刷新失败: {error[:100] if error else 'unknown'}")

    encrypted = encrypt_token(new_token or plain_token)
    updated = await repo.update_refresh_token(account.email, encrypted)
    await repo.record_token_success(account.email)
    from app.oauth.access import invalidate_access_token
    invalidate_access_token(account.email)
    if updated is None:
        logger.error("update_refresh_token 返回 None: %s", account.email)


def get_scope_for_protocol(protocol: str | None) -> str:
    if protocol == PROTOCOL_GRAPH:
        return settings.GRAPH_SCOPE
    return settings.IMAP_SCOPE


def get_protocol_for_scope(scope: str) -> str:
    """根据 scope 返回协议类型字符串。"""
    if ".graph." in scope.lower():
        return PROTOCOL_GRAPH
    return PROTOCOL_IMAP