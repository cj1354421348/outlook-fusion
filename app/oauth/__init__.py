"""OAuth2 授权码 + PKCE（手写，无 msal）。

本模块提供：
- refresh.py: token 刷新交换 + 协议探测（GRAPH vs IMAP）
- 不需要浏览器 OAuth 授权流程（token 由用户手动导入）
"""

from app.oauth.refresh import (
    PROTOCOL_GRAPH,
    PROTOCOL_IMAP,
    detect_protocol,
    get_protocol_for_scope,
    get_scope_for_protocol,
    refresh_token_for_account,
)

__all__ = [
    "PROTOCOL_GRAPH",
    "PROTOCOL_IMAP",
    "detect_protocol",
    "get_protocol_for_scope",
    "get_scope_for_protocol",
    "refresh_token_for_account",
]
