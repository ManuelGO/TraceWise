"""Middleware for request context propagation in structured logging."""

import re
import uuid
from contextvars import Token

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.context import reset_context, reset_token, set_context_var
from app.logging import get_logger

logger = get_logger(__name__)

# Regex to validate UUID-shaped request IDs
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware that manages request context for structured logging.

    Sets up request-scoped context variables (request_id, etc.) at the start
    of each request and ensures they are reset after the response is sent,
    even if the handler raises an exception.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Manage request context lifecycle.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler.

        Returns:
            The response from the next handler.
        """
        # Track tokens for precise context restoration
        tokens: dict[str, Token] = {}

        try:
            # Get or generate request_id with validation to prevent log injection
            raw_request_id = request.headers.get("X-Request-ID", "").strip()
            if raw_request_id and _UUID_RE.match(raw_request_id):
                request_id = raw_request_id
            else:
                request_id = str(uuid.uuid4())
            tokens["request_id"] = set_context_var("request_id", request_id)

            response = await call_next(request)
            return response
        finally:
            # Restore context vars to their prior state using tokens (not .set(None))
            for name, token in tokens.items():
                reset_token(name, token)
            # Catch-all reset in case additional context vars were set elsewhere
            reset_context()
