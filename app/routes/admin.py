"""管理路由：API key 管理 + 安全状态（需登录会话）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import get_session
from app.security.api_keys import ApiKeyService
from app.security.service import security_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_session(request: Request) -> None:
    session_id = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session_id or not security_service.get_session(session_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")


@router.get("/security/status")
async def security_status(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    """安全状态：是否配置 API key、锁定 IP 列表。仅登录会话可查。"""
    _require_session(request)
    api_keys = ApiKeyService(session)
    return {
        "api_key_configured": await api_keys.has_key(),
        "locked_ips": security_service.login_failures.locked_ips(),
        "lock_threshold": settings.LOCK_THRESHOLD,
        "lock_duration_seconds": settings.LOCK_DURATION_SECONDS,
    }


@router.post("/api-key/rotate")
async def rotate_api_key(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """轮换 API key：生成新明文（仅此一次展示），覆盖存储哈希。"""
    _require_session(request)
    plain = await ApiKeyService(session).rotate()
    return {"api_key": plain, "message": "新 API key 已生成（仅展示一次，请立即保存）"}


@router.delete("/api-key")
async def delete_api_key(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """删除 API key。"""
    _require_session(request)
    await ApiKeyService(session).delete()
    return {"message": "API key 已删除"}