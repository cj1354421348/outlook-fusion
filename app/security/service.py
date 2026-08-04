"""安全服务单例：会话 + 登录限流 + API key。"""
from __future__ import annotations

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import logger, settings
from app.security.api_keys import ApiKeyService
from app.security.rate_limit import FailureRegistry
from app.security.sessions import SessionStore


class SecurityService:
    def __init__(self) -> None:
        self.sessions = SessionStore()
        self.login_failures = FailureRegistry()

    # --- 会话 ---
    def create_session(self, username: str) -> str:
        return self.sessions.create(username)

    def get_session(self, session_id: str | None):
        if not session_id:
            return None
        return self.sessions.get(session_id)

    def destroy_session(self, session_id: str | None) -> None:
        if session_id:
            self.sessions.remove(session_id)

    # --- 登录 ---
    def login(self, request: Request, username: str, password: str) -> str:
        ip = request.client.host if request.client else "unknown"
        if self.login_failures.is_locked(ip):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="登录已被临时锁定")

        if username != settings.APP_USERNAME or password != settings.APP_PASSWORD:
            self.login_failures.register_failure(ip)
            logger.warning("登录失败 %s from %s", username, ip)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

        self.login_failures.reset(ip)
        return self.create_session(username)


security_service = SecurityService()

__all__ = ["SecurityService", "security_service"]