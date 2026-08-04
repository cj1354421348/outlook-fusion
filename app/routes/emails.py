"""邮件路由：列表 / dual-view / 详情 / 搜索 / CSV 导出。"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.repository import AccountRepository
from app.db.engine import get_session
from app.email import email_service
from app.schemas import DualViewEmailResponse, EmailDetailsResponse, EmailListResponse

router = APIRouter(prefix="/api/emails", tags=["emails"])


def _get_repo(session: AsyncSession = Depends(get_session)) -> AccountRepository:
    return AccountRepository(session)


@router.get("/{email_id}", response_model=EmailListResponse)
async def list_emails(
    email_id: str,
    repo: AccountRepository = Depends(_get_repo),
    folder: str = Query("inbox", pattern="^(inbox|junk|all)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    refresh: bool = Query(False, description="强制刷新缓存"),
) -> EmailListResponse:
    return await email_service.list_emails(repo, email_id, folder, page, page_size, refresh)


@router.get("/{email_id}/dual-view", response_model=DualViewEmailResponse)
async def dual_view(
    email_id: str,
    repo: AccountRepository = Depends(_get_repo),
    inbox_page: int = Query(1, ge=1),
    junk_page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> DualViewEmailResponse:
    return await email_service.dual_view(repo, email_id, inbox_page, junk_page, page_size)


@router.get("/{email_id}/search", response_model=EmailListResponse)
async def search_emails(
    email_id: str,
    repo: AccountRepository = Depends(_get_repo),
    q: str = Query(..., min_length=1, max_length=200, description="搜索关键词"),
    folder: str = Query("all", pattern="^(inbox|junk|all)$"),
    limit: int = Query(50, ge=1, le=200),
) -> EmailListResponse:
    return await email_service.search_emails(repo, email_id, q, folder, limit)


@router.get("/{email_id}/export.csv")
async def export_csv(
    email_id: str,
    repo: AccountRepository = Depends(_get_repo),
    folder: str = Query("inbox", pattern="^(inbox|junk|all)$"),
    page_size: int = Query(500, ge=1, le=1000),
) -> Response:
    """导出邮件列表为 CSV（UTF-8 BOM，Excel 兼容）。"""
    result = await email_service.list_emails(repo, email_id, folder, 1, page_size, refresh=True)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["文件夹", "主题", "发件人", "日期", "UID", "消息ID"])
    for item in result.emails:
        writer.writerow([item.folder, item.subject, item.from_email, item.date, item.uid or "", item.message_id])

    data = "\ufeff" + buf.getvalue()  # BOM for Excel
    filename = f"{email_id}_{folder}.csv"
    return Response(
        content=data.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{email_id}/cache/clear", response_model=dict)
async def clear_cache(
    email_id: str,
) -> dict:
    """清空指定账户的邮件缓存。"""
    cleared = email_service.clear_cache(email_id)
    return {"message": "缓存已清空", "cleared": cleared}