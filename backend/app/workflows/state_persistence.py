"""Compliance-workflow state persistence (Task 52, Phase 6).

Adds durable checkpointing + recovery AROUND the Task 51 compliance workflow without touching any
agent's domain logic (Architecture Section 1). This module owns:

- ``serialize_state`` / ``deserialize_state`` -- convert a ``WorkflowState`` to/from a JSON-safe dict
  suitable for the ``workflow_state_checkpoints.state_snapshot`` JSONB column. The only non-JSON-native
  members are ``file_bytes`` (raw bytes, deliberately DROPPED -- never persisted) and the Pydantic
  ``extraction_result`` / ``validation_result`` (``model_dump(mode="json")``-ed one way, re-hydrated
  the other). Everything else already round-trips ``json.dumps`` (Architecture Section 5c).
- ``WorkflowCheckpointer`` -- persists one checkpoint per workflow step (``save_checkpoint``) and loads
  the newest checkpoint back for recovery (``load_latest``). Writes are BEST-EFFORT: any failure is
  logged and swallowed so the audit/recovery side-channel can never break a live workflow run. It owns
  its ``AsyncSession`` per write (opened from the injected ``session_factory``, closed on every path --
  the Task 46/51 session-lifecycle pattern), so nothing unserializable is threaded through the graph
  state.

Design decisions (coordinator-confirmed, 2026-07-06 -- see ``phase-6/2026-07-06-task-52-*/plan.md``):
- Persistence is a DOMAIN model (``WorkflowStateCheckpoint`` + ``WorkflowStateRepository``), NOT a
  LangGraph ``BaseCheckpointSaver`` (which needs an uninstalled dep and stores opaque blobs). The
  existing inert ``checkpointer=`` compile seam on ``build_compliance_workflow`` is left in place.
- Each checkpoint snapshots the FULL ``WorkflowState`` (minus ``file_bytes``).
- Recovery ships the primitive (``load_latest``) + a seed-resume path (see ``run_compliance_workflow``);
  node-level skip-forward is carried-forward.
- Checkpointing is OPT-IN (``WORKFLOW_CHECKPOINTING_ENABLED``, default False) and off unless a
  checkpointer is injected -- so existing callers/tests are unaffected.
"""

import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WorkflowStateCheckpoint, WorkflowStepStatus
from app.monitoring.retry_metrics import _sanitize_log
from app.schemas.extraction import ExtractionResult
from app.schemas.validation import ValidationResult
from app.workflows.langgraph_setup import WorkflowState

logger = logging.getLogger(__name__)

# Keys that must NOT reach the JSONB snapshot verbatim.
# ``file_bytes`` is raw document bytes (large, non-JSON, sensitive) -- never persisted.
_DROP_KEYS = frozenset({"file_bytes"})
# Pydantic-model-valued keys: ``model_dump(mode="json")`` out, ``model_validate`` back in.
_PYDANTIC_KEYS: dict[str, type[Any]] = {
    "extraction_result": ExtractionResult,
    "validation_result": ValidationResult,
}


def serialize_state(state: WorkflowState) -> dict[str, Any]:
    """Convert a ``WorkflowState`` into a JSON-serializable snapshot dict.

    Drops ``file_bytes`` and ``model_dump(mode="json")``s the Pydantic ``extraction_result`` /
    ``validation_result``; all other members are already JSON-native (Architecture Section 5c) and pass
    through unchanged. The result satisfies ``json.dumps``.

    Args:
        state: The in-memory workflow state (a ``TypedDict``; treated as a plain mapping).

    Returns:
        A JSON-safe dict snapshot of the state.
    """
    snapshot: dict[str, Any] = {}
    for key, value in state.items():
        if key in _DROP_KEYS:
            continue
        if key in _PYDANTIC_KEYS and value is not None and hasattr(value, "model_dump"):
            snapshot[key] = value.model_dump(mode="json")
        else:
            snapshot[key] = value
    return snapshot


def deserialize_state(snapshot: dict[str, Any]) -> WorkflowState:
    """Reconstruct a ``WorkflowState`` from a persisted snapshot dict (recovery).

    Inverse of ``serialize_state``: re-hydrates the Pydantic ``extraction_result`` /
    ``validation_result`` back into their models so a resumed run type-checks. Tolerant of partial
    snapshots (an early-failed run may lack later keys) -- unknown/absent keys are simply passed
    through or skipped (the state ``TypedDict`` is ``total=False``). A Pydantic sub-dict that fails to
    validate is DROPPED (not kept as a raw dict): downstream nodes type-assert these keys as their
    Pydantic models (e.g. Risk reads ``extraction_result`` as an ``ExtractionResult``), so a mistyped
    dict would crash deep in a service; dropping the key lets the node's own "missing required input"
    guard fail the run cleanly through the workflow error channel instead.

    Args:
        snapshot: The JSON dict read back from ``state_snapshot``.

    Returns:
        A ``WorkflowState`` with Pydantic fields re-hydrated where possible; unrecoverable Pydantic
        fields are omitted.
    """
    state: dict[str, Any] = {}
    for key, value in snapshot.items():
        model_cls = _PYDANTIC_KEYS.get(key)
        if model_cls is not None and isinstance(value, dict):
            try:
                state[key] = model_cls.model_validate(value)
            except Exception:
                logger.warning("Could not re-hydrate %s during recovery; dropping corrupt field", key)
                # Do NOT keep the raw dict -- downstream code expects a Pydantic model here.
                continue
        else:
            state[key] = value
    # ``WorkflowState`` is a ``total=False`` TypedDict; a partial dict is a valid instance.
    return state  # type: ignore[return-value]


class WorkflowCheckpointer:
    """Persists + recovers compliance-workflow state checkpoints (Task 52).

    Injected into ``build_compliance_workflow``; each workflow node is wrapped so that after it runs
    the merged post-node state is checkpointed. All writes are best-effort (logged + swallowed on
    failure) so persistence can never break a run.
    """

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        repository: Any | None = None,
    ) -> None:
        """Initialize the checkpointer.

        Args:
            session_factory: Zero-arg callable returning a fresh ``AsyncSession`` (injected for
                testing; defaults in the builder to the cached Celery-task session factory).
            repository: ``WorkflowStateRepository`` (injected for testing). Defaults to a real one.
        """
        self._session_factory = session_factory
        if repository is None:
            from app.db.repositories.workflow_state import WorkflowStateRepository

            repository = WorkflowStateRepository()
        self._repository = repository

    async def save_checkpoint(
        self,
        *,
        run_id: str,
        case_id: str,
        step: str,
        status: WorkflowStepStatus,
        state: WorkflowState,
        error: str | None = None,
        error_type: str | None = None,
    ) -> None:
        """Persist one checkpoint for a workflow step. Best-effort: never raises into the caller.

        Opens a session, writes the ``WorkflowStateCheckpoint`` row, commits, and closes the session on
        EVERY path. On any failure (invalid ids, session/commit error) it logs and returns -- the
        workflow's own error channel is untouched.

        Args:
            run_id: Per-run identifier (UUID string) grouping this run's checkpoints.
            case_id: Parent compliance case (UUID string) -- the audit/FK link.
            step: The workflow node just completed.
            status: ``in_progress`` | ``completed`` | ``failed`` for this step.
            state: The merged workflow state after the step (serialized into the snapshot).
            error: Sanitized error message when the step failed.
            error_type: The failing step's error type.
        """
        try:
            run_uuid = UUID(run_id)
            case_uuid = UUID(case_id)
        except (ValueError, AttributeError, TypeError):
            # Persistence must not be more fragile than the run it observes: a bad id is logged
            # (sanitized + bounded) and skipped, not raised.
            logger.warning(
                "Skipping checkpoint for step %s: invalid run_id/case_id (run=%s case=%s)",
                _sanitize_log(str(step))[:64],
                _sanitize_log(str(run_id))[:128],
                _sanitize_log(str(case_id))[:128],
            )
            return

        session: AsyncSession | None = None
        try:
            snapshot = serialize_state(state)
            session = self._session_factory()
            row = WorkflowStateCheckpoint(
                run_id=run_uuid,
                case_id=case_uuid,
                step=step,
                status=status,
                state_snapshot=snapshot,
                error=error,
                error_type=error_type,
            )
            await self._repository.create(session, row)
            await session.commit()
            logger.info(
                "Checkpoint saved: run=%s step=%s status=%s",
                run_uuid,
                _sanitize_log(str(step))[:64],
                status.value,
            )
        except Exception:
            # Best-effort: log the raw exception server-side only, swallow it.
            logger.error(
                "Failed to save workflow checkpoint (run=%s step=%s)",
                run_uuid,
                _sanitize_log(str(step))[:64],
                exc_info=True,
            )
        finally:
            if session is not None:
                await session.close()

    async def load_latest(self, run_id: str) -> WorkflowState | None:
        """Load the newest checkpoint for a run and return its recovered ``WorkflowState``.

        The recovery entry point: reconstructs the state (Pydantic fields re-hydrated) from the most
        recent checkpoint so a caller can inspect a failed run or seed a resume. Returns ``None`` when
        the run has no checkpoints or the id is invalid; a read failure is logged and yields ``None``
        (best-effort, like the write path).

        Args:
            run_id: The workflow run identifier (UUID string).

        Returns:
            The recovered ``WorkflowState``, or ``None`` if unavailable.
        """
        try:
            run_uuid = UUID(run_id)
        except (ValueError, AttributeError, TypeError):
            logger.warning(
                "Cannot load checkpoint: invalid run_id %s", _sanitize_log(str(run_id))[:128]
            )
            return None

        session: AsyncSession | None = None
        try:
            session = self._session_factory()
            row = await self._repository.find_latest_by_run_id(session, run_uuid)
            if row is None:
                return None
            return deserialize_state(dict(row.state_snapshot))
        except Exception:
            logger.error("Failed to load latest checkpoint (run=%s)", run_uuid, exc_info=True)
            return None
        finally:
            if session is not None:
                await session.close()


__all__ = [
    "WorkflowCheckpointer",
    "deserialize_state",
    "serialize_state",
]
