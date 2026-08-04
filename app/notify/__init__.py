"""通知抽象：webhook（沿用项目 A 的 Notify Hub 协议）。"""

from app.notify.service import notify_refresh_summary, send

__all__ = ["send", "notify_refresh_summary"]
