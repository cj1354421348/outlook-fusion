"""账户业务服务：所有写操作经此层（PG 事务）。"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

from app.accounts.repository import AccountRepository
from app.security.encryption import encrypt_token


class AccountCreate(BaseModel):
    email: EmailStr
    client_id: str = Field(min_length=1)
    tags: list[str] = []
    note: str | None = None


class AccountService:
    def __init__(self, repository: AccountRepository) -> None:
        self._repo = repository

    async def register(self, payload: AccountCreate, refresh_token: str) -> None:
        """注册账户：refresh_token 加密入库。调用方必须先完成 OAuth 授权拿到 token。"""
        encrypted = encrypt_token(refresh_token)
        await self._repo.create(
            email=payload.email.lower(),
            client_id=payload.client_id,
            refresh_token_encrypted=encrypted,
            tags=payload.tags,
            note=payload.note,
        )

    async def list_accounts(self) -> list[dict]:
        accounts = await self._repo.list_all()
        return [
            {
                "email": a.email,
                "client_id": a.client_id,
                "status": a.status,
                "email_protocol": a.email_protocol,
                "tags": a.tags,
                "note": a.note,
                "last_refreshed_at": a.last_refreshed_at,
            }
            for a in accounts
        ]
