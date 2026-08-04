"""Pydantic 请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class AccountCreateRequest(BaseModel):
    """注册新账户请求（OAuth 授权完成后调用）。"""
    email: EmailStr
    client_id: str = Field(min_length=1)
    refresh_token: str = Field(min_length=1)  # 明文，服务端加密入库
    tags: list[str] = []
    note: str | None = None


class AccountResponse(BaseModel):
    email: str
    client_id: str
    status: str
    email_protocol: str | None
    tags: list
    note: str | None
    last_refreshed_at: datetime | None

    model_config = {"from_attributes": True}


class AccountListResponse(BaseModel):
    total: int
    accounts: list[AccountResponse]


class AccountStatusRequest(BaseModel):
    status: str = Field(pattern=r"^(active|expired|needs_reauth)$")
    reason: str | None = None


class StatusResponse(BaseModel):
    message: str
    email: str


class BatchImportRequest(BaseModel):
    """批量导入：每行 邮箱----密码----client_id----令牌"""
    text: str = Field(min_length=1)


class BatchImportResult(BaseModel):
    success: int
    failed: int
    errors: list[str]


class TokenHealthStatus(BaseModel):
    total: int
    active: int
    expired: int
    needs_reauth: int