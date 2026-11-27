"""登录认证接口。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..security import create_access_token, get_current_user, verify_credentials
from ..config import settings
from fastapi import Depends

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginPayload(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(payload: LoginPayload) -> dict:
    if not verify_credentials(payload.username, payload.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(payload.username)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.token_expire_minutes * 60,
        "username": payload.username,
    }


@router.get("/me")
async def me(username: str = Depends(get_current_user)) -> dict:
    return {"username": username}
