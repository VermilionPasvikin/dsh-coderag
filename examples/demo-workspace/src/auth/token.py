"""Token verification for the demo workspace.

用户令牌在哪里校验？答案就在本模块的 verify_token。
"""

from __future__ import annotations


class Claims:
    """The claims carried by a verified token."""

    def __init__(self, subject: str) -> None:
        self.subject = subject


def verify_token(raw: str) -> Claims:
    """校验用户令牌并返回其声明。"""
    if not raw.startswith("Bearer "):
        raise ValueError("invalid token")
    return Claims(subject=raw.removeprefix("Bearer "))
