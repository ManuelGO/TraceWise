"""Tests for the evidence gap analysis API endpoint (Task 44).

The endpoint is stateless (no database). Tests mount only the evidence-gaps router
on a bare FastAPI app so they exercise the real route without the full application
lifespan (which requires Redis/greenlet not available in unit-test envs).
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.evidence_gaps import router
from app.models.enums import DocumentType
from app.schemas.evidence_gap import GENERAL_DOC_TYPE
from app.services.evidence_gap_analyzer import REQUIRED_FIELDS_BY_DOC_TYPE

ENDPOINT = "/api/v1/evidence-gaps/analyze"
AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture
def client() -> TestClient:
    """Bare app with only the evidence-gaps router (no app lifespan)."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def _extraction_payload(*, certification: str | None = None) -> dict:
    supplier: dict = {"name": "Acme Corp", "country_of_origin": "US"}
    if certification is not None:
        supplier["certification_status"] = certification
    return {
        "document_id": str(uuid4()),
        "supplier": supplier,
        "product": {"name": "Steel Coils"},
        "location": {"country": "US"},
        "shipment": {},
        "extraction_confidence": 0.9,
        "extracted_at": datetime.now(UTC).isoformat(),
        "model_used": "openai/gpt-4o-mini",
    }


def test_router_registered():
    assert router.prefix == "/evidence-gaps"
    assert any(r.path.endswith("/analyze") for r in router.routes)  # type: ignore[attr-defined]


def test_analyze_requires_auth(client: TestClient):
    body = {"extraction": _extraction_payload()}
    resp = client.post(ENDPOINT, json=body)  # no Authorization header
    assert resp.status_code in (401, 403)


def test_analyze_happy_path(client: TestClient):
    body = {
        "extraction": _extraction_payload(certification="certified"),
        "document_type": DocumentType.SUPPLIER_DECLARATION.value,
    }
    resp = client.post(ENDPOINT, json=body, headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_complete"] is True
    assert data["gaps"] == []
    assert data["completeness_score"] == 1.0


def test_analyze_reports_gap(client: TestClient):
    body = {
        "extraction": _extraction_payload(),  # no certification_status
        "document_type": DocumentType.SUPPLIER_DECLARATION.value,
    }
    resp = client.post(ENDPOINT, json=body, headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_complete"] is False
    paths = {g["entity_path"] for g in data["gaps"]}
    assert "supplier.certification_status" in paths
    assert 0.0 <= data["completeness_score"] < 1.0


def test_analyze_default_document_type_is_general(client: TestClient):
    body = {"extraction": _extraction_payload()}
    resp = client.post(ENDPOINT, json=body, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["document_type"] == GENERAL_DOC_TYPE


def test_analyze_unknown_document_type_uses_general(client: TestClient):
    body = {"extraction": _extraction_payload(), "document_type": "mystery"}
    resp = client.post(ENDPOINT, json=body, headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["document_type"] == "mystery"
    assert data["total_required"] == len(REQUIRED_FIELDS_BY_DOC_TYPE[GENERAL_DOC_TYPE])


def test_analyze_invalid_extraction_returns_422(client: TestClient):
    body = {"extraction": {"document_id": "not-a-uuid"}, "document_type": "invoice"}
    resp = client.post(ENDPOINT, json=body, headers=AUTH)
    assert resp.status_code == 422


def test_analyze_missing_extraction_returns_422(client: TestClient):
    resp = client.post(ENDPOINT, json={"document_type": "invoice"}, headers=AUTH)
    assert resp.status_code == 422


def test_analyze_rejects_extra_keys(client: TestClient):
    body = {
        "extraction": _extraction_payload(),
        "document_type": "invoice",
        "unexpected": "x",
    }
    resp = client.post(ENDPOINT, json=body, headers=AUTH)
    assert resp.status_code == 422
