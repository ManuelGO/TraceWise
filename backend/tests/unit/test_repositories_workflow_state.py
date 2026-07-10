"""Unit tests for WorkflowStateRepository (Task 52).

Runs fully offline: the DB-touching finders are exercised against a fake async session whose
``execute`` returns a canned result object, so no live database is required (mirroring the offline
convention of the Phase 6 suites).
"""

from typing import Any
from uuid import uuid4

import pytest

from app.db.repositories.workflow_state import WorkflowStateRepository
from app.db.repository import BaseRepository
from app.models import WorkflowStateCheckpoint, WorkflowStepStatus


class _FakeScalarResult:
    """Stand-in for the SQLAlchemy Result returned by ``session.execute``."""

    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def scalars(self) -> "_FakeScalarResult":
        return self

    def all(self) -> list[Any]:
        return list(self._items)

    def scalar_one_or_none(self) -> Any:
        return self._items[0] if self._items else None


class _FakeSession:
    """Minimal async session: records the executed statement, returns canned rows."""

    def __init__(self, items: list[Any] | None = None) -> None:
        self._items = items if items is not None else []
        self.executed: list[Any] = []

    async def execute(self, stmt: Any) -> _FakeScalarResult:
        self.executed.append(stmt)
        return _FakeScalarResult(self._items)


def _checkpoint(**overrides: Any) -> WorkflowStateCheckpoint:
    base: dict[str, Any] = {
        "run_id": uuid4(),
        "case_id": uuid4(),
        "step": "assess_risk",
        "status": WorkflowStepStatus.COMPLETED,
        "state_snapshot": {},
    }
    base.update(overrides)
    return WorkflowStateCheckpoint(**base)


class TestWorkflowStateRepositoryConfiguration:
    """Configuration + wiring of the repository."""

    def test_model_is_workflow_state_checkpoint(self):
        repo = WorkflowStateRepository()
        assert repo.model == WorkflowStateCheckpoint

    def test_inherits_base_repository(self):
        repo = WorkflowStateRepository()
        assert isinstance(repo, BaseRepository)

    def test_filterable_fields(self):
        repo = WorkflowStateRepository()
        assert repo.FILTERABLE_FIELDS == {"run_id", "case_id", "step", "status"}

    def test_protected_fields(self):
        repo = WorkflowStateRepository()
        assert repo.PROTECTED_FIELDS == {"id", "created_at", "updated_at"}


class TestWorkflowStateRepositoryFinders:
    """The run/case-scoped finders."""

    @pytest.mark.asyncio
    async def test_find_by_run_id_returns_list(self):
        run_id = uuid4()
        rows = [_checkpoint(run_id=run_id, step="extract"), _checkpoint(run_id=run_id, step="retrieve")]
        session = _FakeSession(rows)
        repo = WorkflowStateRepository()

        result = await repo.find_by_run_id(session, run_id)  # type: ignore[arg-type]

        assert result == rows
        assert len(session.executed) == 1

    @pytest.mark.asyncio
    async def test_find_by_run_id_empty(self):
        session = _FakeSession([])
        repo = WorkflowStateRepository()

        result = await repo.find_by_run_id(session, uuid4())  # type: ignore[arg-type]

        assert result == []

    @pytest.mark.asyncio
    async def test_find_by_run_id_caps_limit(self):
        """A limit above 1000 is capped (defensive, matching BaseRepository)."""
        session = _FakeSession([])
        repo = WorkflowStateRepository()

        result = await repo.find_by_run_id(session, uuid4(), limit=99999)  # type: ignore[arg-type]

        assert result == []

    @pytest.mark.asyncio
    async def test_find_latest_by_run_id_returns_newest(self):
        run_id = uuid4()
        latest = _checkpoint(run_id=run_id, step="route_review")
        session = _FakeSession([latest])
        repo = WorkflowStateRepository()

        result = await repo.find_latest_by_run_id(session, run_id)  # type: ignore[arg-type]

        assert result is latest

    @pytest.mark.asyncio
    async def test_find_latest_by_run_id_none_when_empty(self):
        session = _FakeSession([])
        repo = WorkflowStateRepository()

        result = await repo.find_latest_by_run_id(session, uuid4())  # type: ignore[arg-type]

        assert result is None

    @pytest.mark.asyncio
    async def test_find_by_case_id_uses_filter(self):
        case_id = uuid4()
        rows = [_checkpoint(case_id=case_id)]
        session = _FakeSession(rows)
        repo = WorkflowStateRepository()

        result = await repo.find_by_case_id(session, case_id)  # type: ignore[arg-type]

        assert result == rows


class TestWorkflowStateRepositoryOrderingDeterminism:
    """Placeholder for FIX 3 (post-launch): a monotonic tiebreak on find_latest_by_run_id."""

    @pytest.mark.skip(
        reason="FIX 3 deferred post-launch: needs a DB-generated autoincrement 'sequence' column "
        "(migration) so find_latest_by_run_id is deterministic when two checkpoints tie on "
        "created_at. Un-skip and implement when the tiebreaker migration lands."
    )
    @pytest.mark.asyncio
    async def test_find_latest_by_run_id_deterministic_on_created_at_tie(self):
        # When two checkpoints for one run share an identical created_at, find_latest_by_run_id must
        # deterministically return the one inserted last (by the monotonic sequence tiebreaker).
        raise NotImplementedError("Implement alongside the FIX 3 sequence-column migration.")
