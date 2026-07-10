"""Unit tests for compliance-workflow state persistence (Task 52).

Fully offline: serialization is tested with real Pydantic models; the checkpointer is tested against a
fake session + fake repository so no DB is touched. Best-effort semantics (a persistence failure must
never propagate) are asserted explicitly.
"""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.models import WorkflowStateCheckpoint, WorkflowStepStatus
from app.schemas.extraction import (
    ExtractionResult,
    LocationInfo,
    ProductInfo,
    ShipmentInfo,
    SupplierInfo,
)
from app.schemas.validation import ValidationResult
from app.workflows.langgraph_setup import WorkflowState
from app.workflows.state_persistence import (
    WorkflowCheckpointer,
    deserialize_state,
    serialize_state,
)

RUN_ID = "33333333-3333-3333-3333-333333333333"
CASE_ID = "44444444-4444-4444-4444-444444444444"


# ===== Builders / fakes =====


def _extraction_result() -> ExtractionResult:
    return ExtractionResult(
        document_id=uuid4(),
        supplier=SupplierInfo(name="Acme Corp", country_of_origin="DE"),
        product=ProductInfo(name="Coffee beans"),
        location=LocationInfo(country="BR"),
        shipment=ShipmentInfo(),
        extraction_confidence=0.9,
        extracted_at=datetime.now(UTC),
        model_used="fake-model",
    )


def _validation_result() -> ValidationResult:
    return ValidationResult(
        is_valid=True,
        failures=[],
        validation_score=95.0,
        checked_at=datetime.now(UTC),
    )


def _full_state() -> WorkflowState:
    return WorkflowState(
        run_id=RUN_ID,
        case_id=CASE_ID,
        query="Is the supplier compliant?",
        document_id=str(uuid4()),
        document_extraction_id=str(uuid4()),
        file_bytes=b"raw-pdf-bytes",
        document_text="Some document text",
        extraction_result=_extraction_result(),
        validation_result=_validation_result(),
        validation_status="valid",
        retrieval_context="grounded context",
        sources=[{"chunk_index": 0, "similarity_score": 0.6, "content": "c"}],  # type: ignore[list-item]
        result_count=1,
        source_quality=0.6,
        risk_assessment={"risk_level": "medium", "risk_score": 42, "reasoning": "r"},
        answer="r",
        evidence_validation={"is_valid": True, "grounding_score": 0.8},
        report_content="# Report",
        report={"overall_status": "compliant"},
        generated_report_id=str(uuid4()),
        overall_status="compliant",
        needs_human_review=False,
        error=None,
        error_type=None,
    )


class _FakeSession:
    """Minimal async session recording add/commit/close and optionally failing commit."""

    def __init__(self, *, fail_commit: bool = False) -> None:
        self.committed = False
        self.closed = False
        self.added: list[Any] = []
        self._fail_commit = fail_commit

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        if self._fail_commit:
            raise RuntimeError("simulated commit failure")
        self.committed = True

    async def close(self) -> None:
        self.closed = True


class _FakeRepository:
    """Fake WorkflowStateRepository: records creates, returns a canned latest row."""

    def __init__(self, latest: WorkflowStateCheckpoint | None = None) -> None:
        self.created: list[WorkflowStateCheckpoint] = []
        self._latest = latest

    async def create(self, session: Any, obj: WorkflowStateCheckpoint) -> WorkflowStateCheckpoint:
        self.created.append(obj)
        return obj

    async def find_latest_by_run_id(
        self, session: Any, run_id: Any
    ) -> WorkflowStateCheckpoint | None:
        return self._latest


# ===== serialize_state / deserialize_state =====


class TestSerializeState:
    def test_drops_file_bytes(self):
        snapshot = serialize_state(_full_state())
        assert "file_bytes" not in snapshot

    def test_model_dumps_pydantic_fields(self):
        snapshot = serialize_state(_full_state())
        assert isinstance(snapshot["extraction_result"], dict)
        assert isinstance(snapshot["validation_result"], dict)
        assert snapshot["extraction_result"]["supplier"]["name"] == "Acme Corp"

    def test_snapshot_is_json_serializable(self):
        snapshot = serialize_state(_full_state())
        # Must round-trip json.dumps -- the whole point of Task 52 checkpointing.
        dumped = json.dumps(snapshot)
        assert "Acme Corp" in dumped

    def test_passthrough_scalars_and_dicts(self):
        snapshot = serialize_state(_full_state())
        assert snapshot["query"] == "Is the supplier compliant?"
        assert snapshot["risk_assessment"]["risk_level"] == "medium"
        assert snapshot["result_count"] == 1

    def test_none_pydantic_field_passes_through(self):
        state = WorkflowState(query="q", validation_result=None)  # type: ignore[typeddict-item]
        snapshot = serialize_state(state)
        assert snapshot["validation_result"] is None

    def test_empty_state(self):
        assert serialize_state(WorkflowState()) == {}


class TestDeserializeState:
    def test_rehydrates_pydantic_fields(self):
        snapshot = serialize_state(_full_state())
        state = deserialize_state(snapshot)
        assert isinstance(state["extraction_result"], ExtractionResult)
        assert isinstance(state["validation_result"], ValidationResult)
        assert state["extraction_result"].supplier.name == "Acme Corp"

    def test_round_trip_preserves_scalars(self):
        state = deserialize_state(serialize_state(_full_state()))
        assert state["query"] == "Is the supplier compliant?"
        assert state["overall_status"] == "compliant"
        assert state["risk_assessment"]["risk_score"] == 42

    def test_tolerates_partial_snapshot(self):
        # An early-failed run may only have inputs + an error.
        state = deserialize_state({"query": "q", "error": "boom", "error_type": "retrieval"})
        assert state["error"] == "boom"
        assert "extraction_result" not in state

    def test_malformed_pydantic_field_is_dropped(self):
        # FIX 2: a corrupt Pydantic sub-dict must NOT raise and must NOT be kept as a raw dict
        # (downstream nodes type-assert these keys as Pydantic models). The key is dropped so the
        # node's own "missing required input" guard fails the run cleanly instead of crashing.
        state = deserialize_state({"extraction_result": {"not": "valid"}, "query": "q"})
        assert "extraction_result" not in state
        # Non-corrupt keys still pass through.
        assert state["query"] == "q"

    def test_malformed_validation_result_is_dropped(self):
        state = deserialize_state({"validation_result": {"bogus": 1}})
        assert "validation_result" not in state


# ===== WorkflowCheckpointer.save_checkpoint =====


class TestSaveCheckpoint:
    @pytest.mark.asyncio
    async def test_writes_row_and_commits(self):
        session = _FakeSession()
        repo = _FakeRepository()
        cp = WorkflowCheckpointer(lambda: session, repository=repo)  # type: ignore[arg-type]

        await cp.save_checkpoint(
            run_id=RUN_ID,
            case_id=CASE_ID,
            step="assess_risk",
            status=WorkflowStepStatus.COMPLETED,
            state=_full_state(),
        )

        assert len(repo.created) == 1
        row = repo.created[0]
        assert row.step == "assess_risk"
        assert row.status == WorkflowStepStatus.COMPLETED
        assert "file_bytes" not in row.state_snapshot
        assert session.committed is True
        assert session.closed is True

    @pytest.mark.asyncio
    async def test_failed_checkpoint_carries_error(self):
        session = _FakeSession()
        repo = _FakeRepository()
        cp = WorkflowCheckpointer(lambda: session, repository=repo)  # type: ignore[arg-type]

        await cp.save_checkpoint(
            run_id=RUN_ID,
            case_id=CASE_ID,
            step="retrieve",
            status=WorkflowStepStatus.FAILED,
            state=WorkflowState(error="boom", error_type="retrieval"),
            error="boom",
            error_type="retrieval",
        )

        row = repo.created[0]
        assert row.status == WorkflowStepStatus.FAILED
        assert row.error == "boom"
        assert row.error_type == "retrieval"

    @pytest.mark.asyncio
    async def test_invalid_ids_skip_without_writing(self):
        session = _FakeSession()
        repo = _FakeRepository()
        cp = WorkflowCheckpointer(lambda: session, repository=repo)  # type: ignore[arg-type]

        await cp.save_checkpoint(
            run_id="not-a-uuid",
            case_id=CASE_ID,
            step="extract",
            status=WorkflowStepStatus.COMPLETED,
            state=_full_state(),
        )

        assert repo.created == []
        # No session opened for a bad id.
        assert session.committed is False

    @pytest.mark.asyncio
    async def test_commit_failure_is_swallowed_and_session_closed(self):
        session = _FakeSession(fail_commit=True)
        repo = _FakeRepository()
        cp = WorkflowCheckpointer(lambda: session, repository=repo)  # type: ignore[arg-type]

        # Must NOT raise (best-effort).
        await cp.save_checkpoint(
            run_id=RUN_ID,
            case_id=CASE_ID,
            step="generate",
            status=WorkflowStepStatus.COMPLETED,
            state=_full_state(),
        )

        assert session.committed is False
        assert session.closed is True

    @pytest.mark.asyncio
    async def test_factory_failure_is_swallowed(self):
        def _boom() -> Any:
            raise RuntimeError("cannot open session")

        cp = WorkflowCheckpointer(_boom, repository=_FakeRepository())

        # Must NOT raise even when the session factory itself fails.
        await cp.save_checkpoint(
            run_id=RUN_ID,
            case_id=CASE_ID,
            step="extract",
            status=WorkflowStepStatus.COMPLETED,
            state=_full_state(),
        )


# ===== WorkflowCheckpointer.load_latest =====


class TestLoadLatest:
    @pytest.mark.asyncio
    async def test_returns_deserialized_state(self):
        latest = WorkflowStateCheckpoint(
            run_id=uuid4(),
            case_id=uuid4(),
            step="assess_risk",
            status=WorkflowStepStatus.COMPLETED,
            state_snapshot=serialize_state(_full_state()),
        )
        session = _FakeSession()
        repo = _FakeRepository(latest=latest)
        cp = WorkflowCheckpointer(lambda: session, repository=repo)  # type: ignore[arg-type]

        state = await cp.load_latest(RUN_ID)

        assert state is not None
        assert isinstance(state["extraction_result"], ExtractionResult)
        assert state["query"] == "Is the supplier compliant?"
        assert session.closed is True

    @pytest.mark.asyncio
    async def test_none_when_no_checkpoint(self):
        session = _FakeSession()
        cp = WorkflowCheckpointer(lambda: session, repository=_FakeRepository(latest=None))  # type: ignore[arg-type]

        assert await cp.load_latest(RUN_ID) is None

    @pytest.mark.asyncio
    async def test_none_for_invalid_run_id(self):
        session = _FakeSession()
        cp = WorkflowCheckpointer(lambda: session, repository=_FakeRepository())  # type: ignore[arg-type]

        assert await cp.load_latest("not-a-uuid") is None

    @pytest.mark.asyncio
    async def test_read_failure_returns_none(self):
        def _boom() -> Any:
            raise RuntimeError("cannot open session")

        cp = WorkflowCheckpointer(_boom, repository=_FakeRepository())

        assert await cp.load_latest(RUN_ID) is None


class TestCheckpointerDefaults:
    def test_default_repository_constructed(self):
        # No repository injected -> a real WorkflowStateRepository is built lazily.
        from app.db.repositories.workflow_state import WorkflowStateRepository

        cp = WorkflowCheckpointer(lambda: None)  # type: ignore[arg-type,return-value]
        assert isinstance(cp._repository, WorkflowStateRepository)
