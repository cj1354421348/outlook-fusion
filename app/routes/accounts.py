"""账户路由：CRUD + 状态管理。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.repository import AccountRepository
from app.accounts.service import AccountCreate, AccountService
from app.db.engine import get_session
from app.security.dependencies import require_auth
from app.schemas import (
    AccountCreateRequest,
    AccountListResponse,
    AccountResponse,
    AccountStatusRequest,
    BatchImportRequest,
    BatchImportResult,
    StatusResponse,
    TokenHealthStatus,
)

router = APIRouter(prefix="/api/accounts", tags=["accounts"], dependencies=[Depends(require_auth)])


def _get_service(session: AsyncSession = Depends(get_session)) -> AccountService:
    return AccountService(AccountRepository(session))


@router.get("", response_model=AccountListResponse)
async def list_accounts(service: AccountService = Depends(_get_service)) -> AccountListResponse:
    accounts = await service.list_accounts()
    return AccountListResponse(
        total=len(accounts),
        accounts=[AccountResponse.model_validate(a) for a in accounts],
    )


@router.post("", response_model=StatusResponse, status_code=201)
async def register_account(
    body: AccountCreateRequest,
    service: AccountService = Depends(_get_service),
) -> StatusResponse:
    """注册新账户：refresh_token 加密入库。调用前必须已完成 OAuth 授权拿 token。"""
    payload = AccountCreate(email=body.email, client_id=body.client_id, tags=body.tags, note=body.note)
    await service.register(payload, body.refresh_token)
    return StatusResponse(message="账户注册成功", email=body.email)


@router.post("/batch", response_model=BatchImportResult, status_code=201)
async def batch_import_accounts(
    body: BatchImportRequest,
    service: AccountService = Depends(_get_service),
) -> BatchImportResult:
    """批量导入：每行 邮箱----密码----client_id----令牌"""
    result = await service.batch_import(body.text)
    return BatchImportResult(**result)


@router.delete("/{email}", response_model=StatusResponse)
async def delete_account(
    email: str,
    service: AccountService = Depends(_get_service),
) -> StatusResponse:
    if not await service.delete(email):
        raise HTTPException(status_code=404, detail="账户不存在")
    return StatusResponse(message="账户已删除", email=email)


@router.put("/{email}/status", response_model=StatusResponse)
async def set_account_status(
    email: str,
    body: AccountStatusRequest,
    service: AccountService = Depends(_get_service),
) -> StatusResponse:
    await service.mark_status(email, body.status, body.reason)
    return StatusResponse(message=f"状态已更新为 {body.status}", email=email)


@router.get("/_health", response_model=TokenHealthStatus)
async def token_health_summary(service: AccountService = Depends(_get_service)) -> TokenHealthStatus:
    stats = await service.health_summary()
    return TokenHealthStatus(**stats)