"""调度器：asyncio task 生命周期管理。P3 定时保活 + 健康检查。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.accounts.repository import AccountRepository
from app.config import logger, settings
from app.db.engine import SessionFactory
from app.oauth import refresh_token_for_account, detect_protocol


class RefreshScheduler:
    """每日保活：遍历所有 active 账户，逐个刷新 token。"""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop: asyncio.Event | None = None
        self._last_run: datetime | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("RefreshScheduler started (interval=%sh)", settings.REFRESH_INTERVAL_HOURS)

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
        logger.info("RefreshScheduler stopped")

    @property
    def last_run(self) -> datetime | None:
        return self._last_run

    async def _run_loop(self) -> None:
        retry_delay = 60  # 初始重试间隔 60 秒
        max_retry = 3600  # 最多到 1 小时
        try:
            while not self._stop.is_set():  # type: ignore[union-attr]
                # 先等一个间隔再跑，避免启动时立即触发
                interval = settings.REFRESH_INTERVAL_HOURS * 3600
                try:
                    await asyncio.wait_for(asyncio.shield(asyncio.sleep(interval)), timeout=interval)
                except asyncio.CancelledError:
                    break

                try:
                    await self._run_once()
                    retry_delay = 60  # 成功后重置
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("RefreshScheduler: 刷新失败，%s 秒后重试", retry_delay)
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("RefreshScheduler crashed")

    async def trigger_immediate(self) -> None:
        """手动触发一次刷新（不打断计时器）。"""
        await self._run_once()

    async def _run_once(self) -> None:
        logger.info("RefreshScheduler: start refresh cycle")
        async with SessionFactory() as session:
            repo = AccountRepository(session)
            accounts = await repo.list_all()
            active = [a for a in accounts if a.status == "active"]

            success = 0
            failed = 0
            for account in active:
                try:
                    if not account.email_protocol or account.email_protocol == "auto":
                        await detect_protocol(account)
                        await repo.update_protocol(account.email, account.email_protocol or "imap")
                    await refresh_token_for_account(repo, account)
                    success += 1
                    await asyncio.sleep(1)  # 限流
                except Exception as e:
                    logger.warning("Scheduler refresh failed for %s: %s", account.email, e)
                    repo._session.add(account)  # refresh_token_for_account 可能已改状态
                    failed += 1

            await session.commit()
            self._last_run = datetime.now(timezone.utc)
            logger.info("RefreshScheduler: done — success=%d failed=%d total=%d", success, failed, len(active))


scheduler = RefreshScheduler()