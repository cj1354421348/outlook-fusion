"""账户 ORM repository：accounts 表读写（PG 主源唯一写路径）。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AccountRepository:
    """所有账户读写必须经此层。禁止在 service 之外直接构造 Account。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> Account | None:
        stmt = select(Account).where(func.lower(Account.email) == email.lower())
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_all(self) -> list[Account]:
        stmt = select(Account).order_by(Account.email)
        return list((await self._session.execute(stmt)).scalars().all())

    async def create(
        self,
        *,
        email: str,
        client_id: str,
        refresh_token_encrypted: str,
        tags: list[str] | None = None,
        note: str | None = None,
        email_protocol: str | None = None,
    ) -> Account:
        account = Account(
            email=email,
            client_id=client_id,
            refresh_token=refresh_token_encrypted,
            status="active",
            tags=tags or [],
            note=note,
            email_protocol=email_protocol,
            refresh_version=0,
            last_refreshed_at=_now(),
        )
        self._session.add(account)
        return account

    async def update_refresh_token(self, email: str, refresh_token_encrypted: str) -> Account | None:
        """token 轮换更新：refresh_version 乐观锁自增（防并发刷新互踩）。"""
        stmt = (
            update(Account)
            .where(func.lower(Account.email) == email.lower())
            .values(
                refresh_token=refresh_token_encrypted,
                refresh_version=Account.refresh_version + 1,
                last_refreshed_at=_now(),
            )
            .returning(Account)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def mark_status(self, email: str, status: str, reason: str | None = None) -> Account | None:
        stmt = (
            update(Account)
            .where(func.lower(Account.email) == email.lower())
            .values(status=status, status_reason=reason, status_updated_at=_now())
            .returning(Account)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def update_protocol(self, email: str, protocol: str) -> None:
        await self._session.execute(
            update(Account)
            .where(func.lower(Account.email) == email.lower())
            .values(email_protocol=protocol)
        )

    async def record_token_failure(self, email: str, *, status_code: int | None, error_message: str | None) -> None:
        account = await self.get_by_email(email)
        if account is None:
            return
        failures = dict(account.token_failures or {})
        failures["consecutive_count"] = int(failures.get("consecutive_count", 0)) + 1
        failures["last_failure_at"] = _now().isoformat()
        if status_code is not None:
            failures["last_status_code"] = status_code
        if error_message:
            failures["last_error_message"] = error_message
        account.token_failures = failures
        # 认证类错误(400/401/403)阈值 3，其余 8
        threshold = 3 if status_code in (400, 401, 403) else 8
        if failures["consecutive_count"] >= threshold and account.status != "expired":
            account.status = "expired"
            account.status_reason = "token_expired"
            account.status_updated_at = _now()

    async def record_token_success(self, email: str) -> None:
        account = await self.get_by_email(email)
        if account is None:
            return
        account.token_failures = None
        if account.status == "expired":
            account.status = "active"
            account.status_reason = None
            account.status_updated_at = _now()

    async def delete(self, email: str) -> bool:
        account = await self.get_by_email(email)
        if account is None:
            return False
        await self._session.delete(account)
        return True
