"""AI-related Celery tasks for embedding generation and processing."""

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.db.repositories.document import DocumentRepository
from app.db.repositories.document_extraction import DocumentExtractionRepository
from app.db.repositories.job import JobRepository
from app.services.embedding_service import EmbeddingError, EmbeddingService
from app.utils.idempotency import generate_idempotency_key

logger = logging.getLogger(__name__)


async def _get_session() -> AsyncSession:
    """Get a new session from the shared factory.

    Returns:
        AsyncSession: New session from the shared factory
    """
    from app.tasks.document_tasks import _get_session as get_doc_session

    return await get_doc_session()


@celery_app.task(
    name="app.tasks.ai_tasks.generate_embeddings",
    bind=True,
    autoretry_for=(EmbeddingError, OSError, TimeoutError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def generate_embeddings(self, job_id: str) -> dict:
    """Generate embeddings for document chunks.

    Async Celery task that generates vector embeddings for all chunks
    of a document. Uses Task 27 idempotency key to prevent duplicates.

    Args:
        job_id: UUID of job to process

    Returns:
        Dict with status and embedding count

    Raises:
        EmbeddingError: If embedding generation fails
        ValueError: If job or document not found
    """
    import asyncio

    return asyncio.run(_generate_embeddings_async(UUID(job_id)))


async def _generate_embeddings_async(job_id: UUID) -> dict:
    """Async implementation of embedding generation.

    Args:
        job_id: UUID of job to process

    Returns:
        Dict with status and embedding count

    Raises:
        EmbeddingError: If embedding generation fails
        ValueError: If job or document not found
    """
    session = await _get_session()

    try:
        job_repo = JobRepository()
        doc_repo = DocumentRepository()
        ext_repo = DocumentExtractionRepository()

        # Read job
        job = await job_repo.read(session, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Read document
        doc_id = job.job_metadata.get("document_id") if job.job_metadata else None
        if not doc_id:
            raise ValueError(f"Job {job_id} has no document_id in metadata")

        document = await doc_repo.read(session, UUID(doc_id))
        if not document:
            raise ValueError(f"Document {doc_id} not found")

        # Read extraction (chunks)
        extraction = await ext_repo.read(session, UUID(doc_id))
        if not extraction or not extraction.chunks:
            raise ValueError(f"No chunks found for document {doc_id}")

        # Prepare chunks for embedding
        chunks = extraction.chunks
        if not isinstance(chunks, list):
            raise ValueError("Invalid chunk format in extraction")

        # Generate idempotency key for deduplication
        job_metadata = job.job_metadata if isinstance(job.job_metadata, dict) else {}
        job_type_value = str(job.job_type) if job.job_type else job.job_type
        # Include operation type in metadata to distinguish from other job types
        metadata_with_op = {**job_metadata, "_operation": "embeddings"}
        idempotency_key = generate_idempotency_key(
            document_id=document.id,
            job_type=job_type_value,
            job_metadata=metadata_with_op,
        )

        # Check if embeddings already generated (idempotency)
        try:
            cached_result = await session.execute(
                text("SELECT embedding_count FROM embedding_job_cache WHERE idempotency_key = :key"),
                {"key": idempotency_key},
            )
            row = cached_result.fetchone()
            if row:
                logger.info(
                    f"[IDEMPOTENT] Cache HIT for embeddings job {job_id}: "
                    f"using existing embeddings"
                )
                return {"status": "cached", "embedding_count": row[0]}
        except Exception:
            # Cache miss or error, continue with generation
            pass

        # Initialize embedding service
        service = EmbeddingService()
        logger.info(
            f"Starting embedding generation for document {doc_id} "
            f"with {len(chunks)} chunks using {service.provider.get_model_name()}"
        )

        # Generate embeddings
        try:
            embeddings = await service.embed_chunks(chunks)
        except EmbeddingError as e:
            logger.error(f"Embedding generation failed for job {job_id}: {e}")
            raise

        logger.info(
            f"Embedding generation complete for job {job_id}: "
            f"generated {len(embeddings)} embeddings"
        )

        # Store embeddings in extraction (deferred to Task 34 for vector DB)
        # For now, update chunk_count as proxy
        extraction.chunk_count = len(embeddings)
        extraction.extraction_status = "embeddings_generated"
        await session.commit()

        return {
            "status": "success",
            "embedding_count": len(embeddings),
            "model": service.provider.get_model_name(),
            "dimension": service.provider.get_dimension(),
        }

    except Exception as e:
        logger.error(f"Embedding generation task failed for job {job_id}: {e}")
        raise
    finally:
        await session.close()
