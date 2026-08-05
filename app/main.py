"""Outlook Fusion 入口：FastAPI 应用 + lifespan + 单 worker 断言。"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.config import logger
from app.routes.accounts import router as accounts_router
from app.routes.admin import router as admin_router
from app.routes.emails import router as emails_router
from app.routes.tokens import router as tokens_router
from app.routes.web import router as web_router
from app.scheduler import scheduler
from app.scheduler.keepalive import keepalive

APP_VERSION = "0.1.0"


def _print_banner() -> None:
    """启动横幅：打印版本号/commit/运行环境，便于云端确认部署版本。"""
    git_sha = os.getenv("GIT_SHA", "unknown")[:12]
    git_ref = os.getenv("GIT_REF", "unknown")
    port = os.getenv("PORT", "8000")
    keepalive_state = "ENABLED" if keepalive.enabled else "DISABLED (需手动设置 KEEPALIVE_URL)"
    print(
        "=" * 64,
        f"  Outlook Fusion v{APP_VERSION}",
        f"  git: {git_ref} @ {git_sha}",
        f"  port: {port} | keepalive: {keepalive_state}",
        f"  db: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else settings.DATABASE_URL}",
        "=" * 64,
        sep="\n",
        flush=True,
    )


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
    _print_banner()
    _assert_single_worker()
    scheduler.start()
    keepalive.start()
    logger.info("Outlook Fusion started (scheduler enabled, interval=%sh)", settings.REFRESH_INTERVAL_HOURS)
    yield
    await keepalive.stop()
    await scheduler.stop()
    logger.info("Outlook Fusion shutdown complete")


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
app.include_router(emails_router)
app.include_router(admin_router)
app.include_router(web_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")), workers=1)
