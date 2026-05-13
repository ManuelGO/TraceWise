"""Shared API dependencies (session, auth, etc.)."""

from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

security = HTTPBearer()


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Get database session from request app state."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Validate bearer token authentication.

    Phase 2 MVP: validates token existence.
    Phase 3: will be replaced with proper JWT validation.

    Args:
        credentials: HTTP bearer credentials from Authorization header

    Returns:
        The bearer token string

    Raises:
        HTTPException: 401 if authentication fails
    """
    token = credentials.credentials
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
        )
    # Phase 2 MVP: just verify token exists
    # Phase 3: implement proper JWT validation here
    return token
