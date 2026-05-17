"""REST API endpoints for document uploads."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_auth
from app.config import get_settings
from app.exceptions import FileSizeTooLargeError, MimeTypeNotAllowedError
from app.models.compliance_case import ComplianceCase
from app.models.document import Document
from app.models.enums import JobStatus, JobType
from app.models.job import Job
from app.schemas.document import DocumentRead
from app.services.file_handler import (
    classify_document_type,
    delete_stored_file,
    generate_storage_path,
    store_file,
    validate_file_size,
    validate_mime_type_by_magic_bytes,
)
from app.tasks.document_tasks import extract_text_task, validate_document_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cases", tags=["documents"])


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
    "/{case_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document to a compliance case",
    dependencies=[Depends(require_auth)],
)
async def upload_document(
    case_id: UUID,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> DocumentRead:
    """Upload a document to a compliance case.

    Requires authentication (bearer token in Authorization header).

    Args:
        case_id: UUID of the compliance case
        file: File to upload (multipart form data)
        session: Database session

    Returns:
        Document metadata including storage path and timestamps

    Raises:
        HTTPException: 400 if required fields missing
        HTTPException: 401 if authentication required
        HTTPException: 404 if case not found
        HTTPException: 413 if file exceeds size limit
        HTTPException: 415 if MIME type not allowed
        HTTPException: 500 if file storage fails
    """
    settings = get_settings()
    storage_path: str | None = None
    filename = file.filename or "unnamed"

    try:
        # Validate case exists
        await _get_case_or_404(case_id, session)

        # Read file content
        file_content = await file.read()
        file_size = len(file_content)

        # Validate file size
        validate_file_size(file_size, settings.get_max_file_size_bytes())

        # Validate MIME type via magic bytes (not client header)
        actual_mime = validate_mime_type_by_magic_bytes(
            file_content, settings.get_allowed_mime_types_list(), filename
        )

        # Classify document type based on filename and MIME type
        document_type = classify_document_type(filename, actual_mime)

        # Generate storage path with uniqueness handling and path traversal protection
        storage_path = generate_storage_path(case_id, filename, settings.STORAGE_PATH)

        # Store file
        store_file(file_content, storage_path, settings.STORAGE_PATH)

        # Create document record in database
        db_document = Document(
            case_id=case_id,
            filename=filename,
            document_type=document_type,
            storage_path=storage_path,
            file_size=file_size,
            mime_type=actual_mime,
        )
        session.add(db_document)
        await session.commit()
        await session.refresh(db_document)

        logger.info(
            f"Document uploaded: id={db_document.id}, case_id={case_id}, "
            f"filename={filename}, size={file_size}"
        )

        # Create validation job and enqueue task
        validation_job = Job(
            case_id=case_id,
            job_type=JobType.VALIDATE_DOCUMENT,
            status=JobStatus.PENDING,
            job_metadata={"document_id": str(db_document.id)},
        )
        session.add(validation_job)
        await session.commit()
        await session.refresh(validation_job)

        logger.info(f"Validation job created: id={validation_job.id}")

        # Enqueue validation task (async, non-blocking)
        validate_document_task.delay(str(validation_job.id))
        logger.info(f"Validation task enqueued for job {validation_job.id}")

        # Create extraction job and enqueue task
        extraction_job = Job(
            case_id=case_id,
            job_type=JobType.EXTRACT_TEXT,
            status=JobStatus.PENDING,
            job_metadata={"document_id": str(db_document.id)},
        )
        session.add(extraction_job)
        await session.commit()
        await session.refresh(extraction_job)

        logger.info(f"Extraction job created: id={extraction_job.id}")

        # Enqueue extraction task (async, non-blocking)
        extract_text_task.delay(str(extraction_job.id))
        logger.info(f"Extraction task enqueued for job {extraction_job.id}")

        return DocumentRead.model_validate(db_document)

    except FileSizeTooLargeError as e:
        logger.warning(f"Validation error during file upload: {e}")
        if storage_path is not None:
            try:
                delete_stored_file(storage_path, settings.STORAGE_PATH)
            except Exception as cleanup_error:
                logger.error(f"Error during file cleanup: {cleanup_error}")
        raise HTTPException(
            status_code=status.HTTP_413_PAYLOAD_TOO_LARGE,
            detail="File size exceeds maximum allowed",
        )

    except MimeTypeNotAllowedError as e:
        logger.warning(f"Validation error during file upload: {e}")
        if storage_path is not None:
            try:
                delete_stored_file(storage_path, settings.STORAGE_PATH)
            except Exception as cleanup_error:
                logger.error(f"Error during file cleanup: {cleanup_error}")
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File type is not allowed",
        )

    except ValueError as e:
        logger.warning(f"Validation error during file upload: {e}")
        if storage_path is not None:
            try:
                delete_stored_file(storage_path, settings.STORAGE_PATH)
            except Exception as cleanup_error:
                logger.error(f"Error during file cleanup: {cleanup_error}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File validation failed: {e}",
        )

    except OSError as e:
        logger.error(f"File storage error: {e}")
        if storage_path is not None:
            try:
                delete_stored_file(storage_path, settings.STORAGE_PATH)
            except Exception as cleanup_error:
                logger.error(f"Error during file cleanup: {cleanup_error}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store file",
        ) from e

    except Exception as e:
        logger.error(f"Unexpected error during file upload: {e}")
        if storage_path is not None:
            try:
                delete_stored_file(storage_path, settings.STORAGE_PATH)
            except Exception as cleanup_error:
                logger.error(f"Error during file cleanup: {cleanup_error}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during file upload",
        ) from e
