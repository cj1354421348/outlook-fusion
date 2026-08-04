"""API key 管理：只存 SHA256 哈希（PG app_settings），杜绝明文落库。"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app.security.settings_repo import AppSettingRepository

API_KEY_HASH_KEY = "api_key_hash"


def hash_api_key(plain: str) -> str:
    """SHA256 哈希（hex）。比较用 hmac.compare_digest 防时序。"""
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    """生成 48 字符 URL-safe 明文 key（仅此一次展示，之后只存哈希）。"""
    return secrets.token_urlsafe(36)


def verify_api_key(plain: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    return hmac.compare_digest(hash_api_key(plain), stored_hash)


class ApiKeyService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = AppSettingRepository(session)

    async def get_hash(self) -> str | None:
        return await self._repo.get_value(API_KEY_HASH_KEY)

    async def verify(self, plain: str) -> bool:
        stored = await self.get_hash()
        return verify_api_key(plain, stored)

    async def rotate(self) -> str:
        """生成新 key 并覆盖哈希，返回明文（仅此一次）。"""
        plain = generate_api_key()
        await self._repo.set(API_KEY_HASH_KEY, hash_api_key(plain))
        return plain

    async def delete(self) -> None:
        await self._repo.set(API_KEY_HASH_KEY, None)

    async def has_key(self) -> bool:
        return await self.get_hash() is not None


__all__ = ["ApiKeyService", "hash_api_key", "generate_api_key", "verify_api_key"]