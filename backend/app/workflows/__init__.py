"""LangGraph workflow orchestration for TraceWise (Phase 6, Tasks 51-52).

Composes the six Phase 6 agents (Tasks 45-50) into one top-level compliance workflow ``StateGraph``.
The workflow is orchestration-of-orchestrators: each node wraps one agent's compiled graph, bridges
its state contract to the next agent, and threads a single shared ``WorkflowState``. Domain logic
lives in the agents and their wrapped services; the workflow adds only composition, field-mapping,
a unified error channel, and the per-case report persistence the agents deferred.

Task 52 adds durable state persistence around the workflow: an opt-in ``WorkflowCheckpointer``
persists a ``WorkflowStateCheckpoint`` snapshot after each step (fault tolerance + auditability) and
recovers the latest state for resume via ``run_compliance_workflow(resume_from=...)``.
"""

from app.workflows.compliance_workflow import (
    build_compliance_workflow,
    run_compliance_workflow,
)
from app.workflows.langgraph_setup import WorkflowState
from app.workflows.state_persistence import (
    WorkflowCheckpointer,
    deserialize_state,
    serialize_state,
)

__all__ = [
    "WorkflowCheckpointer",
    "WorkflowState",
    "build_compliance_workflow",
    "deserialize_state",
    "run_compliance_workflow",
    "serialize_state",
]
