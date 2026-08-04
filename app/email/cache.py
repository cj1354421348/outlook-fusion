"""进程内 TTL 缓存（单 worker 约束下安全）。"""
from __future__ import annotations

import threading
import time
from typing import Any

from app.config import settings


class TTLCache:
    """线程安全 TTL 缓存：值 + 过期时间戳。"""

    def __init__(self, default_ttl: int | None = None) -> None:
        self._default_ttl = default_ttl if default_ttl is not None else settings.CACHE_EXPIRE_SECONDS
        self._data: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            value, expires = entry
            if expires < time.monotonic():
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        ttl = self._default_ttl if ttl is None else ttl
        with self._lock:
            self._data[key] = (value, time.monotonic() + ttl)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear_prefix(self, prefix: str) -> int:
        with self._lock:
            keys = [k for k in self._data if k.startswith(prefix)]
            for k in keys:
                del self._data[k]
            return len(keys)

    def clear_all(self) -> None:
        with self._lock:
            self._data.clear()


email_cache = TTLCache()