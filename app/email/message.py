"""邮件解析工具：header 解码 / 正文提取 / 日期格式化 / 发件人首字母。"""
from __future__ import annotations

import email
import re
from email.header import decode_header
from email.utils import parsedate_to_datetime

from app.config import logger


def decode_header_value(header_value: str) -> str:
    """解码 RFC2047 编码的 header（如 =?utf-8?B?...?=）。"""
    if not header_value:
        return ""
    try:
        parts = decode_header(str(header_value))
        out = ""
        for chunk, charset in parts:
            if isinstance(chunk, bytes):
                try:
                    out += chunk.decode(charset or "utf-8", errors="replace")
                except (LookupError, UnicodeDecodeError):
                    out += chunk.decode("utf-8", errors="replace")
            else:
                out += str(chunk)
        return out.strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("header 解码失败 %r: %s", header_value, exc)
        return str(header_value) if header_value else ""


def extract_email_content(msg: email.message.EmailMessage) -> tuple[str, str]:
    """递归提取正文，返回 (body_plain, body_html)。"""
    body_plain = ""
    body_html = ""

    try:
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if "attachment" in str(part.get("Content-Disposition", "")).lower():
                    continue
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                charset = part.get_content_charset() or "utf-8"
                try:
                    content = payload.decode(charset, errors="replace")
                except (LookupError, UnicodeDecodeError):
                    content = payload.decode("utf-8", errors="replace")
                if ctype == "text/plain" and not body_plain:
                    body_plain = content
                elif ctype == "text/html" and not body_html:
                    body_html = content
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                try:
                    content = payload.decode(charset, errors="replace")
                except (LookupError, UnicodeDecodeError):
                    content = payload.decode("utf-8", errors="replace")
                if msg.get_content_type() == "text/html":
                    body_html = content
                else:
                    body_plain = content
    except Exception as exc:  # noqa: BLE001
        logger.error("正文提取失败: %s", exc)

    return body_plain.strip(), body_html.strip()


def extract_sender_initial(from_email: str) -> str:
    match = re.search(r"([a-zA-Z])", from_email)
    return match.group(1).upper() if match else "?"


def format_date(date_str: str) -> str:
    """RFC2822 日期 → ISO8601 字符串；解析失败回退当前时间。"""
    try:
        if date_str:
            dt = parsedate_to_datetime(date_str)
            return dt.astimezone().isoformat()
    except Exception:  # noqa: BLE001
        pass
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).astimezone().isoformat()


__all__ = ["decode_header_value", "extract_email_content", "extract_sender_initial", "format_date"]