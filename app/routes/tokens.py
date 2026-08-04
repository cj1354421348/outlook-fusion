"""Token 操作路由：刷新 + 协议探测。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.repository import AccountRepository
from app.db.engine import get_session
from app.notify import notify_refresh_summary
from app.oauth import detect_protocol, refresh_token_for_account
from app.scheduler import scheduler
from app.schemas import StatusResponse

router = APIRouter(prefix="/api/tokens", tags=["tokens"])


@router.post("/{email}/refresh", response_model=StatusResponse)
async def refresh_single(email: str, session: AsyncSession = Depends(get_session)) -> StatusResponse:
    """刷新指定账户的 access token（自动选协议，首次自动探测）。"""
    repo = AccountRepository(session)
    account = await repo.get_by_email(email)
    if account is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="账户不存在")

    # 首次或协议未知 → 探测
    if not account.email_protocol or account.email_protocol == "auto":
        protocol = await detect_protocol(account)
        await repo.update_protocol(email, protocol)

    await refresh_token_for_account(repo, account)
    await session.commit()
    return StatusResponse(message=f"Token 刷新成功 (协议: {account.email_protocol})", email=email)


@router.post("/refresh-all", response_model=StatusResponse)
async def refresh_all(session: AsyncSession = Depends(get_session)) -> StatusResponse:
    """批量刷新所有账户（跳过 expired）并发送通知。"""
    repo = AccountRepository(session)
    accounts = await repo.list_all()
    success = 0
    failed = 0

    for account in accounts:
        if account.status == "expired":
            continue
        try:
            if not account.email_protocol or account.email_protocol == "auto":
                protocol = await detect_protocol(account)
                await repo.update_protocol(account.email, protocol)
            await refresh_token_for_account(repo, account)
            success += 1
        except Exception:
            failed += 1

    await session.commit()
    await notify_refresh_summary(success, failed, success + failed)
    return StatusResponse(message=f"刷新完成: 成功 {success}, 失败 {failed}", email="*")


@router.post("/trigger-scheduler", response_model=StatusResponse)
async def trigger_scheduler() -> StatusResponse:
    """手动触发调度器立即执行一轮刷新。"""
    await scheduler.trigger_immediate()
    return StatusResponse(message="调度器已手动触发", email="*")