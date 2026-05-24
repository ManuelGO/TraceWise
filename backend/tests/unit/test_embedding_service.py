"""Unit tests for embedding service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from app.services.embedding_service import (
    EmbeddingError,
    EmbeddingProviderFactory,
    EmbeddingService,
    OpenRouterEmbeddingProvider,
)


@pytest.fixture
def mock_embedding_settings():
    """Mock settings for embedding service tests."""
    mock_settings = MagicMock()
    mock_settings.OPENROUTER_API_KEY = SecretStr("config-key")
    mock_settings.EMBEDDING_PRIMARY_MODEL = "openai/text-embedding-3-small"
    mock_settings.EMBEDDING_FALLBACK_MODEL = "nomic-ai/nomic-embed-text-v1"
    mock_settings.EMBEDDING_BATCH_SIZE = 20
    mock_settings.EMBEDDING_CACHE_TTL_SECONDS = 86400
    mock_settings.EMBEDDING_CACHE_ENABLED = True
    return mock_settings


class TestOpenRouterEmbeddingProvider:
    """Tests for OpenRouter embedding provider."""

    def test_provider_init_with_api_key(self):
        """Test provider initialization with API key."""
        provider = OpenRouterEmbeddingProvider(api_key="test-key-123")

        assert provider.api_key == "test-key-123"
        assert provider.primary_model == "openai/text-embedding-3-small"
        assert provider.fallback_model == "nomic-ai/nomic-embed-text-v1"
        assert provider.current_model == provider.primary_model

    def test_provider_init_invalid_api_key(self):
        """Test provider initialization with empty API key raises error."""
        with pytest.raises(ValueError, match="API key cannot be empty"):
            OpenRouterEmbeddingProvider(api_key="")

    def test_provider_init_custom_models(self):
        """Test provider initialization with custom models."""
        provider = OpenRouterEmbeddingProvider(
            api_key="test-key",
            primary_model="openai/text-embedding-3-large",
            fallback_model="cohere/embed-english-v3.0",
        )

        assert provider.primary_model == "openai/text-embedding-3-large"
        assert provider.fallback_model == "cohere/embed-english-v3.0"

    def test_get_dimension_primary_model(self):
        """Test getting dimension for primary model."""
        provider = OpenRouterEmbeddingProvider(api_key="test-key")
        dimension = provider.get_dimension()

        assert dimension == 1536  # OpenAI text-embedding-3-small

    def test_get_dimension_fallback_model(self):
        """Test getting dimension for fallback model."""
        provider = OpenRouterEmbeddingProvider(api_key="test-key")
        provider.current_model = "nomic-ai/nomic-embed-text-v1"
        dimension = provider.get_dimension()

        assert dimension == 768  # Nomic embed text

    def test_get_model_name(self):
        """Test getting current model name."""
        provider = OpenRouterEmbeddingProvider(api_key="test-key")
        assert provider.get_model_name() == "openai/text-embedding-3-small"

    @pytest.mark.asyncio
    async def test_embed_single_text(self):
        """Test embedding a single text."""
        provider = OpenRouterEmbeddingProvider(api_key="test-key")

        # Mock the HTTP call
        with patch("app.services.embedding_service.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": [{"embedding": [0.1, 0.2, 0.3] * 512}]  # 1536 dims
            }
            mock_response.raise_for_status = MagicMock()

            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            embeddings = await provider.embed(["Hello world"])

            assert len(embeddings) == 1
            assert len(embeddings[0]) == 1536

    @pytest.mark.asyncio
    async def test_embed_multiple_texts(self):
        """Test embedding multiple texts."""
        provider = OpenRouterEmbeddingProvider(api_key="test-key")

        with patch("app.services.embedding_service.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": [
                    {"embedding": [0.1] * 1536},
                    {"embedding": [0.2] * 1536},
                    {"embedding": [0.3] * 1536},
                ]
            }
            mock_response.raise_for_status = MagicMock()

            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            embeddings = await provider.embed(["Text 1", "Text 2", "Text 3"])

            assert len(embeddings) == 3
            assert all(len(e) == 1536 for e in embeddings)

    @pytest.mark.asyncio
    async def test_embed_empty_list(self):
        """Test embedding empty list returns empty list."""
        provider = OpenRouterEmbeddingProvider(api_key="test-key")
        embeddings = await provider.embed([])

        assert embeddings == []

    @pytest.mark.asyncio
    async def test_embed_api_timeout(self):
        """Test embedding with API timeout on both models raises error."""
        provider = OpenRouterEmbeddingProvider(api_key="test-key")

        with patch("app.services.embedding_service.httpx.AsyncClient") as mock_client:
            import httpx

            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.TimeoutException("timeout")
            )

            with pytest.raises(EmbeddingError, match="Both primary and fallback"):
                await provider.embed(["Hello"])

    @pytest.mark.asyncio
    async def test_embed_fallback_on_primary_failure(self):
        """Test fallback to secondary model on primary failure."""
        provider = OpenRouterEmbeddingProvider(api_key="test-key")

        with patch("app.services.embedding_service.httpx.AsyncClient") as mock_client:
            import httpx

            call_count = 0

            async def post_side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # First call (primary) fails with status error
                    mock_response = MagicMock()
                    mock_response.status_code = 429
                    error = httpx.HTTPStatusError(
                        "rate limited", request=MagicMock(), response=mock_response
                    )
                    raise error
                else:
                    # Second call (fallback) succeeds
                    response = MagicMock()
                    response.json.return_value = {
                        "data": [{"embedding": [0.1] * 768}]  # Nomic dimension
                    }
                    response.raise_for_status = MagicMock()
                    return response

            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=post_side_effect
            )

            embeddings = await provider.embed(["Hello"])

            assert len(embeddings) == 1
            assert len(embeddings[0]) == 768  # Fallback model dimension
            assert provider.current_model == provider.fallback_model


class TestEmbeddingProviderFactory:
    """Tests for provider factory."""

    def test_register_provider(self):
        """Test registering a provider."""
        factory = EmbeddingProviderFactory()
        assert "openrouter" in factory.list_providers()

    def test_create_provider(self):
        """Test creating a provider from factory."""
        provider = EmbeddingProviderFactory.create(
            "openrouter",
            api_key="test-key",
        )

        assert provider is not None
        assert isinstance(provider, OpenRouterEmbeddingProvider)

    def test_create_unknown_provider_raises_error(self):
        """Test creating unknown provider raises error."""
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            EmbeddingProviderFactory.create("unknown-provider", api_key="test-key")

    def test_list_providers(self):
        """Test listing available providers."""
        providers = EmbeddingProviderFactory.list_providers()

        assert isinstance(providers, list)
        assert "openrouter" in providers


class TestEmbeddingService:
    """Tests for embedding service."""

    def test_service_init_with_provider(self):
        """Test service initialization with custom provider."""
        provider = OpenRouterEmbeddingProvider(api_key="test-key")
        service = EmbeddingService(provider=provider)

        assert service.provider == provider
        assert service.batch_size == 20
        assert service.cache_enabled is True

    def test_service_init_with_provider_factory(self, mock_embedding_settings):
        """Test service initialization using provider factory."""
        with patch("app.services.embedding_service.get_settings") as mock_settings:
            mock_settings.return_value = mock_embedding_settings

            service = EmbeddingService(provider_name="openrouter")

            assert service.provider is not None
            assert isinstance(service.provider, OpenRouterEmbeddingProvider)

    @patch("app.services.embedding_service.get_settings")
    def test_service_init_without_provider(self, mock_settings, mock_embedding_settings):
        """Test service initialization creates provider from config."""
        mock_settings.return_value = mock_embedding_settings

        service = EmbeddingService()

        assert service.provider is not None
        assert isinstance(service.provider, OpenRouterEmbeddingProvider)

    @patch("app.services.embedding_service.get_settings")
    def test_service_init_missing_api_key(self, mock_settings, mock_embedding_settings):
        """Test service initialization fails without API key."""
        mock_embedding_settings.OPENROUTER_API_KEY = SecretStr("")
        mock_settings.return_value = mock_embedding_settings

        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            EmbeddingService()

    def test_make_cache_key(self):
        """Test cache key generation."""
        provider = OpenRouterEmbeddingProvider(api_key="test-key")
        service = EmbeddingService(provider=provider)

        key1 = service._make_cache_key("hello world", "openai/text-embedding-3-small")
        key2 = service._make_cache_key("hello world", "openai/text-embedding-3-small")
        key3 = service._make_cache_key("goodbye world", "openai/text-embedding-3-small")

        # Same text and model should produce same key
        assert key1 == key2
        # Different text should produce different key
        assert key1 != key3
        # Key should have expected format
        assert key1.startswith("embedding:openai/text-embedding-3-small:")
        # Verify SHA256 hash is full 64-char hex, not truncated
        parts = key1.split(":")
        assert len(parts) == 3  # embedding, model, hash
        assert len(parts[2]) == 64  # Full SHA256 hex digest
        assert all(c in "0123456789abcdef" for c in parts[2])

    @pytest.mark.asyncio
    async def test_embed_chunks_single_chunk(self):
        """Test embedding a single chunk."""
        provider = OpenRouterEmbeddingProvider(api_key="test-key")
        service = EmbeddingService(provider=provider)

        with patch.object(service.provider, "embed", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [[0.1] * 1536]

            chunks = [{"chunk_id": "1", "text": "Hello world"}]
            results = await service.embed_chunks(chunks)

            assert len(results) == 1
            assert results[0]["chunk_id"] == "1"
            assert len(results[0]["vector"]) == 1536
            assert results[0]["model_name"] == "openai/text-embedding-3-small"
            assert results[0]["embedding_dim"] == 1536

    @pytest.mark.asyncio
    async def test_embed_chunks_multiple_chunks(self):
        """Test embedding multiple chunks."""
        provider = OpenRouterEmbeddingProvider(api_key="test-key")
        service = EmbeddingService(provider=provider)

        with patch.object(service.provider, "embed", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [[0.1] * 1536, [0.2] * 1536]

            chunks = [
                {"chunk_id": "1", "text": "Text 1"},
                {"chunk_id": "2", "text": "Text 2"},
            ]
            results = await service.embed_chunks(chunks)

            assert len(results) == 2
            assert results[0]["chunk_id"] == "1"
            assert results[1]["chunk_id"] == "2"

    @pytest.mark.asyncio
    async def test_embed_chunks_empty(self):
        """Test embedding empty chunk list."""
        provider = OpenRouterEmbeddingProvider(api_key="test-key")
        service = EmbeddingService(provider=provider)

        results = await service.embed_chunks([])

        assert results == []

    @pytest.mark.asyncio
    async def test_embed_chunks_with_caching_disabled(self):
        """Test embedding with cache disabled."""
        provider = OpenRouterEmbeddingProvider(api_key="test-key")
        service = EmbeddingService(provider=provider)
        service.cache_enabled = False

        with patch.object(service.provider, "embed", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [[0.1] * 1536]

            chunks = [{"chunk_id": "1", "text": "Hello"}]
            results = await service.embed_chunks(chunks)

            assert len(results) == 1
            assert mock_embed.call_count == 1

    @pytest.mark.asyncio
    async def test_embed_chunks_batch_processing(self):
        """Test batch processing of large chunk list."""
        provider = OpenRouterEmbeddingProvider(api_key="test-key")
        service = EmbeddingService(provider=provider)
        service.batch_size = 5

        with patch.object(service.provider, "embed", new_callable=AsyncMock) as mock_embed:
            # Return appropriate number of embeddings for each batch
            mock_embed.side_effect = [
                [[0.1] * 1536 for _ in range(5)],  # First batch
                [[0.2] * 1536 for _ in range(5)],  # Second batch
            ]

            chunks = [{"chunk_id": str(i), "text": f"Text {i}"} for i in range(10)]
            results = await service.embed_chunks(chunks)

            assert len(results) == 10
            # Provider.embed should be called twice (batches of 5)
            assert mock_embed.call_count == 2

    @pytest.mark.asyncio
    async def test_embed_chunks_deduplicates_identical_text(self):
        """Test that identical text is only embedded once."""
        provider = OpenRouterEmbeddingProvider(api_key="test-key")
        service = EmbeddingService(provider=provider)

        with patch.object(service.provider, "embed", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [[0.1] * 1536]

            chunks = [
                {"chunk_id": "1", "text": "Same text"},
                {"chunk_id": "2", "text": "Same text"},
            ]
            results = await service.embed_chunks(chunks)

            assert len(results) == 2
            # Only one unique text to embed
            assert mock_embed.call_count == 1
            # But both chunks have results
            assert results[0]["vector"] == results[1]["vector"]
