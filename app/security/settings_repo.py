"""app_settings 键值表 repository：API key 哈希 / 健康开关等。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppSetting


class AppSettingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str) -> AppSetting | None:
        return await self._session.get(AppSetting, key)

    async def get_value(self, key: str, default=None):
        setting = await self.get(key)
        return setting.value if setting is not None else default

    async def set(self, key: str, value) -> None:
        setting = await self.get(key)
        if setting is None:
            self._session.add(AppSetting(key=key, value=value))
        else:
            setting.value = value

    async def list_all(self) -> dict[str, object]:
        rows = (await self._session.execute(select(AppSetting))).scalars().all()
        return {r.key: r.value for r in rows}


__all__ = ["AppSettingRepository"]