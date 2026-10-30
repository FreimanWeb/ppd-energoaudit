"""Парольный доступ для React и других HTTP-клиентов."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..services.authentication import (
    SESSION_TTL,
    configured_password,
    issue_session,
    matches,
    valid_session,
)


router = APIRouter(prefix="/auth", tags=["authentication"])
COOKIE_NAME = "ppd_session"
_PUBLIC_PATHS = {"/health", "/auth/session", "/auth/login", "/auth/logout"}


class LoginRequest(BaseModel):
    password: str = Field(max_length=4096)


class SessionStatus(BaseModel):
    authentication_required: bool
    authenticated: bool


def session_status(request: Request) -> SessionStatus:
    password = configured_password()
    return SessionStatus(
        authentication_required=password is not None,
        authenticated=password is None or valid_session(request.cookies.get(COOKIE_NAME), password),
    )


@router.get("/session", response_model=SessionStatus)
def session(request: Request) -> SessionStatus:
    return session_status(request)


@router.post("/login", response_model=SessionStatus)
def login(body: LoginRequest, response: Response) -> SessionStatus:
    password = configured_password()
    if password is not None:
        if not matches(body.password, password):
            raise HTTPException(401, detail="Неверный пароль.")
        response.set_cookie(
            COOKIE_NAME,
            issue_session(password),
            max_age=SESSION_TTL,
            httponly=True,
            samesite="strict",
            secure=os.getenv("PPD_COOKIE_SECURE", "").lower() in {"1", "true"},
            path="/",
        )
    return SessionStatus(authentication_required=password is not None, authenticated=True)


@router.post("/logout", response_model=SessionStatus)
def logout(response: Response) -> SessionStatus:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="strict")
    required = configured_password() is not None
    return SessionStatus(authentication_required=required, authenticated=not required)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("origin"):
            try:
                origin = urlsplit(request.headers["origin"])
            except ValueError:
                return JSONResponse({"detail": "Недопустимый источник запроса."}, status_code=403)
            host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
            if origin.scheme not in {"http", "https"} or origin.netloc != host:
                return JSONResponse({"detail": "Недопустимый источник запроса."}, status_code=403)
        if request.url.path not in _PUBLIC_PATHS and not session_status(request).authenticated:
            return JSONResponse({"detail": "Требуется вход в приложение."}, status_code=401)
        return await call_next(request)
