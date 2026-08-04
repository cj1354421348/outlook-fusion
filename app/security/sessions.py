"""会话存储：进程内 SessionStore（单 worker 硬约束下安全）。"""
from __future__ import annotations

import secrets
import threading
import time
from typing import Any

from app.config import settings


class SessionStore:
    """内存会话表：secrets.token_urlsafe(32) 会话 ID + 最后活跃时间（滑动过期）。"""

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self, username: str) -> str:
        session_id = secrets.token_urlsafe(32)
        now = time.time()
        with self._lock:
            self._sessions[session_id] = {
                "username": username,
                "created_at": now,
                "last_active": now,
            }
        return session_id

    def get(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            now = time.time()
            if now - session["last_active"] > settings.SESSION_TTL_SECONDS:
                del self._sessions[session_id]
                return None
            session["last_active"] = now
            return session

    def remove(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


__all__ = ["SessionStore"]