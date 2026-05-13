"""Tests for compliance case API endpoints."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import create_app
from app.models.compliance_case import ComplianceCase
from app.models.enums import CaseStatus, RiskLevel


@pytest.mark.asyncio
async def test_create_case_success(test_db_session: AsyncSession):
    """POST /cases creates a case and returns 201 with populated fields."""
    app = create_app()

    async def mock_get_session(request):
        yield test_db_session

    from app.api.cases import get_session as original_get_session

    app.dependency_overrides[original_get_session] = mock_get_session

    client = TestClient(app)
    payload = {
        "title": "Test Case 1",
        "supplier_name": "TestCorp",
        "product_type": "Widget",
        "country_of_origin": "US",
        "risk_level": "high",
    }

    response = client.post("/api/v1/cases", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert data["title"] == "Test Case 1"
    assert data["supplier_name"] == "TestCorp"
    assert data["status"] == "draft"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_case_duplicate_title(test_db_session: AsyncSession):
    """POST /cases returns 409 when title already exists."""
    existing = ComplianceCase(
        title="Existing Case",
        supplier_name="Supplier A",
        product_type="Product A",
        country_of_origin="US",
        risk_level=RiskLevel.LOW,
    )
    test_db_session.add(existing)
    await test_db_session.commit()

    app = create_app()

    async def mock_get_session(request):
        yield test_db_session

    from app.api.cases import get_session as original_get_session

    app.dependency_overrides[original_get_session] = mock_get_session

    client = TestClient(app)
    payload = {
        "title": "Existing Case",
        "supplier_name": "TestCorp",
        "product_type": "Widget",
        "country_of_origin": "US",
        "risk_level": "medium",
    }

    response = client.post("/api/v1/cases", json=payload)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_case_invalid_risk_level(test_db_session: AsyncSession):
    """POST /cases returns 422 for invalid risk_level."""
    app = create_app()

    async def mock_get_session(request):
        yield test_db_session

    from app.api.cases import get_session as original_get_session

    app.dependency_overrides[original_get_session] = mock_get_session

    client = TestClient(app)
    payload = {
        "title": "Test Case",
        "supplier_name": "TestCorp",
        "product_type": "Widget",
        "country_of_origin": "US",
        "risk_level": "invalid",
    }

    response = client.post("/api/v1/cases", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_case_by_id_success(test_db_session: AsyncSession):
    """GET /cases/{id} returns case details."""
    case = ComplianceCase(
        title="Test Case Get",
        supplier_name="TestCorp",
        product_type="Widget",
        country_of_origin="US",
        risk_level=RiskLevel.MEDIUM,
    )
    test_db_session.add(case)
    await test_db_session.commit()
    await test_db_session.refresh(case)

    app = create_app()

    async def mock_get_session(request):
        yield test_db_session

    from app.api.cases import get_session as original_get_session

    app.dependency_overrides[original_get_session] = mock_get_session

    client = TestClient(app)
    response = client.get(f"/api/v1/cases/{case.id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(case.id)
    assert data["title"] == "Test Case Get"


@pytest.mark.asyncio
async def test_get_case_not_found(test_db_session: AsyncSession):
    """GET /cases/{id} returns 404 for non-existent case."""
    app = create_app()

    async def mock_get_session(request):
        yield test_db_session

    from app.api.cases import get_session as original_get_session

    app.dependency_overrides[original_get_session] = mock_get_session

    client = TestClient(app)
    fake_id = uuid4()
    response = client.get(f"/api/v1/cases/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_cases_empty(test_db_session: AsyncSession):
    """GET /cases returns empty list when no cases exist."""
    app = create_app()

    async def mock_get_session(request):
        yield test_db_session

    from app.api.cases import get_session as original_get_session

    app.dependency_overrides[original_get_session] = mock_get_session

    client = TestClient(app)
    response = client.get("/api/v1/cases")
    assert response.status_code == 200

    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_cases_with_pagination(test_db_session: AsyncSession):
    """GET /cases returns paginated results."""
    for i in range(5):
        case = ComplianceCase(
            title=f"Case {i}",
            supplier_name=f"Supplier {i}",
            product_type="Widget",
            country_of_origin="US",
            risk_level=RiskLevel.LOW,
        )
        test_db_session.add(case)
    await test_db_session.commit()

    app = create_app()

    async def mock_get_session(request):
        yield test_db_session

    from app.api.cases import get_session as original_get_session

    app.dependency_overrides[original_get_session] = mock_get_session

    client = TestClient(app)
    response = client.get("/api/v1/cases?skip=0&limit=2")
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5


@pytest.mark.asyncio
async def test_list_cases_filter_by_status(test_db_session: AsyncSession):
    """GET /cases filters by status."""
    draft_case = ComplianceCase(
        title="Draft Case",
        supplier_name="Supplier",
        product_type="Widget",
        country_of_origin="US",
        risk_level=RiskLevel.LOW,
        status=CaseStatus.DRAFT,
    )
    processing_case = ComplianceCase(
        title="Processing Case",
        supplier_name="Supplier",
        product_type="Widget",
        country_of_origin="US",
        risk_level=RiskLevel.LOW,
        status=CaseStatus.PROCESSING,
    )
    test_db_session.add(draft_case)
    test_db_session.add(processing_case)
    await test_db_session.commit()

    app = create_app()

    async def mock_get_session(request):
        yield test_db_session

    from app.api.cases import get_session as original_get_session

    app.dependency_overrides[original_get_session] = mock_get_session

    client = TestClient(app)
    response = client.get("/api/v1/cases?status=draft")
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "Draft Case"
    assert data["total"] == 1


@pytest.mark.asyncio
async def test_update_case_success(test_db_session: AsyncSession):
    """PATCH /cases/{id} updates case fields."""
    case = ComplianceCase(
        title="Original Title",
        supplier_name="Supplier",
        product_type="Widget",
        country_of_origin="US",
        risk_level=RiskLevel.LOW,
        status=CaseStatus.DRAFT,
    )
    test_db_session.add(case)
    await test_db_session.commit()
    await test_db_session.refresh(case)

    app = create_app()

    async def mock_get_session(request):
        yield test_db_session

    from app.api.cases import get_session as original_get_session

    app.dependency_overrides[original_get_session] = mock_get_session

    client = TestClient(app)
    update_payload = {
        "status": "processing",
        "risk_level": "high",
    }

    response = client.patch(f"/api/v1/cases/{case.id}", json=update_payload)
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "processing"
    assert data["risk_level"] == "high"


@pytest.mark.asyncio
async def test_update_case_partial(test_db_session: AsyncSession):
    """PATCH /cases/{id} supports partial updates."""
    case = ComplianceCase(
        title="Original",
        supplier_name="Original Supplier",
        product_type="Widget",
        country_of_origin="US",
        risk_level=RiskLevel.LOW,
    )
    test_db_session.add(case)
    await test_db_session.commit()
    await test_db_session.refresh(case)

    app = create_app()

    async def mock_get_session(request):
        yield test_db_session

    from app.api.cases import get_session as original_get_session

    app.dependency_overrides[original_get_session] = mock_get_session

    client = TestClient(app)
    update_payload = {"supplier_name": "New Supplier"}

    response = client.patch(f"/api/v1/cases/{case.id}", json=update_payload)
    assert response.status_code == 200

    data = response.json()
    assert data["supplier_name"] == "New Supplier"
    assert data["title"] == "Original"


@pytest.mark.asyncio
async def test_update_case_not_found(test_db_session: AsyncSession):
    """PATCH /cases/{id} returns 404 for non-existent case."""
    app = create_app()

    async def mock_get_session(request):
        yield test_db_session

    from app.api.cases import get_session as original_get_session

    app.dependency_overrides[original_get_session] = mock_get_session

    client = TestClient(app)
    fake_id = uuid4()
    update_payload = {"status": "processing"}

    response = client.patch(f"/api/v1/cases/{fake_id}", json=update_payload)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_case_duplicate_title(test_db_session: AsyncSession):
    """PATCH /cases/{id} returns 409 when updating to existing title."""
    case1 = ComplianceCase(
        title="Case 1",
        supplier_name="Supplier 1",
        product_type="Widget",
        country_of_origin="US",
        risk_level=RiskLevel.LOW,
    )
    case2 = ComplianceCase(
        title="Case 2",
        supplier_name="Supplier 2",
        product_type="Widget",
        country_of_origin="US",
        risk_level=RiskLevel.LOW,
    )
    test_db_session.add(case1)
    test_db_session.add(case2)
    await test_db_session.commit()
    await test_db_session.refresh(case1)
    await test_db_session.refresh(case2)

    app = create_app()

    async def mock_get_session(request):
        yield test_db_session

    from app.api.cases import get_session as original_get_session

    app.dependency_overrides[original_get_session] = mock_get_session

    client = TestClient(app)
    update_payload = {"title": "Case 1"}

    response = client.patch(f"/api/v1/cases/{case2.id}", json=update_payload)
    assert response.status_code == 409
