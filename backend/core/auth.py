# core/auth.py — FastAPI dependency for protected routes
# Re-exports access_security from services/auth.py so routers can do:
#   Depends(get_current_user)
#
# credentials.subject will contain: {"user_id": ..., "username": ..., "salting": ...}

from fastapi import Depends
from fastapi_jwt import JwtAuthorizationCredentials

from services.auth import access_security


def get_current_user(
    credentials: JwtAuthorizationCredentials = Depends(access_security),
) -> dict:
    """
    Injected into any route that requires authentication.
    fastapi_jwt automatically validates the token from the
    Authorization header or cookie.

    Java equivalent: @AuthenticationPrincipal

    Usage in a router:
        @router.get("/protected")
        def protected(current_user: dict = Depends(get_current_user)):
            current_user["username"]
            current_user["user_id"]
    """
    return credentials.subject  # {"user_id": ..., "username": ..., "salting": ...}
