"""Unit tests for the WorkflowStateCheckpoint domain model (Task 52)."""

from uuid import uuid4

from app.models import WorkflowStateCheckpoint, WorkflowStepStatus


class TestWorkflowStateCheckpointModel:
    """Tests for WorkflowStateCheckpoint instantiation and basic properties."""

    def test_instantiation_with_all_fields(self):
        """Create a checkpoint with all fields populated."""
        run_id = uuid4()
        case_id = uuid4()
        snapshot = {"query": "q", "risk_assessment": {"risk_level": "medium"}}

        cp = WorkflowStateCheckpoint(
            run_id=run_id,
            case_id=case_id,
            step="assess_risk",
            status=WorkflowStepStatus.COMPLETED,
            state_snapshot=snapshot,
            error=None,
            error_type=None,
        )

        assert cp.run_id == run_id
        assert cp.case_id == case_id
        assert cp.step == "assess_risk"
        assert cp.status == WorkflowStepStatus.COMPLETED
        assert cp.state_snapshot == snapshot
        assert cp.error is None
        assert cp.error_type is None

    def test_instantiation_failed_checkpoint(self):
        """A failed checkpoint carries the sanitized error + error_type."""
        cp = WorkflowStateCheckpoint(
            run_id=uuid4(),
            case_id=uuid4(),
            step="retrieve",
            status=WorkflowStepStatus.FAILED,
            state_snapshot={"error": "boom", "error_type": "retrieval"},
            error="boom",
            error_type="retrieval",
        )

        assert cp.status == WorkflowStepStatus.FAILED
        assert cp.error == "boom"
        assert cp.error_type == "retrieval"

    def test_state_snapshot_accepts_nested_json(self):
        """The JSONB snapshot stores arbitrarily nested JSON structures."""
        snapshot = {
            "risk_assessment": {"violations": [{"rule": "r1"}], "reasoning": "x"},
            "sources": [{"chunk_index": 0, "similarity_score": 0.6}],
            "result_count": 1,
        }
        cp = WorkflowStateCheckpoint(
            run_id=uuid4(),
            case_id=uuid4(),
            step="generate",
            status=WorkflowStepStatus.COMPLETED,
            state_snapshot=snapshot,
        )
        assert cp.state_snapshot == snapshot

    def test_has_uuid_primary_key_default(self):
        """The id column defaults to a UUID (populated at flush; None pre-flush)."""
        cp = WorkflowStateCheckpoint(
            run_id=uuid4(),
            case_id=uuid4(),
            step="extract",
            status=WorkflowStepStatus.IN_PROGRESS,
            state_snapshot={},
        )
        assert cp.id is None or isinstance(cp.id, type(uuid4()))

    def test_repr_contains_key_fields(self):
        """__repr__ surfaces run_id, case_id, step, and status."""
        cp = WorkflowStateCheckpoint(
            run_id=uuid4(),
            case_id=uuid4(),
            step="route_review",
            status=WorkflowStepStatus.COMPLETED,
            state_snapshot={},
        )
        cp.id = uuid4()
        text = repr(cp)
        assert "WorkflowStateCheckpoint" in text
        assert "run_id" in text
        assert "case_id" in text
        assert "step" in text
        assert "status" in text

    def test_tablename(self):
        """The model maps to the workflow_state_checkpoints table."""
        assert WorkflowStateCheckpoint.__tablename__ == "workflow_state_checkpoints"

    def test_run_id_created_at_index_defined(self):
        """The composite (run_id, created_at) index backs latest-checkpoint queries."""
        index_names = {idx.name for idx in WorkflowStateCheckpoint.__table__.indexes}
        assert "ix_workflow_state_checkpoints_run_id_created_at" in index_names


class TestWorkflowStepStatusEnum:
    """Tests for the WorkflowStepStatus enum."""

    def test_status_values(self):
        """All valid WorkflowStepStatus values."""
        assert WorkflowStepStatus.IN_PROGRESS.value == "in_progress"
        assert WorkflowStepStatus.COMPLETED.value == "completed"
        assert WorkflowStepStatus.FAILED.value == "failed"

    def test_status_enum_members(self):
        """WorkflowStepStatus has exactly 3 members."""
        assert len(list(WorkflowStepStatus)) == 3
