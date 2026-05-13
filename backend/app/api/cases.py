"""REST API endpoints for case management."""

import logging
from collections.abc import AsyncGenerator
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compliance_case import ComplianceCase
from app.schemas.compliance_case import (
    ComplianceCaseCreate,
    ComplianceCaseListResponse,
    ComplianceCaseRead,
    ComplianceCaseUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cases", tags=["cases"])


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Get database session from request app state."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


async def _handle_integrity_error(
    e: IntegrityError,
    session: AsyncSession,
    context: str = "",
) -> NoReturn:
    """Handle integrity errors with constraint name matching.

    Attempts to match by constraint name first (most robust), falls back to
    substring matching for compatibility.
    """
    await session.rollback()

    # Try constraint-name matching first (most robust)
    if hasattr(e, "orig") and e.orig and hasattr(e.orig, "constraint_name"):
        constraint_name = getattr(e.orig, "constraint_name", "")
        if constraint_name == "uq_compliance_cases_title":
            logger.warning(f"Duplicate case title {context}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A case with this title already exists",
            )

    # Fallback: substring match (for compatibility)
    if "title" in str(e).lower():
        logger.warning(f"Duplicate case title {context}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A case with this title already exists",
        )

    # Generic constraint violation
    logger.error(f"Database constraint violation {context}: {e}")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database constraint violation",
    )


async def _get_case_or_404(
    case_id: UUID,
    session: AsyncSession,
) -> ComplianceCase:
    """Fetch a case by ID or raise 404 HTTPException."""
    result = await session.execute(select(ComplianceCase).where(ComplianceCase.id == case_id))
    db_case = result.scalars().first()

    if db_case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case with id {case_id} not found",
        )

    return db_case


@router.post(
    "",
    response_model=ComplianceCaseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new compliance case",
)
async def create_case(
    case_data: ComplianceCaseCreate,
    session: AsyncSession = Depends(get_session),
) -> ComplianceCaseRead:
    """Create a new compliance case.

    The case status is always initialized to 'draft'. Risk level must be one of:
    low, medium, high, or critical.

    Args:
        case_data: Case creation payload
        session: Database session

    Returns:
        Newly created case with auto-generated fields (id, timestamps)

    Raises:
        HTTPException: 409 if title already exists
    """
    try:
        db_case = ComplianceCase(
            title=case_data.title,
            supplier_name=case_data.supplier_name,
            product_type=case_data.product_type,
            country_of_origin=case_data.country_of_origin,
            risk_level=case_data.risk_level,
        )
        session.add(db_case)
        await session.commit()
        await session.refresh(db_case)
        return ComplianceCaseRead.model_validate(db_case)
    except IntegrityError as e:
        await _handle_integrity_error(e, session, "during case creation")


@router.get(
    "/{case_id}",
    response_model=ComplianceCaseRead,
    summary="Get case details by ID",
)
async def get_case(
    case_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ComplianceCaseRead:
    """Get a specific compliance case by its ID.

    Args:
        case_id: UUID of the case to retrieve
        session: Database session

    Returns:
        Case details if found

    Raises:
        HTTPException: 404 if case not found
    """
    db_case = await _get_case_or_404(case_id, session)
    return ComplianceCaseRead.model_validate(db_case)


@router.get(
    "",
    response_model=ComplianceCaseListResponse,
    summary="List compliance cases with pagination",
)
async def list_cases(
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    risk_level: Annotated[str | None, Query()] = None,
    supplier_name: Annotated[str | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
) -> ComplianceCaseListResponse:
    """List compliance cases with pagination and optional filtering.

    Query parameters:
    - skip: Number of cases to skip (default: 0)
    - limit: Max cases to return (default: 50, max: 1000)
    - status: Filter by case status (optional)
    - risk_level: Filter by risk level (optional)
    - supplier_name: Filter by supplier name (partial match, optional)

    Returns:
        Paginated list with items, total count, and pagination metadata
    """
    query = select(ComplianceCase)

    if status_filter:
        query = query.where(ComplianceCase.status == status_filter)
    if risk_level:
        query = query.where(ComplianceCase.risk_level == risk_level)
    if supplier_name:
        query = query.where(ComplianceCase.supplier_name.ilike(f"%{supplier_name}%"))

    # Use COUNT(*) for total instead of materializing all rows
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(desc(ComplianceCase.created_at))
    query = query.offset(skip).limit(limit)

    result = await session.execute(query)
    cases = result.scalars().all()

    return ComplianceCaseListResponse(
        items=[ComplianceCaseRead.model_validate(case) for case in cases],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.patch(
    "/{case_id}",
    response_model=ComplianceCaseRead,
    summary="Update a compliance case",
)
async def update_case(
    case_id: UUID,
    case_data: ComplianceCaseUpdate,
    session: AsyncSession = Depends(get_session),
) -> ComplianceCaseRead:
    """Update a compliance case with partial update support.

    Only provided fields are updated. The case must exist.

    Args:
        case_id: UUID of the case to update
        case_data: Partial case update payload
        session: Database session

    Returns:
        Updated case

    Raises:
        HTTPException: 404 if case not found
        HTTPException: 409 if title already exists
    """
    db_case = await _get_case_or_404(case_id, session)

    update_data = case_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_case, field, value)

    try:
        session.add(db_case)
        await session.commit()
        await session.refresh(db_case)
        return ComplianceCaseRead.model_validate(db_case)
    except IntegrityError as e:
        conflicting_title = update_data.get("title", "<unknown>")
        await _handle_integrity_error(
            e, session, f"during case update (title={conflicting_title!r})"
        )
