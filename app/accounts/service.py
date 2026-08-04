"""账户业务服务：所有写操作经此层（PG 事务）。"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

from app.accounts.repository import AccountRepository
from app.config import logger
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
        """注册账户：refresh_token 加密入库。"""
        encrypted = encrypt_token(refresh_token)
        await self._repo.create(
            email=payload.email.lower(),
            client_id=payload.client_id,
            refresh_token_encrypted=encrypted,
            tags=payload.tags,
            note=payload.note,
        )

    async def batch_import(self, text: str) -> dict:
        """批量导入：每行格式 邮箱----密码----client_id----令牌"""
        lines = text.strip().splitlines()
        success = 0
        failed = 0
        errors: list[str] = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            parts = line.split("----")
            if len(parts) != 4:
                errors.append(f"格式错误(需4段): {line[:60]}...")
                failed += 1
                continue

            email, password, client_id, refresh_token = parts
            email = email.strip()
            client_id = client_id.strip()
            refresh_token = refresh_token.strip()

            if not email or not client_id or not refresh_token:
                errors.append(f"必填字段缺失: {line[:60]}...")
                failed += 1
                continue

            try:
                encrypted = encrypt_token(refresh_token)
                await self._repo.create(
                    email=email.lower(),
                    client_id=client_id,
                    refresh_token_encrypted=encrypted,
                    email_protocol="auto",  # 首次刷新时自动探测 GRAPH vs IMAP
                )
                success += 1
            except Exception as e:
                logger.error("批量导入失败 %s: %s", email, e)
                errors.append(f"{email}: {e}")
                failed += 1

        return {"success": success, "failed": failed, "errors": errors}

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

    async def mark_status(self, email: str, status: str, reason: str | None = None) -> None:
        account = await self._repo.mark_status(email, status, reason)
        if account is None:
            raise ValueError(f"账户不存在: {email}")

    async def delete(self, email: str) -> bool:
        return await self._repo.delete(email)

    async def health_summary(self) -> dict:
        accounts = await self._repo.list_all()
        total = len(accounts)
        active = sum(1 for a in accounts if a.status == "active")
        expired = sum(1 for a in accounts if a.status == "expired")
        needs_reauth = sum(1 for a in accounts if a.status == "needs_reauth")
        return {"total": total, "active": active, "expired": expired, "needs_reauth": needs_reauth}
