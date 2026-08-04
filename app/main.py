"""Outlook Fusion 入口：FastAPI 应用 + lifespan + 单 worker 断言。"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routes.accounts import router as accounts_router
from app.routes.tokens import router as tokens_router


def _assert_single_worker() -> None:
    """单实例硬约束：进程内缓存/会话/连接池/刷新锁均依赖单一进程。"""
    workers = os.getenv("WORKERS", os.getenv("WEB_CONCURRENCY", ""))
    if workers and workers not in ("", "1", "0"):
        raise RuntimeError(
            f"Outlook Fusion 必须单 worker 运行（当前 WORKERS={workers}）。"
            "内存缓存、会话、IMAP 连接池、per-account 刷新锁均为进程内状态。"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _assert_single_worker()
    # TODO(P3): 启动 TokenHealthScheduler / RefreshScheduler
    yield
    # TODO(P3): 关闭调度器


app = FastAPI(
    title="Outlook Fusion API",
    description="Outlook 邮箱账户全生命周期管理：OAuth token 保活 + 邮件读取",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS：仅同源或白名单（禁 *，防 B 项目的 allow_origins=["*"]+credentials 组合漏洞）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.APP_NAME}


app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(accounts_router)
app.include_router(tokens_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")), workers=1)
