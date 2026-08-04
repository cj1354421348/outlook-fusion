"""ORM 模型：accounts / token_events / notify_targets / app_settings。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, JSON, Integer, Text
from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Account(Base, TimestampMixin):
    """邮箱账户主表。email 唯一，大小写归一化。"""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet 密文
    # 允许明文 password? 不。纯 OAuth 无密码。
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_protocol: Mapped[str | None] = mapped_column(Text, nullable=True)  # graph_api/imap_office365/imap_live/auto
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # type: ignore[assignment]
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_failures: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)  # type: ignore[assignment]
    refresh_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TokenEvent(Base):
    """token 操作审计：刷新/失效/授权/重授权。"""

    __tablename__ = "token_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)  # refresh_success/refresh_fail/mark_expired/reauth
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NotifyTarget(Base, TimestampMixin):
    """通知渠道：webhook/telegram 等。"""

    __tablename__ = "notify_targets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(Text, nullable=False)  # webhook
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)  # type: ignore[assignment]
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class AppSetting(Base):
    """键值配置：API key 哈希 / token 健康开关与间隔 等。"""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)