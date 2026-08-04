"""OAuth2 手写模块（无 msal）。

当前功能:
- refresh.py: token 刷新交换 + 协议探测（GRAPH vs IMAP）
  - 每个账户用各自的 client_id 续杯（支持购买账号 + 自有账号并存）

TODO(P3): 自有应用 OAuth 授权码流程
  - GET  /oauth/authorize → 生成微软登录 URL（PKCE）
  - GET  /oauth/callback  → 回调处理，拿 refresh_token 入库
  - 场景: 用户注册了自己的 Azure 应用，需要浏览器授权拿 token
  - 实现: 手写 PKCE（code_verifier 存内存 TTL 10min），cookie 只存 state
  - 参考: 项目 A（MS-Graph-Token-Generator）的 main.py 授权码流程
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
