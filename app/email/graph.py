"""Graph API 邮件读取（httpx 异步）。对应协议 GRAPH。"""
from __future__ import annotations

import httpx
from fastapi import HTTPException

from app.config import logger
from app.email.message import extract_sender_initial, strip_html
from app.schemas import EmailDetailsResponse, EmailItem, EmailListResponse

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


async def _get_json(url: str, access_token: str, params: dict | None = None) -> dict:
    """GET 并解析 JSON，含鉴权头。401/403 → 抛 401（驱动 token 失败处理）。"""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers, params=params)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=500, detail=f"Graph 网络错误: {exc}") from exc

    if resp.status_code in (401, 403):
        raise HTTPException(status_code=401, detail="Graph 访问被拒绝：token 可能已失效")
    if resp.status_code != 200:
        logger.warning("Graph API error (status=%d): %s", resp.status_code, resp.text[:200])
        raise HTTPException(status_code=500, detail="Graph API 请求失败")
    return resp.json()


async def list_emails(
    account_email: str,
    access_token: str,
    folder: str,
    page: int,
    page_size: int,
) -> EmailListResponse:
    """列出收件箱/垃圾邮件。folder: inbox/junk/all。"""
    graph_folder = "inbox"
    if folder.lower() == "junk":
        graph_folder = "junkemail"

    params = {
        "$top": page_size,
        "$skip": (page - 1) * page_size,
        "$select": "id,subject,from,receivedDateTime,isRead,hasAttachments,parentFolderId",
        "$orderby": "receivedDateTime desc",
        "$count": "true",
    }
    data = await _get_json(
        f"{GRAPH_BASE}/me/mailFolders/{graph_folder}/messages", access_token, params
    )
    total = data.get("@odata.count", 0)
    items: list[EmailItem] = []
    for msg in data.get("value", []):
        from_info = (msg.get("from") or {}).get("emailAddress") or {}
        from_email = from_info.get("address", "Unknown")
        items.append(EmailItem(
            message_id=msg.get("id", ""),
            folder=folder,
            subject=msg.get("subject", "(No Subject)"),
            from_email=from_email,
            date=msg.get("receivedDateTime", ""),
            is_read=msg.get("isRead", False),
            has_attachments=msg.get("hasAttachments", False),
            sender_initial=extract_sender_initial(from_info.get("name", "?")),
        ))
    return EmailListResponse(
        email_id=account_email, folder_view=folder, page=page, page_size=page_size,
        total_emails=total, emails=items,
    )


async def get_email_details(
    account_email: str,
    access_token: str,
    message_id: str,
) -> EmailDetailsResponse:
    """获取单封邮件详情（含正文）。"""
    params = {"$select": "id,subject,from,toRecipients,receivedDateTime,body"}
    data = await _get_json(f"{GRAPH_BASE}/me/messages/{message_id}", access_token, params)

    to_list = [r["emailAddress"]["address"] for r in data.get("toRecipients", [])]
    from_info = (data.get("from") or {}).get("emailAddress") or {}
    body = data.get("body") or {}
    is_html = body.get("contentType") == "html"
    content = body.get("content", "")

    return EmailDetailsResponse(
        message_id=data.get("id", message_id),
        subject=data.get("subject", ""),
        from_email=from_info.get("address", ""),
        to_email=", ".join(to_list),
        date=data.get("receivedDateTime", ""),
        body_html=content if is_html else None,
        body_plain=strip_html(content) if is_html else content or None,
    )


async def search_emails(
    account_email: str,
    access_token: str,
    query: str,
    folder: str,
    limit: int,
) -> EmailListResponse:
    """Graph 搜索（$search 需要 'ConsistencyLevel: eventual' 头 / $filter）。"""
    graph_folder = "inbox"
    if folder.lower() == "junk":
        graph_folder = "junkemail"

    params = {
        "$top": limit,
        "$select": "id,subject,from,receivedDateTime,isRead,hasAttachments",
        "$orderby": "receivedDateTime desc",
        "$filter": f"contains(subject, '{query}') or contains(from/emailAddress/address, '{query}')",
    }
    data = await _get_json(
        f"{GRAPH_BASE}/me/mailFolders/{graph_folder}/messages", access_token, params
    )
    total = data.get("@odata.count", 0)
    items: list[EmailItem] = []
    for msg in data.get("value", []):
        from_info = (msg.get("from") or {}).get("emailAddress") or {}
        from_email = from_info.get("address", "Unknown")
        items.append(EmailItem(
            message_id=msg.get("id", ""),
            folder=folder,
            subject=msg.get("subject", "(No Subject)"),
            from_email=from_email,
            date=msg.get("receivedDateTime", ""),
            is_read=msg.get("isRead", False),
            has_attachments=msg.get("hasAttachments", False),
            sender_initial=extract_sender_initial(from_info.get("name", "?")),
        ))
    return EmailListResponse(
        email_id=account_email, folder_view=folder, page=1, page_size=limit,
        total_emails=total, emails=items,
    )