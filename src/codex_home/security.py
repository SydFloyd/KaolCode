from __future__ import annotations

import hashlib
import hmac

from fastapi import Header, HTTPException, Request, status


def verify_github_signature(body: bytes, signature: str | None, secret: str) -> bool:
    if not secret:
        return True
    if not signature:
        return False
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    provided = signature.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)


def require_operator_token(token: str | None, expected: str) -> None:
    if not expected:
        return
    if token is None or token != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid operator token.",
        )


async def operator_auth_dependency(
    request: Request,
    x_operator_token: str | None = Header(default=None),
) -> None:
    settings = request.app.state.settings
    require_operator_token(x_operator_token, settings.operator_token)

