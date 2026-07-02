"""LangGraph workflow orchestration for TraceWise (Phase 6, Task 51).

Composes the six Phase 6 agents (Tasks 45-50) into one top-level compliance workflow ``StateGraph``.
The workflow is orchestration-of-orchestrators: each node wraps one agent's compiled graph, bridges
its state contract to the next agent, and threads a single shared ``WorkflowState``. Domain logic
lives in the agents and their wrapped services; the workflow adds only composition, field-mapping,
a unified error channel, and the per-case report persistence the agents deferred.
"""

from app.workflows.compliance_workflow import (
    build_compliance_workflow,
    run_compliance_workflow,
)
from app.workflows.langgraph_setup import WorkflowState

__all__ = [
    "WorkflowState",
    "build_compliance_workflow",
    "run_compliance_workflow",
]
