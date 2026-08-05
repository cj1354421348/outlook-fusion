"""保活任务：PaaS 免费实例（Render 等）15 分钟无入站流量会休眠。

原理：Render 免费实例按「入站流量」判定活跃——容器内 ping localhost 不算，
必须请求经过 Render 入口的公网 URL。Render 会自动注入 RENDER_EXTERNAL_URL，
应用定时自 ping 该公网地址，阻止休眠。仅在有公网 URL 时启用。

间隔在 [KEEPALIVE_MIN_INTERVAL, KEEPALIVE_INTERVAL] 之间随机，避免固定节奏。
"""
from __future__ import annotations

import asyncio
import logging
import random

import httpx

from app.config import settings

logger = logging.getLogger("outlook_fusion")


class KeepAlive:
    """定时请求自身公网 URL，阻止平台按空闲休眠。"""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop: asyncio.Event | None = None
        # Render 自动注入 RENDER_EXTERNAL_URL；KEEPALIVE_URL 可手动覆盖
        self._base_url = (settings.KEEPALIVE_URL or settings.RENDER_EXTERNAL_URL or "").rstrip("/")
        self._min_interval = settings.KEEPALIVE_MIN_INTERVAL_MINUTES * 60
        self._max_interval = settings.KEEPALIVE_INTERVAL_MINUTES * 60

    @property
    def enabled(self) -> bool:
        return bool(self._base_url)

    def _next_interval(self) -> int:
        return random.randint(self._min_interval, self._max_interval)

    def start(self) -> None:
        if not self.enabled:
            logger.info("KeepAlive disabled (KEEPALIVE_URL / RENDER_EXTERNAL_URL 为空)")
            return
        if self._task is not None and not self._task.done():
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "KeepAlive started -> %s every %s-%ss (random)",
            self._base_url, self._min_interval, self._max_interval,
        )

    async def stop(self) -> None:
        if self._stop:
            self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("KeepAlive stopped")

    async def _run_loop(self) -> None:
        try:
            while not self._stop.is_set():  # type: ignore[union-attr]
                await asyncio.sleep(self._next_interval())
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.get(f"{self._base_url}/health")
                    logger.info("KeepAlive ping %s -> %s", self._base_url, resp.status_code)
                except Exception:
                    logger.warning("KeepAlive ping failed，%s 秒后重试", self._max_interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("KeepAlive crashed")


keepalive = KeepAlive()
