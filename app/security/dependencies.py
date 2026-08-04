"""FastAPI 认证依赖：require_auth — 会话 cookie 或 API key 任一通过即可。"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import get_session
from app.security.api_keys import ApiKeyService
from app.security.service import security_service


async def require_auth(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> None:
    """认证守卫：优先会话 cookie，其次 X-API-Key 头（哈希比对）。"""
    session_id = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if session_id and security_service.get_session(session_id):
        return

    api_key = request.headers.get(settings.API_KEY_HEADER)
    if api_key and await ApiKeyService(session).verify(api_key):
        return

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未认证：请登录或提供 API key")


__all__ = ["require_auth"]