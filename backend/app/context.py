"""Request-scoped context variables for structured logging."""

from contextvars import ContextVar, Token
from typing import Any

# Define context variables for request tracking and logging
request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
case_id: ContextVar[str | None] = ContextVar("case_id", default=None)
document_id: ContextVar[str | None] = ContextVar("document_id", default=None)
user_id: ContextVar[str | None] = ContextVar("user_id", default=None)
session_id: ContextVar[str | None] = ContextVar("session_id", default=None)

# Map of context variable names to their ContextVar instances
_context_vars = {
    "request_id": request_id,
    "case_id": case_id,
    "document_id": document_id,
    "user_id": user_id,
    "session_id": session_id,
}

# Exported list of context variable names for use in formatters and other consumers
CONTEXT_VAR_NAMES: tuple[str, ...] = tuple(_context_vars.keys())


def get_context_var(name: str) -> Any | None:
    """Get a context variable value by name.

    Args:
        name: The name of the context variable.

    Returns:
        The value of the context variable, or None if not set.

    Raises:
        ValueError: If the context variable name is unknown.
    """
    if name not in _context_vars:
        raise ValueError(f"Unknown context variable: {name}")
    return _context_vars[name].get()


def set_context_var(name: str, value: Any) -> Token[Any | None]:
    """Set a context variable value by name.

    Args:
        name: The name of the context variable.
        value: The value to set.

    Returns:
        A Token that can be used to restore the prior value via reset_token().

    Raises:
        ValueError: If the context variable name is unknown.
    """
    if name not in _context_vars:
        raise ValueError(f"Unknown context variable: {name}")
    return _context_vars[name].set(value)


def reset_token(name: str, token: Token[Any | None]) -> None:
    """Restore a context variable to its state via a saved token.

    Args:
        name: The name of the context variable.
        token: The token returned from set_context_var().

    Raises:
        ValueError: If the context variable name is unknown.
    """
    if name not in _context_vars:
        raise ValueError(f"Unknown context variable: {name}")
    _context_vars[name].reset(token)


def reset_context() -> None:
    """Reset all context variables to their default values (set to None)."""
    for context_var in _context_vars.values():
        context_var.set(None)
