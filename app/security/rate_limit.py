"""登录限流：按 IP 记录失败次数，超过阈值锁定一段时间。"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass

from app.config import logger, settings


@dataclass
class FailureEntry:
    count: int = 0
    locked_until: float = 0.0


class FailureRegistry:
    def __init__(self) -> None:
        self._store: dict[str, FailureEntry] = defaultdict(FailureEntry)
        self._lock = threading.Lock()

    def register_failure(self, ip: str) -> None:
        with self._lock:
            entry = self._store[ip]
            entry.count += 1
            if entry.count >= settings.LOCK_THRESHOLD:
                entry.locked_until = time.time() + settings.LOCK_DURATION_SECONDS
                logger.warning("IP %s 触发登录锁定 %s 秒", ip, settings.LOCK_DURATION_SECONDS)

    def reset(self, ip: str) -> None:
        with self._lock:
            if ip in self._store:
                self._store[ip] = FailureEntry()

    def is_locked(self, ip: str) -> bool:
        with self._lock:
            entry = self._store.get(ip)
            if entry is None:
                return False
            if entry.locked_until > time.time():
                return True
            if entry.locked_until and entry.locked_until <= time.time():
                self._store[ip] = FailureEntry()
            return False

    def locked_ips(self) -> list[str]:
        with self._lock:
            now = time.time()
            return [ip for ip, e in self._store.items() if e.locked_until > now]


__all__ = ["FailureEntry", "FailureRegistry"]