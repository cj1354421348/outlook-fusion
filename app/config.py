"""应用配置：pydantic-settings 集中管理所有环境变量。"""

from __future__ import annotations

import logging
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 显式配置：确保 INFO 级日志在所有运行环境（含 uvicorn dictConfig 后）可见
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    force=True,
)
logger = logging.getLogger("outlook_fusion")
logger.setLevel(logging.INFO)
logger.disabled = False  # 防止 uvicorn dictConfig 的 disable_existing_loggers 吞掉


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- 基础 ---
    APP_NAME: str = "Outlook Fusion"
    DEBUG: bool = False

    # --- 数据库（PG 主源）---
    DATABASE_URL: str = "postgresql+asyncpg://outlook:outlook@localhost:5432/outlook_fusion"

    # --- 安全 ---
    SECRET_KEY: str = ""  # cookie 签名，secrets.token_urlsafe(32)
    TOKEN_ENCRYPTION_KEY: str = ""  # Fernet key，cryptography.fernet.Fernet.generate_key()
    TOKEN_ENCRYPTION_KEY_OLD: str = ""  # 轮换期旧 key（双读）
    APP_USERNAME: str = "admin"
    APP_PASSWORD: str = "admin"
    LOCK_THRESHOLD: int = 5
    LOCK_DURATION_SECONDS: int = 3600

    # --- 会话 / API key ---
    SESSION_COOKIE_NAME: str = "of_session"
    SESSION_TTL_SECONDS: int = 86400  # 24h 无活动过期
    API_KEY_HEADER: str = "X-API-Key"

    # --- OAuth / Microsoft ---
    AUTHORITY: str = "https://login.microsoftonline.com/consumers"
    DEFAULT_CLIENT_ID: str = ""
    REDIRECT_BASE_URL: str = "http://localhost:8000"  # 开发期隧道 URL；部署期切公网域名
    OAUTH_CALLBACK_PATH: str = "/auth/callback"
    # 授权码流请求的 scope（无 offline_access，MSAL 会自动加；手写则显式包含）
    OAUTH_SCOPE: str = "offline_access https://outlook.office.com/IMAP.AccessAsUser.All Mail.Read"
    GRAPH_SCOPE: str = "https://graph.microsoft.com/.default offline_access"
    IMAP_SCOPE: str = "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"

    # --- IMAP ---
    IMAP_SERVER_OFFICE365: str = "outlook.office365.com"
    IMAP_SERVER_LIVE: str = "outlook.live.com"
    IMAP_PORT: int = 993
    MAX_CONNECTIONS: int = 5
    CONNECTION_TIMEOUT: int = 30
    SOCKET_TIMEOUT: int = 15

    # --- 调度 ---
    REFRESH_INTERVAL_HOURS: int = 24  # 保活间隔，上限 168（7 天）
    TOKEN_HEALTH_ENABLED: bool = True

    # --- 平台保活（Render 等免费实例防休眠）---
    RENDER_EXTERNAL_URL: str = ""  # Render 自动注入的公网地址（非 Render 平台留空）
    KEEPALIVE_URL: str = ""  # 手动指定公网 URL（留空则用 RENDER_EXTERNAL_URL）
    KEEPALIVE_MIN_INTERVAL_MINUTES: int = 1  # 随机间隔下限（分钟）
    KEEPALIVE_INTERVAL_MINUTES: int = 10  # 随机间隔上限（分钟），上限须 < 平台休眠阈值（Render = 15min）

    # --- 通知 ---
    NOTIFY_API_URL: str = ""
    NOTIFY_KEY: str = ""

    # --- 缓存 ---
    CACHE_EXPIRE_SECONDS: int = 60

    # --- CORS ---
    CORS_ORIGINS: str = ""  # 逗号分隔；空 = 仅同源

    @field_validator("REFRESH_INTERVAL_HOURS")
    @classmethod
    def _validate_refresh_interval(cls, v: int) -> int:
        if v < 1 or v > 168:
            raise ValueError("REFRESH_INTERVAL_HOURS must be in [1, 168]")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def redirect_uri(self) -> str:
        return f"{self.REDIRECT_BASE_URL.rstrip('/')}{self.OAUTH_CALLBACK_PATH}"

    @property
    def oauth_scope_list(self) -> list[str]:
        return self.OAUTH_SCOPE.split()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
