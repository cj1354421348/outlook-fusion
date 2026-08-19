"""邮件读取模块（P4）：IMAP/Graph 双协议，无发送链路。

保持轻量：不聚合导出 service，避免 import 任意子模块（如 message）时
触发 service → AccountRepository 的整条 DB 依赖链。需要 service 时直接
`from app.email.service import email_service`。
"""
