"""EmailService 编排：协议解析 → access token → provider 分派 → 内存缓存。"""
from __future__ import annotations

from fastapi import HTTPException

from app.accounts.repository import AccountRepository
from app.config import logger
from app.db.models import Account
from app.email import cache as cache_mod
from app.email import graph as graph_provider
from app.email import imap as imap_provider
from app.oauth import PROTOCOL_GRAPH, PROTOCOL_IMAP, detect_protocol
from app.oauth.access import fetch_access_token
from app.schemas import DualViewEmailResponse, EmailDetailsResponse, EmailListResponse


class EmailService:
    """邮件读取业务编排。不复刻旧代码的 DB 缓存（P4 用进程内缓存，单 worker 安全）。"""

    @staticmethod
    def _cache_key(email: str, folder: str, page: int, page_size: int) -> str:
        return f"list:{email}:{folder}:{page}:{page_size}"

    async def _get_active_account(self, repo: AccountRepository, email: str) -> Account:
        account = await repo.get_by_email(email)
        if account is None:
            raise HTTPException(status_code=404, detail="账户不存在")
        if account.status != "active":
            reason = account.status_reason or account.status
            raise HTTPException(status_code=403, detail=f"账户不可用: {reason}")
        return account

    async def _resolve_account_and_token(
        self, repo: AccountRepository, email: str
    ) -> tuple[Account, str, str]:
        """获取可用账户，确保协议已决议（消除 auto 伪状态），返回 (account, protocol, token)。"""
        account = await self._get_active_account(repo, email)
        protocol = account.email_protocol
        if not protocol or protocol == "auto":
            protocol = await detect_protocol(account)
            await repo.update_protocol(account.email, protocol)
            if account.refresh_token:
                await repo.update_refresh_token(account.email, account.refresh_token)
            account.email_protocol = protocol

        token = await fetch_access_token(account, protocol=protocol)
        return account, protocol, token

    async def list_emails(
        self,
        repo: AccountRepository,
        email: str,
        folder: str,
        page: int,
        page_size: int,
        refresh: bool = False,
    ) -> EmailListResponse:
        cache_key = self._cache_key(email, folder, page, page_size)
        if not refresh:
            cached = cache_mod.email_cache.get(cache_key)
            if cached:
                return cached

        account, protocol, token = await self._resolve_account_and_token(repo, email)

        try:
            if protocol == PROTOCOL_GRAPH:
                result = await graph_provider.list_emails(email, token, folder, page, page_size)
            else:
                result = await imap_provider.list_emails(account, token, folder, page, page_size)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("列出邮件失败 %s/%s: %s", email, folder, exc)
            # 回退缓存
            cached = cache_mod.email_cache.get(cache_key)
            if cached:
                return cached
            raise HTTPException(status_code=500, detail="获取邮件列表失败") from exc

        result.from_cache = False
        cache_mod.email_cache.set(cache_key, result)
        return result

    async def get_email_details(
        self,
        repo: AccountRepository,
        email: str,
        message_id: str,
    ) -> EmailDetailsResponse:
        account, protocol, token = await self._resolve_account_and_token(repo, email)

        # message_id 格式: "文件夹-序号"（IMAP）；Graph 原生 id 无分隔符
        folder_name = "INBOX"
        msg_id = message_id
        if "-" in message_id:
            folder_name, msg_id = message_id.split("-", 1)

        try:
            if protocol == PROTOCOL_GRAPH:
                return await graph_provider.get_email_details(email, token, message_id)
            return await imap_provider.get_email_details(account, token, folder_name, msg_id)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("获取详情失败 %s/%s: %s", email, message_id, exc)
            raise HTTPException(status_code=500, detail="获取邮件详情失败") from exc

    async def dual_view(
        self,
        repo: AccountRepository,
        email: str,
        inbox_page: int,
        junk_page: int,
        page_size: int,
    ) -> DualViewEmailResponse:
        inbox = await self.list_emails(repo, email, "inbox", inbox_page, page_size)
        junk = await self.list_emails(repo, email, "junk", junk_page, page_size)
        return DualViewEmailResponse(
            email_id=email,
            inbox_emails=inbox.emails,
            junk_emails=junk.emails,
            inbox_total=inbox.total_emails,
            junk_total=junk.total_emails,
        )

    async def search_emails(
        self,
        repo: AccountRepository,
        email: str,
        query: str,
        folder: str,
        limit: int,
    ) -> EmailListResponse:
        account, protocol, token = await self._resolve_account_and_token(repo, email)

        try:
            if protocol == PROTOCOL_GRAPH:
                return await graph_provider.search_emails(email, token, query, folder, limit)
            return await imap_provider.search_emails(account, token, query, folder, limit)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("搜索邮件失败 %s: %s", email, exc)
            raise HTTPException(status_code=500, detail="搜索邮件失败") from exc

    def clear_cache(self, email: str | None = None) -> int:
        prefix = f"list:{email}:" if email else ""
        return cache_mod.email_cache.clear_prefix(prefix) if email else cache_mod.email_cache.clear_all()


email_service = EmailService()