"""Integration tests for embedding generation Celery task."""

import pytest


class TestEmbeddingTask:
    """Tests for embedding generation task."""

    def test_embedding_task_configuration(self):
        """Test generate_embeddings task is correctly configured."""
        from app.services.embedding_service import EmbeddingError
        from app.tasks.ai_tasks import generate_embeddings

        assert generate_embeddings.name == "app.tasks.ai_tasks.generate_embeddings"
        assert generate_embeddings.autoretry_for == (
            EmbeddingError,
            OSError,
            TimeoutError,
        )
        assert generate_embeddings.max_retries == 3

    def test_embedding_task_has_retry_backoff(self):
        """Test generate_embeddings task has exponential backoff."""
        from app.tasks.ai_tasks import generate_embeddings

        assert generate_embeddings.retry_backoff is True
        assert generate_embeddings.retry_backoff_max == 600
        assert generate_embeddings.retry_jitter is True

    def test_embedding_task_can_be_enqueued(self):
        """Test that generate_embeddings task can be enqueued."""
        from app.tasks.ai_tasks import generate_embeddings

        assert hasattr(generate_embeddings, "delay")
        assert callable(generate_embeddings.delay)

    def test_embedding_service_imported(self):
        """Test that embedding service can be imported in task."""
        from app.tasks.ai_tasks import EmbeddingService

        assert EmbeddingService is not None

    def test_embedding_error_imported(self):
        """Test that EmbeddingError can be imported in task."""
        from app.tasks.ai_tasks import EmbeddingError

        assert EmbeddingError is not None

    @pytest.mark.asyncio
    async def test_embedding_service_initialization(self):
        """Test embedding service initializes correctly."""
        from unittest.mock import patch

        from pydantic import SecretStr

        from app.services.embedding_service import EmbeddingService

        with patch("app.services.embedding_service.get_settings") as mock_settings:
            mock_settings.return_value.OPENROUTER_API_KEY = SecretStr("test-key")
            mock_settings.return_value.EMBEDDING_PRIMARY_MODEL = (
                "openai/text-embedding-3-small"
            )
            mock_settings.return_value.EMBEDDING_FALLBACK_MODEL = (
                "nomic-ai/nomic-embed-text-v1"
            )
            mock_settings.return_value.EMBEDDING_BATCH_SIZE = 20
            mock_settings.return_value.EMBEDDING_CACHE_TTL_SECONDS = 86400
            mock_settings.return_value.EMBEDDING_CACHE_ENABLED = True

            service = EmbeddingService()

            assert service.provider is not None
            assert service.batch_size == 20
            assert service.cache_enabled is True

    @pytest.mark.asyncio
    async def test_embedding_with_sample_chunks(self):
        """Test embedding generation with sample chunks."""
        from unittest.mock import AsyncMock, patch

        from pydantic import SecretStr

        from app.services.embedding_service import EmbeddingService

        with patch("app.services.embedding_service.get_settings") as mock_settings:

            mock_settings.return_value.OPENROUTER_API_KEY = SecretStr("test-key")
            mock_settings.return_value.EMBEDDING_PRIMARY_MODEL = (
                "openai/text-embedding-3-small"
            )
            mock_settings.return_value.EMBEDDING_FALLBACK_MODEL = (
                "nomic-ai/nomic-embed-text-v1"
            )
            mock_settings.return_value.EMBEDDING_BATCH_SIZE = 20
            mock_settings.return_value.EMBEDDING_CACHE_TTL_SECONDS = 86400
            mock_settings.return_value.EMBEDDING_CACHE_ENABLED = False

            service = EmbeddingService()

            # Mock the provider
            with patch.object(
                service.provider, "embed", new_callable=AsyncMock
            ) as mock_embed:
                mock_embed.return_value = [[0.1] * 1536]

                chunks = [{"chunk_id": "1", "text": "Sample text for embedding"}]
                embeddings = await service.embed_chunks(chunks)

                assert len(embeddings) == 1
                assert embeddings[0]["chunk_id"] == "1"
                assert len(embeddings[0]["vector"]) == 1536

    def test_idempotency_key_generation(self):
        """Test idempotency key generation for embedding tasks."""
        from uuid import uuid4

        from app.utils.idempotency import generate_idempotency_key

        doc_id = uuid4()
        job_type = "embedding_generation"
        job_metadata = {"some": "metadata"}

        key1 = generate_idempotency_key(
            document_id=doc_id,
            job_type=job_type,
            job_metadata=job_metadata,
        )
        key2 = generate_idempotency_key(
            document_id=doc_id,
            job_type=job_type,
            job_metadata=job_metadata,
        )

        # Same inputs should produce same key
        assert key1 == key2
        # Key should be 64 hex characters (SHA256)
        assert len(key1) == 64
        assert all(c in "0123456789abcdef" for c in key1)
