"""Tests for compliance case API endpoints.

Note: Full integration tests require a live database and proper async test harness.
These are placeholder structure tests that verify the API module loads correctly.
"""

from app.api.cases import create_case, get_case, list_cases, router, update_case
from app.main import create_app
from app.models.compliance_case import ComplianceCase
from app.schemas.compliance_case import ComplianceCaseListResponse


def test_cases_router_exists():
    """Verify cases router is properly defined."""
    assert router is not None
    assert router.prefix == "/cases"
    assert len(router.routes) == 4


def test_create_case_function_exists():
    """Verify create_case endpoint function exists."""
    assert create_case is not None
    assert callable(create_case)


def test_get_case_function_exists():
    """Verify get_case endpoint function exists."""
    assert get_case is not None
    assert callable(get_case)


def test_list_cases_function_exists():
    """Verify list_cases endpoint function exists."""
    assert list_cases is not None
    assert callable(list_cases)


def test_update_case_function_exists():
    """Verify update_case endpoint function exists."""
    assert update_case is not None
    assert callable(update_case)


def test_app_includes_cases_router():
    """Verify FastAPI app includes cases router."""
    app = create_app()
    # Check that /api/v1/cases routes exist
    routes = [route.path for route in app.routes]
    assert any("/cases" in route for route in routes)


def test_compliance_case_list_response_schema():
    """Verify ComplianceCaseListResponse schema is valid."""
    response = ComplianceCaseListResponse(items=[], total=0, skip=0, limit=50)
    assert response.total == 0
    assert response.skip == 0
    assert response.limit == 50
    assert response.items == []
    assert len(response.model_fields) == 4


def test_compliance_case_model_exists():
    """Verify ComplianceCase model exists and has required fields."""
    assert hasattr(ComplianceCase, "__tablename__")
    assert ComplianceCase.__tablename__ == "compliance_cases"
