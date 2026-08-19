"""邮件解析工具：header 解码 / 正文提取 / 日期格式化 / 发件人首字母。"""
from __future__ import annotations

import base64
import email
import re
from email.header import decode_header
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup, Comment

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


# ---------- HTML → 纯文本（正规解析，对齐微软 bodyPreview 质量） ----------

# 块级元素：提取后自成一行，保持段落结构
_BLOCK_TAGS = [
    "p", "div", "br", "hr", "li", "ul", "ol", "table", "tr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "pre", "section", "article", "header", "footer",
    "address", "fieldset", "form", "figure",
]
# 不可见内容：直接丢弃（Outlook 服务器注入的响应式样式就藏在 <style> 里）
_SKIP_TAGS = ["style", "script", "head", "title", "noscript", "meta", "link"]


def html_to_text(html: str) -> str:
    """HTML 正文 → 可读纯文本，对齐微软 bodyPreview 的解析规则：

    - `<style>`/`<script>`/`<head>`/注释全部丢弃（Outlook 注入的响应式样式不再混进正文）
    - HTML 实体正确解码（`&amp;` → `&`，`&nbsp;` → 空格）
    - 块级元素自动换行（p/div/li/table/标题...），段落清晰
    - `<img>` 用 `alt` 属性作为文本替代（微软规则；无 `alt` 则无输出）
    - 链接保留：`<a>` 有锚文本 → "文本 (url)"；锚是图片且无 alt → 直接保留 url
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(_SKIP_TAGS):
        tag.decompose()
    for node in soup.find_all(string=lambda s: isinstance(s, Comment)):
        node.extract()

    # 微软 bodyPreview 规则：图片的文本替代是 alt 属性，无 alt 则忽略
    for img in soup.find_all("img"):
        alt = (img.get("alt") or "").strip()
        img.replace_with(alt)

    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        text = a.get_text(" ", strip=True)
        if not text and href:
            a.replace_with(href)  # 锚是 <img> 之类的验证按钮：留 URL
        elif text and href and href != text and not href.startswith(("mailto:", "tel:", "#")):
            a.replace_with(f"{text} ({href})")
        else:
            a.replace_with(text or href)

    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_after("\n")

    text = soup.get_text(" ")  # get_text 自动解码实体
    text = text.replace("\xa0", " ")  # &nbsp; → 空格
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def extract_email_content(msg: email.message.EmailMessage) -> tuple[str, str]:
    """递归提取正文，返回 (body_plain, body_html)。
    支持提取 multipart/related 内嵌图片 (Content-ID) 并转为 data: URI 注入 HTML。
    纯 HTML 邮件时 body_plain 为 html_to_text 规范解析后的纯文本。
    """
    body_plain = ""
    body_html = ""
    cid_map: dict[str, str] = {}

    try:
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                cid_header = part.get("Content-ID")
                disposition = str(part.get("Content-Disposition", "")).lower()

                # 收集内嵌图片/附件 CID
                if cid_header:
                    raw_cid = cid_header.strip("<> \t\r\n")
                    payload = part.get_payload(decode=True)
                    if raw_cid and payload:
                        b64_data = base64.b64encode(payload).decode("ascii")
                        cid_map[raw_cid] = f"data:{ctype};base64,{b64_data}"

                if "attachment" in disposition and not cid_header:
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

    # 替换 HTML 中的 cid: 引用为 data:URI
    if cid_map and body_html:
        for cid_val, data_uri in cid_map.items():
            pattern = re.compile(rf"cid:(?:<{re.escape(cid_val)}>|{re.escape(cid_val)})", re.IGNORECASE)
            body_html = pattern.sub(data_uri, body_html)

    body_plain = body_plain.strip()
    body_html = body_html.strip()
    # 纯 HTML 邮件：正规解析为纯文本作为回退
    if not body_plain and body_html:
        body_plain = html_to_text(body_html)
    return body_plain, body_html


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


__all__ = ["decode_header_value", "extract_email_content", "extract_sender_initial", "format_date", "html_to_text"]