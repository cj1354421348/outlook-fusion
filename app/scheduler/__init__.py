"""调度器：asyncio task 管理（非 subprocess）。P3 定时保活。"""

from app.scheduler.refresh import scheduler

__all__ = ["scheduler"]
