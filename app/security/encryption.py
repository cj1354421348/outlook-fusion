"""凭据加密：Fernet。refresh_token 绝不明文落库。"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

_fernet: Fernet | None = None
_fernet_old: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        if not settings.TOKEN_ENCRYPTION_KEY:
            raise RuntimeError("TOKEN_ENCRYPTION_KEY 未配置（cryptography.fernet.Fernet.generate_key()）")
        _fernet = Fernet(settings.TOKEN_ENCRYPTION_KEY.encode())
    return _fernet


def _get_fernet_old() -> Fernet | None:
    """轮换期旧 key 双读。"""
    global _fernet_old
    if settings.TOKEN_ENCRYPTION_KEY_OLD and _fernet_old is None:
        _fernet_old = Fernet(settings.TOKEN_ENCRYPTION_KEY_OLD.encode())
    return _fernet_old or None


def encrypt_token(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    f = _get_fernet()
    try:
        return f.decrypt(encrypted.encode()).decode()
    except InvalidToken:
        old = _get_fernet_old()
        if old is not None:
            return old.decrypt(encrypted.encode()).decode()
        raise