"""Shared helpers for the Phase 6 LangGraph agents.

These small utilities are common to every agent ``StateGraph`` (document ingestion,
entity extraction, and the agents that follow). They are factored out here so the
error-channel + routing convention stays defined in exactly one place.

Convention:
- A node returns a partial state update. On a permanent failure it returns ``agent_fail``
  (sets ``error`` + ``error_type``); ``route_after`` then short-circuits the graph to END.
- The returned ``error`` message is sanitized (newline/CR/NUL stripped) so it is safe both
  to log and to surface to downstream consumers.
"""

import logging
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from langgraph.graph import END

from app.monitoring.retry_metrics import _sanitize_log

logger = logging.getLogger(__name__)

# Call sites pass a LangGraph ``TypedDict`` state. ``Mapping`` accepts any of them
# (a TypedDict is not assignable to ``dict[str, Any]`` under mypy, but is to ``Mapping``).
StateT = TypeVar("StateT", bound=Mapping[str, Any])


def agent_fail(agent_label: str, error_type: str, message: str) -> dict[str, Any]:
    """Build a partial state update representing a permanent failure.

    The message is sanitized once and used for both the log line and the returned
    ``error`` field, so a sanitized value is what propagates to downstream consumers.

    Args:
        agent_label: Human-readable agent name for the log line (e.g. "Entity extraction").
        error_type: Stable error category (e.g. ``"extraction"``, ``"validation"``).
        message: Raw failure message; sanitized before logging/returning.
    """
    sanitized = _sanitize_log(message)
    logger.warning("%s failed (%s): %s", agent_label, error_type, sanitized)
    return {"error": sanitized, "error_type": error_type}


def has_error(state: Mapping[str, Any]) -> bool:
    """True when an upstream node has already recorded a permanent error."""
    return bool(state.get("error"))


def route_after(node_name: str) -> Callable[[StateT], str]:
    """Build a conditional-edge router that goes to END on error, else to ``node_name``."""

    def router(state: StateT) -> str:
        return END if has_error(state) else node_name

    return router
