"""通知抽象：webhook 推送（沿用项目 A 的 Notify Hub 协议）。"""

from __future__ import annotations

import json

import httpx

from app.config import logger, settings


async def send(title: str, content: str, level: str = "info") -> bool:
    """发送通知到 webhook。level: info/success/warning/error。"""
    if not settings.NOTIFY_API_URL:
        logger.debug("NOTIFY_API_URL not configured, skip notification")
        return False

    payload = {
        "project_name": "Outlook Fusion",
        "title": title,
        "content": content,
        "level": level,
    }
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if settings.NOTIFY_KEY:
        headers["X-Project-Key"] = settings.NOTIFY_KEY

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(settings.NOTIFY_API_URL, json=payload, headers=headers)
            if resp.status_code == 403:
                logger.warning("Notify auth failed: check NOTIFY_KEY")
                return False
            logger.info("Notification sent: title=%s level=%s", title, level)
            return True
    except Exception as e:
        logger.error("Notification failed: %s", e)
        return False


async def notify_refresh_summary(success: int, failed: int, total: int) -> None:
    """发送刷新汇总通知。"""
    from datetime import datetime

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    level = "success" if failed == 0 else ("error" if success == 0 else "warning")
    title = f"{'✅' if level == 'success' else '⚠️'} Token 保活 {level}"
    content = (
        f"执行时间: {ts}\n"
        f"成功: {success}/{total}\n"
        f"失败: {failed}/{total}\n"
        f"状态: {'正常' if level == 'success' else '部分失败，请检查'} "
    )
    await send(title, content, level)