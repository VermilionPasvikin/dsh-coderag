"""Request authentication middleware for the demo workspace."""

from __future__ import annotations

from src.auth.token import verify_token


def require_auth(raw: str) -> None:
    """拦截未认证的请求；令牌无效时抛出。"""
    if not raw:
        raise PermissionError("unauthorized")
    verify_token(raw)
