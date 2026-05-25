"""Embedding service for generating vector embeddings from text chunks."""

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, ClassVar

import httpx

from app.config import get_settings
from app.monitoring.retry_metrics import _sanitize_log

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""

    pass


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (one per input text)

        Raises:
            EmbeddingError: If embedding generation fails
        """
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        """Get the embedding dimension for this provider.

        Returns:
            Number of dimensions in embeddings
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Get the model name for this provider.

        Returns:
            Model name for metadata tracking
        """
        pass


class EmbeddingProviderFactory:
    """Factory for creating embedding providers."""

    _providers: ClassVar[dict[str, type[EmbeddingProvider]]] = {}

    @classmethod
    def register(cls, name: str, provider_class: type[EmbeddingProvider]) -> None:
        """Register a provider class.

        Args:
            name: Provider name
            provider_class: Provider class
        """
        cls._providers[name] = provider_class

    @classmethod
    def create(cls, provider_name: str, **kwargs: Any) -> EmbeddingProvider:
        """Create a provider instance.

        Args:
            provider_name: Name of provider to create
            **kwargs: Arguments to pass to provider constructor

        Returns:
            Provider instance

        Raises:
            ValueError: If provider not found
        """
        if provider_name not in cls._providers:
            raise ValueError(
                f"Unknown embedding provider: {provider_name}. "
                f"Available: {list(cls._providers.keys())}"
            )

        provider_class = cls._providers[provider_name]
        return provider_class(**kwargs)

    @classmethod
    def list_providers(cls) -> list[str]:
        """List registered provider names.

        Returns:
            List of provider names
        """
        return list(cls._providers.keys())


class OpenRouterEmbeddingProvider(EmbeddingProvider):
    """OpenRouter embedding provider with fallback support."""

    def __init__(
        self,
        api_key: str,
        primary_model: str = "openai/text-embedding-3-small",
        fallback_model: str = "nomic-ai/nomic-embed-text-v1",
    ) -> None:
        """Initialize OpenRouter embedding provider.

        Args:
            api_key: OpenRouter API key
            primary_model: Primary model name (OpenRouter format)
            fallback_model: Fallback model name (OpenRouter format)

        Raises:
            ValueError: If API key is empty
        """
        if not api_key.strip():
            raise ValueError("OpenRouter API key cannot be empty")

        self.api_key = api_key
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.base_url = "https://openrouter.ai/api/v1"
        self.timeout = 30.0

        # Model dimension mapping
        self.dimensions = {
            "openai/text-embedding-3-small": 1536,
            "openai/text-embedding-3-large": 3072,
            "nomic-ai/nomic-embed-text-v1": 768,
        }

        self.current_model = primary_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using OpenRouter API with fallback.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors

        Raises:
            EmbeddingError: If both primary and fallback models fail
        """
        if not texts:
            return []

        try:
            embeddings = await self._embed_with_model(texts, self.primary_model)
            self.current_model = self.primary_model
            return embeddings
        except EmbeddingError as e:
            logger.warning(
                f"Primary model {self.primary_model} failed: {_sanitize_log(str(e))}. "
                f"Attempting fallback model {self.fallback_model}"
            )
            try:
                embeddings = await self._embed_with_model(texts, self.fallback_model)
                self.current_model = self.fallback_model
                return embeddings
            except EmbeddingError as fallback_error:
                raise EmbeddingError(
                    f"Both primary and fallback embedding models failed. "
                    f"Primary: {self.primary_model}, Fallback: {self.fallback_model}"
                ) from fallback_error

    async def _embed_with_model(self, texts: list[str], model: str) -> list[list[float]]:
        """Generate embeddings with a specific model.

        Args:
            texts: List of text strings to embed
            model: Model name to use

        Returns:
            List of embedding vectors

        Raises:
            EmbeddingError: If API request fails
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "input": texts,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()

                data = response.json()
                embeddings = [item["embedding"] for item in data.get("data", [])]

                if len(embeddings) != len(texts):
                    raise EmbeddingError(
                        f"Expected {len(texts)} embeddings, got {len(embeddings)}"
                    )

                return embeddings

        except httpx.TimeoutException as e:
            raise EmbeddingError(f"Embedding API timeout (model={model})") from e
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if hasattr(e, 'response') else "unknown"
            error_msg = f"Embedding API error: {status_code}"
            try:
                if hasattr(e, 'response'):
                    error_detail = e.response.json().get("error", {})
                    if isinstance(error_detail, dict):
                        error_msg += f" - {error_detail.get('message', 'Unknown error')}"
            except Exception:
                pass
            raise EmbeddingError(error_msg) from e
        except Exception as e:
            raise EmbeddingError(f"Failed to generate embeddings with {model}: {e!s}") from e

    def get_dimension(self) -> int:
        """Get embedding dimension for the current model.

        Returns:
            Number of dimensions

        Raises:
            EmbeddingError: If model dimension is unknown
        """
        if self.current_model not in self.dimensions:
            raise EmbeddingError(f"Unknown model dimension for {self.current_model}")
        return self.dimensions[self.current_model]

    def get_model_name(self) -> str:
        """Get the current model name.

        Returns:
            Model name
        """
        return self.current_model


class EmbeddingService:
    """Service for generating and caching embeddings."""

    def __init__(
        self,
        provider: EmbeddingProvider | None = None,
        provider_name: str | None = None,
    ) -> None:
        """Initialize embedding service.

        Args:
            provider: Embedding provider instance (takes precedence over provider_name)
            provider_name: Name of provider to create from factory (default "openrouter")

        Raises:
            ValueError: If configuration is invalid
        """
        settings = get_settings()

        if provider is None:
            provider_name = provider_name or "openrouter"
            api_key = settings.OPENROUTER_API_KEY.get_secret_value()
            if not api_key:
                raise ValueError("OPENROUTER_API_KEY environment variable must be set")

            provider = EmbeddingProviderFactory.create(
                provider_name,
                api_key=api_key,
                primary_model=settings.EMBEDDING_PRIMARY_MODEL,
                fallback_model=settings.EMBEDDING_FALLBACK_MODEL,
            )

        self.provider = provider
        self.batch_size = settings.EMBEDDING_BATCH_SIZE
        self.cache_enabled = settings.EMBEDDING_CACHE_ENABLED
        self.cache_ttl = settings.EMBEDDING_CACHE_TTL_SECONDS

        # Lazy import of cache client
        self._cache_client = None

    @property
    def cache_client(self) -> Any:
        """Get Redis cache client (lazy import).

        Returns:
            Redis client or None if caching disabled
        """
        if not self.cache_enabled:
            return None

        if self._cache_client is None:
            try:
                import redis.asyncio as redis

                settings = get_settings()
                self._cache_client = redis.from_url(settings.REDIS_URL)
            except Exception as e:
                logger.warning(f"Failed to initialize Redis client: {e}")
                self._cache_client = None

        return self._cache_client

    def _make_cache_key(self, text: str, model: str) -> str:
        """Generate cache key for embedding.

        Args:
            text: Text to embed
            model: Model name

        Returns:
            Cache key
        """
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        return f"embedding:{model}:{text_hash}"

    async def embed_query(self, query: str) -> list[float]:
        """Generate a single embedding for a query string.

        Args:
            query: Query text to embed

        Returns:
            Embedding vector (list of floats)

        Raises:
            EmbeddingError: If embedding generation fails
        """
        embeddings = await self.provider.embed([query])
        if not embeddings:
            raise EmbeddingError("Embedding provider returned no vectors")
        return embeddings[0]

    async def embed_chunks(
        self,
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Generate embeddings for document chunks.

        Args:
            chunks: List of chunk dicts with 'chunk_id' and 'text' keys

        Returns:
            List of dicts with 'chunk_id', 'vector', 'model_name', 'embedding_dim'

        Raises:
            EmbeddingError: If embedding generation fails
        """
        if not chunks:
            return []

        model_name = self.provider.get_model_name()
        embedding_dim = self.provider.get_dimension()

        # Collect texts and track chunk IDs
        cached_embeddings: dict[str, dict[str, Any]] = {}
        texts_to_embed: list[str] = []
        text_to_chunk_ids: dict[str, list[str]] = {}
        cache_client = self.cache_client

        for chunk in chunks:
            chunk_id = chunk["chunk_id"]
            text = chunk["text"]
            cache_key = self._make_cache_key(text, model_name)

            # Try to get from cache
            if cache_client:
                try:
                    cached_vector = await cache_client.get(cache_key)
                    if cached_vector:
                        # Decompress if needed (stored as JSON list)
                        vector = json.loads(cached_vector)
                        cached_embeddings[chunk_id] = {
                            "chunk_id": chunk_id,
                            "vector": vector,
                            "model_name": model_name,
                            "embedding_dim": embedding_dim,
                        }
                        logger.debug(f"Cache hit for chunk {chunk_id}")
                        continue
                except Exception as e:
                    logger.warning(f"Cache lookup failed: {e}")

            # Not in cache, need to embed
            if text not in text_to_chunk_ids:
                text_to_chunk_ids[text] = []
                texts_to_embed.append(text)
            text_to_chunk_ids[text].append(chunk_id)

        # Generate embeddings for uncached texts
        generated_embeddings = {}
        if texts_to_embed:
            generated_embeddings = await self._embed_batch(
                texts_to_embed, model_name, text_to_chunk_ids
            )

        # Combine results in original order
        results = []
        for chunk in chunks:
            chunk_id = chunk["chunk_id"]

            if chunk_id in cached_embeddings:
                results.append(cached_embeddings[chunk_id])
            elif chunk_id in generated_embeddings:
                results.append(generated_embeddings[chunk_id])
            else:
                raise EmbeddingError(f"Missing embedding for chunk {chunk_id}")

        return results

    async def _embed_batch(
        self,
        texts: list[str],
        model_name: str,
        text_to_chunk_ids: dict[str, list[str]],
    ) -> dict[str, dict[str, Any]]:
        """Generate and cache embeddings for texts.

        Args:
            texts: List of texts to embed
            model_name: Model name for metadata
            text_to_chunk_ids: Mapping of text to chunk IDs

        Returns:
            Dict mapping chunk_id to embedding result
        """
        results = {}
        cache_client = self.cache_client
        embedding_dim = self.provider.get_dimension()

        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i : i + self.batch_size]

            try:
                vectors = await self.provider.embed(batch_texts)
            except EmbeddingError:
                raise

            # Cache and map results
            for text, vector in zip(batch_texts, vectors):
                cache_key = self._make_cache_key(text, model_name)

                # Cache the embedding
                if cache_client:
                    try:
                        await cache_client.setex(
                            cache_key,
                            self.cache_ttl,
                            json.dumps(vector),
                        )
                    except Exception as e:
                        logger.warning(f"Failed to cache embedding: {e}")

                # Map to chunk IDs
                for chunk_id in text_to_chunk_ids[text]:
                    results[chunk_id] = {
                        "chunk_id": chunk_id,
                        "vector": vector,
                        "model_name": model_name,
                        "embedding_dim": embedding_dim,
                    }

        return results


# Register providers with factory
EmbeddingProviderFactory.register("openrouter", OpenRouterEmbeddingProvider)
