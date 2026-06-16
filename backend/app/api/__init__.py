"""API routes."""

from fastapi import APIRouter

from app.api.cases import router as cases_router
from app.api.documents import router as documents_router
from app.api.evidence_gaps import router as evidence_gaps_router
from app.api.health import router as health_router
from app.api.timeline import router as timeline_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(cases_router)
api_router.include_router(documents_router, tags=["documents"])
api_router.include_router(timeline_router)
api_router.include_router(evidence_gaps_router)
