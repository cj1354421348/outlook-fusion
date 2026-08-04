"""Web 路由：登录页 / 首页 + 登录登出 API。server-rendered UI。"""
from __future__ import annotations

from fastapi import APIRouter, Request, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from app.config import settings
from app.security.service import security_service

router = APIRouter(tags=["web"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.get("/")
async def root(request: Request):
    session_id = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session_id or not security_service.get_session(session_id):
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return FileResponse("static/index.html")


@router.get("/login")
async def login_page(request: Request):
    session_id = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if session_id and security_service.get_session(session_id):
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return FileResponse("static/login.html")


@router.post("/api/auth/login")
async def login(body: LoginRequest, request: Request):
    session_id = security_service.login(request, body.username, body.password)
    response = JSONResponse({"message": "登录成功"})
    response.set_cookie(
        settings.SESSION_COOKIE_NAME,
        session_id,
        httponly=True,
        samesite="lax",
        max_age=settings.SESSION_TTL_SECONDS,
    )
    return response


@router.post("/api/auth/logout")
async def logout(request: Request):
    session_id = request.cookies.get(settings.SESSION_COOKIE_NAME)
    security_service.destroy_session(session_id)
    response = JSONResponse({"message": "已退出"})
    response.delete_cookie(settings.SESSION_COOKIE_NAME)
    return response