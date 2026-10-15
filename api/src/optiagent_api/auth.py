"""Authentication: verify Clerk session tokens and identify the user.

Clerk issues short-lived RS256 session JWTs. The browser sends one as `Authorization: Bearer ...`;
we check the signature against Clerk's published keys (JWKS), the issuer, the expiry and the
`azp` (authorized party) claim, then use `sub` (the Clerk user ID) as the owner of their data.

With no issuer configured, authentication is off and everything belongs to the single local user
(owner None). That keeps local development simple.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any, Protocol

import jwt
from fastapi import Depends, HTTPException, Request

from optiagent_api.settings import Settings, get_settings


class KeySource(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> Any: ...


@lru_cache
def jwks_client(issuer: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(
        f"{issuer.rstrip('/')}/.well-known/jwks.json", cache_keys=True, lifespan=3600
    )


class AuthError(Exception):
    pass


def verify_token(token: str, *, issuer: str, authorized_parties: list[str], keys: KeySource) -> str:
    """Return the user ID in a valid session token, or raise AuthError."""
    try:
        signing_key = keys.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer.rstrip("/"),
            leeway=30,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"invalid session token: {exc}") from exc
    azp = claims.get("azp")
    if azp and authorized_parties and azp not in authorized_parties:
        raise AuthError(f"token issued for an unexpected origin: {azp}")
    user_id = claims["sub"]
    if not isinstance(user_id, str) or not user_id:
        raise AuthError("token has no user")
    return user_id


def current_user(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> str | None:
    """The signed-in user's ID, or None when authentication is disabled (local mode)."""
    if not settings.auth_issuer:
        return None
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Sign in to continue.", headers={"WWW-Authenticate": "Bearer"})
    try:
        user_id = verify_token(
            token,
            issuer=settings.auth_issuer,
            authorized_parties=settings.auth_authorized_parties or settings.cors_origins,
            keys=jwks_client(settings.auth_issuer),
        )
    except AuthError:
        raise HTTPException(
            401, "Your session has expired. Sign in again.", headers={"WWW-Authenticate": "Bearer"}
        ) from None
    request.state.user_id = user_id
    return user_id


CurrentUser = Annotated[str | None, Depends(current_user)]
