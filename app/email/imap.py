"""异步 IMAP 连接池 + 邮件读取（aioimaplib，XOAUTH2）。前台 office365 / 后台 live 双 host。"""
from __future__ import annotations

import email as _email
import re
from contextlib import asynccontextmanager
from email.message import EmailMessage
from typing import TYPE_CHECKING, AsyncIterator

import aioimaplib
from fastapi import HTTPException

from app.config import logger, settings
from app.email.message import decode_header_value, extract_email_content, extract_sender_initial, format_date
from app.oauth.access import invalidate_access_token
from app.schemas import EmailDetailsResponse, EmailItem, EmailListResponse

if TYPE_CHECKING:
    from app.db.models import Account

HOST_OFFICE365 = settings.IMAP_SERVER_OFFICE365  # outlook.office365.com
HOST_LIVE = settings.IMAP_SERVER_LIVE            # outlook.live.com

_HOSTS = [HOST_OFFICE365, HOST_LIVE]
_HEADER_ID_PATTERN = re.compile(rb"(\d+)\s+\(")

_pool: dict[str, list[aioimaplib.IMAP4_SSL]] = {}
_pool_count: dict[str, int] = {}


async def _connect(email: str, access_token: str, host: str) -> aioimaplib.IMAP4_SSL:
    try:
        client = aioimaplib.IMAP4_SSL(host=host, port=settings.IMAP_PORT, timeout=settings.SOCKET_TIMEOUT)
        await client.wait_hello_from_server()
        resp = await client.xoauth2(email, access_token)
        if resp.result != "OK":
            # 认证失败时立即让缓存的 access_token 失效
            invalidate_access_token(email)
            raise ConnectionError(f"XOAUTH2 认证失败: {resp.result} {resp.lines}")
        return client
    except Exception as exc:  # noqa: BLE001
        logger.error("IMAP 连接失败 %s@%s: %s", email, host, exc)
        raise


async def _get_connection(email: str, access_token: str) -> aioimaplib.IMAP4_SSL:
    """取一个可用连接：先试 office365，失败回退 live；带池复用。"""
    key = email.lower()
    for host in _HOSTS:
        try:
            # 尝试从池中复用
            if key in _pool and _pool[key]:
                while _pool[key]:
                    client = _pool[key].pop()
                    try:
                        resp = await client.noop()
                        if resp.result == "OK":
                            return client
                        await client.logout()
                    except Exception:  # noqa: BLE001
                        pass
                    _pool_count[key] = max(0, _pool_count.get(key, 1) - 1)

            # 新建连接
            if _pool_count.get(key, 0) < settings.MAX_CONNECTIONS:
                client = await _connect(email, access_token, host)
                _pool_count[key] = _pool_count.get(key, 0) + 1
                return client

            raise ConnectionError("达到最大连接数")
        except Exception as exc:  # noqa: BLE001
            logger.warning("office365 连接失败，回退 live: %s", exc)
    raise HTTPException(status_code=500, detail=f"无法连接 {email} 的 IMAP 服务器")


async def _return_connection(email: str, client: aioimaplib.IMAP4_SSL) -> None:
    key = email.lower()
    try:
        _pool.setdefault(key, []).append(client)
    except Exception:  # noqa: BLE001
        try:
            await client.logout()
        except Exception:  # noqa: BLE001
            pass
        _pool_count[key] = max(0, _pool_count.get(key, 1) - 1)


@asynccontextmanager
async def get_imap_client(email: str, access_token: str) -> AsyncIterator[aioimaplib.IMAP4_SSL]:
    """IMAP 连接上下文管理器，强保证连接的安全归还与防泄露。"""
    client = await _get_connection(email, access_token)
    try:
        yield client
    finally:
        await _return_connection(email, client)


async def _select(client: aioimaplib.IMAP4_SSL, folder: str) -> int:
    """SELECT 文件夹，返回邮件数量。readonly=True。"""
    quoted = f'"{folder}"'
    resp = await client.select(quoted, readonly=True)
    if resp.result != "OK":
        if folder == "Junk":
            resp = await client.select('"Junk Email"', readonly=True)
    if resp.result != "OK" or not resp.lines:
        return 0
    try:
        return int(resp.lines[0])
    except (ValueError, TypeError):
        return 0


async def _fetch_header_lines(
    client: aioimaplib.IMAP4_SSL, sequence: str
) -> tuple[dict[bytes, EmailMessage], dict[bytes, str]]:
    """FETCH 头 + UID，返回 (msg_by_seq, uid_by_seq)。"""
    messages: dict[bytes, EmailMessage] = {}
    uids: dict[bytes, str] = {}

    resp = await client.fetch(sequence, "(UID)")
    if resp.result == "OK":
        for entry in resp.lines:
            if not isinstance(entry, tuple) or len(entry) < 2:
                continue
            header = entry[0]
            if isinstance(header, (bytes, bytearray)):
                header = header.decode(errors="ignore")
            m = _HEADER_ID_PATTERN.search(str(header))
            if m:
                um = re.search(r"UID\s+(\d+)", str(header))
                if um:
                    uids[m.group(1).encode()] = um.group(1)

    resp = await client.fetch(
        sequence, "(FLAGS BODY.PEEK[HEADER.FIELDS (SUBJECT DATE FROM MESSAGE-ID)])"
    )
    if resp.result == "OK":
        for entry in resp.lines:
            if not isinstance(entry, tuple) or len(entry) < 2:
                continue
            header, content = entry[0], entry[1]
            if isinstance(header, (bytes, bytearray)):
                header = header.decode(errors="ignore")
            m = _HEADER_ID_PATTERN.search(str(header))
            if m:
                msg_id = m.group(1).encode()
                if isinstance(content, (bytes, bytearray)):
                    raw = bytes(content).split(b"\r\n\r\n", 1)[-1]
                    messages[msg_id] = _email.message_from_bytes(raw)
    return messages, uids


async def list_emails(
    account: Account,
    access_token: str,
    folder: str,
    page: int,
    page_size: int,
) -> EmailListResponse:
    """列出邮件。folder: inbox/junk/all。全局分页（跨 INBOX+Junk 合并）。"""
    try:
        async with get_imap_client(account.email, access_token) as client:
            target = ["INBOX"] if folder == "inbox" else ["Junk"] if folder == "junk" else ["INBOX", "Junk"]

            folder_counts: list[tuple[str, int]] = []
            total = 0
            for fn in target:
                count = await _select(client, fn)
                folder_counts.append((fn, count))
                total += count

            emails_needed = page_size
            emails_to_skip = (page - 1) * page_size
            items: list[EmailItem] = []

            for fn, count in folder_counts:
                if emails_needed <= 0:
                    break
                if count <= emails_to_skip:
                    emails_to_skip -= count
                    continue
                available = count - emails_to_skip
                take = min(emails_needed, available)
                high = count - emails_to_skip
                low = high - take + 1
                emails_to_skip = 0
                emails_needed -= take
                if low < 1:
                    low = 1
                await _select(client, fn)
                messages, uids = await _fetch_header_lines(client, f"{low}:{high}")
                for seq, msg in messages.items():
                    subject = decode_header_value(msg.get("Subject", "(No Subject)"))
                    from_email = decode_header_value(msg.get("From", "(Unknown Sender)"))
                    date = format_date(msg.get("Date", "") or "")
                    items.append(EmailItem(
                        message_id=f"{fn}-{seq.decode()}",
                        folder=fn,
                        subject=subject,
                        from_email=from_email,
                        date=date,
                        sender_initial=extract_sender_initial(from_email),
                        uid=uids.get(seq),
                    ))

            items.sort(key=lambda x: x.date or "", reverse=True)
            return EmailListResponse(
                email_id=account.email, folder_view=folder, page=page, page_size=page_size,
                total_emails=total, emails=items,
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("列出邮件失败 %s: %s", account.email, exc)
        raise HTTPException(status_code=500, detail="获取邮件列表失败") from exc


async def get_email_details(
    account: Account,
    access_token: str,
    folder_name: str,
    msg_id: str,
) -> EmailDetailsResponse:
    """获取单封邮件完整内容（RFC822）。"""
    try:
        async with get_imap_client(account.email, access_token) as client:
            quoted = f'"{folder_name}"' if not folder_name.startswith('"') else folder_name
            resp = await client.select(quoted, readonly=True)
            if resp.result != "OK":
                raise HTTPException(status_code=404, detail="文件夹不存在")

            uid_resp = await client.fetch(msg_id, "(UID)")
            uid = None
            if uid_resp.result == "OK" and uid_resp.lines:
                header = uid_resp.lines[0]
                if isinstance(header, tuple):
                    header = header[0]
                if isinstance(header, (bytes, bytearray)):
                    header = header.decode(errors="ignore")
                um = re.search(r"UID\s+(\d+)", str(header))
                if um:
                    uid = um.group(1)

            fetch_resp = await client.fetch(msg_id, "(RFC822)")
            if fetch_resp.result != "OK" or not fetch_resp.lines:
                raise HTTPException(status_code=404, detail="邮件不存在")

            raw = None
            for entry in fetch_resp.lines:
                if isinstance(entry, tuple) and isinstance(entry[1], (bytes, bytearray)):
                    raw = bytes(entry[1])
                    break
            if raw is None:
                raise HTTPException(status_code=404, detail="邮件不存在")

            msg = _email.message_from_bytes(raw)
            subject = decode_header_value(msg.get("Subject", "(No Subject)"))
            from_email = decode_header_value(msg.get("From", "(Unknown Sender)"))
            to_email = decode_header_value(msg.get("To", "(Unknown Recipient)"))
            date = format_date(msg.get("Date", "") or "")
            body_plain, body_html = extract_email_content(msg)

            return EmailDetailsResponse(
                message_id=f"{folder_name}-{msg_id}",
                subject=subject, from_email=from_email, to_email=to_email, date=date,
                body_plain=body_plain or None, body_html=body_html or None, uid=uid,
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("获取邮件详情失败 %s/%s: %s", account.email, msg_id, exc)
        raise HTTPException(status_code=500, detail="获取邮件详情失败") from exc


async def search_emails(
    account: Account,
    access_token: str,
    query: str,
    folder: str,
    limit: int,
) -> EmailListResponse:
    """IMAP 搜索（SUBJECT/发件人正文）。folder: inbox/junk/all。"""
    try:
        async with get_imap_client(account.email, access_token) as client:
            target = ["INBOX"] if folder == "inbox" else ["Junk"] if folder == "junk" else ["INBOX", "Junk"]
            items: list[EmailItem] = []

            search_cmd = f'OR HEADER SUBJECT "{query}" HEADER FROM "{query}"'
            for fn in target:
                await _select(client, fn)
                resp = await client.search(search_cmd)
                if resp.result != "OK" or not resp.lines or not resp.lines[0]:
                    continue
                ids = resp.lines[0].split()
                ids = ids[-limit:]
                if not ids:
                    continue
                sequence = b",".join(ids).decode()
                messages, uids = await _fetch_header_lines(client, sequence)
                for seq, msg in messages.items():
                    subject = decode_header_value(msg.get("Subject", "(No Subject)"))
                    from_email = decode_header_value(msg.get("From", "(Unknown Sender)"))
                    items.append(EmailItem(
                        message_id=f"{fn}-{seq.decode()}", folder=fn, subject=subject,
                        from_email=from_email, date=format_date(msg.get("Date", "") or ""),
                        sender_initial=extract_sender_initial(from_email), uid=uids.get(seq),
                    ))
                if len(items) >= limit:
                    break

            items = items[:limit]
            items.sort(key=lambda x: x.date or "", reverse=True)
            return EmailListResponse(
                email_id=account.email, folder_view=folder, page=1, page_size=limit,
                total_emails=len(items), emails=items,
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("搜索邮件失败 %s: %s", account.email, exc)
        raise HTTPException(status_code=500, detail="搜索邮件失败") from exc