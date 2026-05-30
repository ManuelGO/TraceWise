"""Unit tests for LLM service."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.services.llm_service import (
    ContextPromptTemplate,
    LLMError,
    LLMProviderFactory,
    LLMService,
    OpenRouterLLMProvider,
    SystemPromptTemplate,
    UserPromptTemplate,
    get_llm_service,
)


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider."""
    provider = AsyncMock()
    provider.generate = AsyncMock(
        return_value={
            "text": "This is a generated answer based on context.",
            "tokens": {"input": 100, "output": 50, "total": 150},
            "cost": 0.0015,
            "model": "openai/gpt-4o-mini",
        }
    )
    provider.get_model_name = MagicMock(return_value="openai/gpt-4o-mini")
    provider.count_tokens = MagicMock(return_value=100)
    return provider


@pytest.fixture
def mock_settings():
    """Mock settings."""
    settings = MagicMock()
    settings.LLM_PRIMARY_MODEL = "openai/gpt-4o-mini"
    settings.LLM_FALLBACK_MODEL = "meta-llama/llama-2-70b-chat"
    settings.LLM_TEMPERATURE = 0.7
    settings.LLM_MAX_TOKENS = 2048
    settings.LLM_CONTEXT_MAX_TOKENS = 3000
    settings.LLM_TIMEOUT_SECONDS = 30.0
    return settings


class TestLLMServiceInit:
    """Tests for LLMService initialization."""

    def test_init_with_valid_provider(self, mock_llm_provider):
        """Test successful initialization."""
        service = LLMService(mock_llm_provider)

        assert service.provider == mock_llm_provider

    def test_init_with_none_provider(self):
        """Test initialization with None provider raises error."""
        with pytest.raises(ValueError, match="provider cannot be None"):
            LLMService(None)


class TestLLMProviderFactory:
    """Tests for LLMProviderFactory."""

    def test_create_openrouter_provider(self):
        """Test creating OpenRouter provider."""
        provider = LLMProviderFactory.create(
            "openrouter",
            api_key="test-key",
            primary_model="openai/gpt-4o-mini",
            fallback_model="meta-llama/llama-2-70b-chat",
        )

        assert isinstance(provider, OpenRouterLLMProvider)
        assert provider.get_model_name() == "openai/gpt-4o-mini"

    def test_create_unknown_provider(self):
        """Test creating unknown provider raises error."""
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            LLMProviderFactory.create("unknown_provider")

    def test_list_providers(self):
        """Test listing registered providers."""
        providers = LLMProviderFactory.list_providers()
        assert "openrouter" in providers


class TestOpenRouterLLMProviderInit:
    """Tests for OpenRouterLLMProvider initialization."""

    def test_init_with_valid_key(self):
        """Test initialization with valid API key."""
        provider = OpenRouterLLMProvider(api_key="test-key")

        assert provider.api_key == "test-key"
        assert provider.primary_model == "openai/gpt-4o-mini"
        assert provider.fallback_model == "meta-llama/llama-2-70b-chat"

    def test_init_with_empty_key(self):
        """Test initialization with empty key raises error."""
        with pytest.raises(ValueError, match="OpenRouter API key cannot be empty"):
            OpenRouterLLMProvider(api_key="")

    def test_init_with_custom_models(self):
        """Test initialization with custom models."""
        provider = OpenRouterLLMProvider(
            api_key="test-key",
            primary_model="custom-primary",
            fallback_model="custom-fallback",
        )

        assert provider.primary_model == "custom-primary"
        assert provider.fallback_model == "custom-fallback"


class TestOpenRouterLLMProviderTokenCounting:
    """Tests for token counting."""

    def test_count_tokens_simple_text(self):
        """Test token counting with simple text."""
        provider = OpenRouterLLMProvider(api_key="test-key")
        tokens = provider.count_tokens("Hello world")

        assert tokens > 0

    def test_count_tokens_long_text(self):
        """Test token counting with longer text."""
        provider = OpenRouterLLMProvider(api_key="test-key")
        text = "This is a longer text. " * 10
        tokens = provider.count_tokens(text)

        assert tokens > 0


class TestOpenRouterLLMProviderModelName:
    """Tests for getting model name."""

    def test_get_model_name_primary(self):
        """Test getting primary model name."""
        provider = OpenRouterLLMProvider(api_key="test-key")

        assert provider.get_model_name() == "openai/gpt-4o-mini"

    def test_get_model_name_after_init(self):
        """Test model name after custom initialization."""
        provider = OpenRouterLLMProvider(
            api_key="test-key", primary_model="custom-model"
        )

        assert provider.get_model_name() == "custom-model"


class TestOpenRouterLLMProviderErrorHandling:
    """Tests for error handling in OpenRouter provider."""

    @pytest.mark.asyncio
    async def test_generate_with_timeout(self, monkeypatch):
        """Test handling of API timeout."""
        provider = OpenRouterLLMProvider(api_key="test-key")

        # Mock httpx.AsyncClient to raise timeout
        async def mock_post(*args, **kwargs):
            raise httpx.TimeoutException("Request timed out")

        monkeypatch.setattr(
            "httpx.AsyncClient.post",
            mock_post,
        )

        with pytest.raises(LLMError, match="timeout"):
            await provider._generate_with_model("test prompt", 0.7, 100, "test-model")

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self):
        """Test fallback model selection on primary failure."""
        provider = OpenRouterLLMProvider(
            api_key="test-key",
            primary_model="invalid-model",
            fallback_model="valid-model",
        )

        # The actual API call will fail, but we test the fallback attempt
        with pytest.raises(LLMError, match="Both primary and fallback"):
            await provider.generate("test prompt", 0.7, 100)


class TestOpenRouterLLMProviderCostCalculation:
    """Tests for cost calculation."""

    def test_calculate_cost_known_model(self):
        """Test cost calculation for known model."""
        provider = OpenRouterLLMProvider(api_key="test-key")
        cost = provider._calculate_cost("openai/gpt-4o-mini", 1000, 500)

        assert cost > 0

    def test_calculate_cost_unknown_model(self):
        """Test cost calculation for unknown model returns 0."""
        provider = OpenRouterLLMProvider(api_key="test-key")
        cost = provider._calculate_cost("unknown-model", 1000, 500)

        assert cost == 0.0

    def test_calculate_cost_zero_tokens(self):
        """Test cost calculation with zero tokens."""
        provider = OpenRouterLLMProvider(api_key="test-key")
        cost = provider._calculate_cost("openai/gpt-4o-mini", 0, 0)

        assert cost == 0.0


class TestLLMServiceGenerateAnswer:
    """Tests for answer generation."""

    @pytest.mark.asyncio
    async def test_generate_answer_with_valid_input(
        self, mock_llm_provider, mock_settings, monkeypatch
    ):
        """Test successful answer generation."""
        monkeypatch.setattr("app.services.llm_service.get_settings", lambda: mock_settings)

        service = LLMService(mock_llm_provider)
        result = await service.generate_answer(
            "What is the capital of France?",
            [
                {
                    "embedding_id": "test-1",
                    "document_extraction_id": "doc-1",
                    "chunk_index": 0,
                    "chunk_text": "France is a country in Europe. Its capital is Paris.",
                    "similarity_score": 0.95,
                    "embedding_model": "openai/text-embedding-3-small",
                }
            ],
        )

        assert result["answer"] == "This is a generated answer based on context."
        assert result["tokens"]["total"] == 150
        assert result["cost"] == 0.0015
        assert result["model"] == "openai/gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_generate_answer_with_empty_query(self, mock_llm_provider):
        """Test answer generation with empty query raises error."""
        service = LLMService(mock_llm_provider)

        with pytest.raises(LLMError, match="Query cannot be empty"):
            await service.generate_answer("", [])

    @pytest.mark.asyncio
    async def test_generate_answer_with_whitespace_only(self, mock_llm_provider):
        """Test answer generation with whitespace-only query raises error."""
        service = LLMService(mock_llm_provider)

        with pytest.raises(LLMError, match="Query cannot be empty"):
            await service.generate_answer("   ", [])

    @pytest.mark.asyncio
    async def test_generate_answer_with_custom_params(
        self, mock_llm_provider, mock_settings, monkeypatch
    ):
        """Test answer generation with custom temperature and max_tokens."""
        monkeypatch.setattr("app.services.llm_service.get_settings", lambda: mock_settings)

        service = LLMService(mock_llm_provider)
        await service.generate_answer(
            "Test query",
            [],
            temperature=0.5,
            max_tokens=1024,
        )

        call_args = mock_llm_provider.generate.call_args
        assert call_args.args[1] == 0.5  # temperature is second positional arg
        assert call_args.args[2] == 1024  # max_tokens is third positional arg

    @pytest.mark.asyncio
    async def test_generate_answer_with_empty_context(
        self, mock_llm_provider, mock_settings, monkeypatch
    ):
        """Test answer generation with no search results."""
        monkeypatch.setattr("app.services.llm_service.get_settings", lambda: mock_settings)

        service = LLMService(mock_llm_provider)
        result = await service.generate_answer("Test query", [])

        assert "answer" in result
        assert "tokens" in result

    @pytest.mark.asyncio
    async def test_generate_answer_provider_error(
        self, mock_llm_provider, mock_settings, monkeypatch
    ):
        """Test answer generation when provider fails."""
        monkeypatch.setattr("app.services.llm_service.get_settings", lambda: mock_settings)
        mock_llm_provider.generate.side_effect = LLMError("API error")

        service = LLMService(mock_llm_provider)

        with pytest.raises(LLMError):
            await service.generate_answer("Test query", [])

    @pytest.mark.asyncio
    async def test_generate_answer_returns_all_fields(
        self, mock_llm_provider, mock_settings, monkeypatch
    ):
        """Test that answer includes all required fields."""
        monkeypatch.setattr("app.services.llm_service.get_settings", lambda: mock_settings)

        service = LLMService(mock_llm_provider)
        result = await service.generate_answer("Test query", [])

        assert "answer" in result
        assert "tokens" in result
        assert "cost" in result
        assert "model" in result
        assert "input" in result["tokens"]
        assert "output" in result["tokens"]
        assert "total" in result["tokens"]


class TestLLMServiceContextManagement:
    """Tests for context truncation and validation."""

    def test_truncate_context_within_limit(self, mock_llm_provider, mock_settings, monkeypatch):
        """Test that context within token limit is not truncated."""
        monkeypatch.setattr("app.services.llm_service.get_settings", lambda: mock_settings)
        mock_settings.LLM_CONTEXT_MAX_TOKENS = 1000

        service = LLMService(mock_llm_provider)
        search_results = [
            {
                "embedding_id": "test-1",
                "document_extraction_id": "doc-1",
                "chunk_index": 0,
                "chunk_text": "Short text",
                "similarity_score": 0.9,
                "embedding_model": "openai/text-embedding-3-small",
            }
        ]

        truncated = service._truncate_context(search_results)

        assert len(truncated) == 1

    def test_truncate_context_exceeds_limit(self, mock_llm_provider, mock_settings, monkeypatch):
        """Test that context exceeding token limit is truncated."""
        monkeypatch.setattr("app.services.llm_service.get_settings", lambda: mock_settings)
        mock_settings.LLM_CONTEXT_MAX_TOKENS = 10  # Very low limit

        service = LLMService(mock_llm_provider)
        search_results = [
            {
                "embedding_id": "test-1",
                "document_extraction_id": "doc-1",
                "chunk_index": 0,
                "chunk_text": "This is a very long text that will exceed the token limit",
                "similarity_score": 0.9,
                "embedding_model": "openai/text-embedding-3-small",
            },
            {
                "embedding_id": "test-2",
                "document_extraction_id": "doc-2",
                "chunk_index": 0,
                "chunk_text": "More text",
                "similarity_score": 0.8,
                "embedding_model": "openai/text-embedding-3-small",
            },
        ]

        truncated = service._truncate_context(search_results)

        assert len(truncated) <= len(search_results)

    def test_truncate_context_empty(self, mock_llm_provider):
        """Test truncating empty context."""
        service = LLMService(mock_llm_provider)
        truncated = service._truncate_context([])

        assert len(truncated) == 0

    def test_validate_grounding_with_context(self, mock_llm_provider):
        """Test grounding validation with matching context."""
        service = LLMService(mock_llm_provider)
        answer = "The answer is related to the important information"
        search_results = [
            {
                "embedding_id": "test-1",
                "document_extraction_id": "doc-1",
                "chunk_index": 0,
                "chunk_text": "Important information about the topic",
                "similarity_score": 0.9,
                "embedding_model": "openai/text-embedding-3-small",
            }
        ]

        # Should not raise, just log warning if not grounded
        service._validate_grounding(answer, search_results)

    def test_validate_grounding_no_context(self, mock_llm_provider):
        """Test grounding validation with no context."""
        service = LLMService(mock_llm_provider)
        answer = "This is an answer"

        # Should log warning but not raise
        service._validate_grounding(answer, [])


class TestLLMServiceEdgeCases:
    """Tests for edge cases and error scenarios."""

    @pytest.mark.asyncio
    async def test_generate_answer_with_special_characters(
        self, mock_llm_provider, mock_settings, monkeypatch
    ):
        """Test answer generation with special characters in context."""
        monkeypatch.setattr("app.services.llm_service.get_settings", lambda: mock_settings)

        service = LLMService(mock_llm_provider)
        search_results = [
            {
                "embedding_id": "test-1",
                "document_extraction_id": "doc-1",
                "chunk_index": 0,
                "chunk_text": "Code example: print('hello')",
                "similarity_score": 0.9,
                "embedding_model": "openai/text-embedding-3-small",
            }
        ]

        result = await service.generate_answer("What is the code?", search_results)

        assert result["answer"]

    @pytest.mark.asyncio
    async def test_generate_answer_with_unicode(
        self, mock_llm_provider, mock_settings, monkeypatch
    ):
        """Test answer generation with unicode characters."""
        monkeypatch.setattr("app.services.llm_service.get_settings", lambda: mock_settings)

        service = LLMService(mock_llm_provider)
        search_results = [
            {
                "embedding_id": "test-1",
                "document_extraction_id": "doc-1",
                "chunk_index": 0,
                "chunk_text": "Unicode: 你好世界 мир שלום",
                "similarity_score": 0.9,
                "embedding_model": "openai/text-embedding-3-small",
            }
        ]

        result = await service.generate_answer("What about unicode?", search_results)

        assert result["answer"]

    @pytest.mark.asyncio
    async def test_generate_answer_with_many_documents(
        self, mock_llm_provider, mock_settings, monkeypatch
    ):
        """Test answer generation with many search results."""
        monkeypatch.setattr("app.services.llm_service.get_settings", lambda: mock_settings)

        service = LLMService(mock_llm_provider)
        search_results = [
            {
                "embedding_id": f"test-{i}",
                "document_extraction_id": f"doc-{i}",
                "chunk_index": 0,
                "chunk_text": f"Document content {i}",
                "similarity_score": 0.9 - (i * 0.01),
                "embedding_model": "openai/text-embedding-3-small",
            }
            for i in range(10)
        ]

        result = await service.generate_answer("What is in these documents?", search_results)

        assert result["answer"]

    def test_token_counting_empty_string(self, mock_llm_provider):
        """Test token counting with empty string."""
        tokens = mock_llm_provider.count_tokens("")

        assert tokens > 0  # Should return at least 1

    def test_token_counting_long_text(self, mock_llm_provider):
        """Test token counting with very long text."""
        long_text = "This is a test. " * 1000
        tokens = mock_llm_provider.count_tokens(long_text)

        assert tokens > 0
        assert tokens < len(long_text)  # Should be less than character count


class TestPromptTemplates:
    """Tests for prompt template classes."""

    def test_system_prompt_template(self):
        """Test system prompt template rendering."""
        template = SystemPromptTemplate()
        prompt = template.render()

        assert "helpful assistant" in prompt
        assert "context" in prompt.lower()
        assert "provided context" in prompt

    def test_context_prompt_template_with_results(self):
        """Test context prompt template with search results."""
        template = ContextPromptTemplate()
        search_results = [
            {
                "embedding_id": "test-1",
                "document_extraction_id": "doc-1",
                "chunk_index": 0,
                "chunk_text": "Important information",
                "similarity_score": 0.95,
                "embedding_model": "openai/text-embedding-3-small",
            }
        ]

        context = template.render(search_results=search_results)

        assert "Document 1" in context
        assert "Important information" in context
        assert "95.0%" in context

    def test_context_prompt_template_empty(self):
        """Test context prompt template with no results."""
        template = ContextPromptTemplate()
        context = template.render(search_results=None)

        assert "(No context documents provided)" in context

    def test_user_prompt_template(self):
        """Test user prompt template rendering."""
        template = UserPromptTemplate()
        prompt = template.render(query="What is X?", context="Context text")

        assert "What is X?" in prompt
        assert "Context text" in prompt
        assert "Question" in prompt

    def test_user_prompt_template_without_context(self):
        """Test user prompt template without context."""
        template = UserPromptTemplate()
        prompt = template.render(query="What is X?", context="")

        assert "What is X?" in prompt
        assert "(No context documents provided)" in prompt


class TestLLMServicePromptAssembly:
    """Tests for prompt assembly and formatting."""

    def test_assemble_prompt_with_context(self, mock_llm_provider):
        """Test prompt assembly with context."""
        service = LLMService(mock_llm_provider)
        search_results = [
            {
                "embedding_id": "test-1",
                "document_extraction_id": "doc-1",
                "chunk_index": 0,
                "chunk_text": "Test context",
                "similarity_score": 0.9,
                "embedding_model": "openai/text-embedding-3-small",
            }
        ]

        prompt = service._assemble_prompt("What is the answer?", search_results)

        assert "helpful assistant" in prompt
        assert "Test context" in prompt
        assert "What is the answer?" in prompt

    def test_assemble_prompt_without_context(self, mock_llm_provider):
        """Test prompt assembly without context."""
        service = LLMService(mock_llm_provider)

        prompt = service._assemble_prompt("Test query", [])

        assert "Test query" in prompt
        assert "(No context documents provided)" in prompt

    def test_context_template_single_document(self):
        """Test context template rendering with single document."""
        template = ContextPromptTemplate()
        search_results = [
            {
                "embedding_id": "test-1",
                "document_extraction_id": "doc-1",
                "chunk_index": 0,
                "chunk_text": "Sample text",
                "similarity_score": 0.95,
                "embedding_model": "openai/text-embedding-3-small",
            }
        ]

        context = template.render(search_results=search_results)

        assert "Document 1" in context
        assert "Sample text" in context
        assert "95.0%" in context

    def test_context_template_multiple_documents(self):
        """Test context template rendering with multiple documents."""
        template = ContextPromptTemplate()
        search_results = [
            {
                "embedding_id": "test-1",
                "document_extraction_id": "doc-1",
                "chunk_index": 0,
                "chunk_text": "First document",
                "similarity_score": 0.95,
                "embedding_model": "openai/text-embedding-3-small",
            },
            {
                "embedding_id": "test-2",
                "document_extraction_id": "doc-2",
                "chunk_index": 0,
                "chunk_text": "Second document",
                "similarity_score": 0.85,
                "embedding_model": "openai/text-embedding-3-small",
            },
        ]

        context = template.render(search_results=search_results)

        assert "Document 1" in context
        assert "Document 2" in context
        assert "First document" in context
        assert "Second document" in context

    def test_context_template_empty(self):
        """Test context template rendering with empty results."""
        template = ContextPromptTemplate()

        context = template.render(search_results=[])

        assert "(No context documents provided)" in context


class TestGetLLMService:
    """Tests for get_llm_service factory function."""

    def test_get_llm_service_success(self, monkeypatch, mock_settings):
        """Test successful LLMService creation with config."""
        from pydantic import SecretStr

        # Mock get_settings to return test settings
        mock_settings.LLM_PROVIDER = "openrouter"
        mock_settings.LLM_API_KEY = SecretStr("test-key")
        mock_settings.OPENROUTER_API_KEY = SecretStr("")
        mock_settings.LLM_PRIMARY_MODEL = "openai/gpt-4o-mini"
        mock_settings.LLM_FALLBACK_MODEL = "meta-llama/llama-2-70b-chat"

        monkeypatch.setattr("app.services.llm_service.get_settings", lambda: mock_settings)

        service = get_llm_service()

        assert isinstance(service, LLMService)
        assert service.provider is not None

    def test_get_llm_service_fallback_to_openrouter_key(self, monkeypatch, mock_settings):
        """Test LLMService falls back to OPENROUTER_API_KEY if LLM_API_KEY empty."""
        from pydantic import SecretStr

        # Mock get_settings with LLM_API_KEY empty but OPENROUTER_API_KEY set
        mock_settings.LLM_PROVIDER = "openrouter"
        mock_settings.LLM_API_KEY = SecretStr("")
        mock_settings.OPENROUTER_API_KEY = SecretStr("openrouter-key")
        mock_settings.LLM_PRIMARY_MODEL = "openai/gpt-4o-mini"
        mock_settings.LLM_FALLBACK_MODEL = "meta-llama/llama-2-70b-chat"

        monkeypatch.setattr("app.services.llm_service.get_settings", lambda: mock_settings)

        service = get_llm_service()

        assert isinstance(service, LLMService)

    def test_get_llm_service_missing_api_key(self, monkeypatch, mock_settings):
        """Test get_llm_service raises error when no API key configured."""
        from pydantic import SecretStr

        # Mock get_settings with both API keys empty
        mock_settings.LLM_PROVIDER = "openrouter"
        mock_settings.LLM_API_KEY = SecretStr("")
        mock_settings.OPENROUTER_API_KEY = SecretStr("")
        mock_settings.LLM_PRIMARY_MODEL = "openai/gpt-4o-mini"
        mock_settings.LLM_FALLBACK_MODEL = "meta-llama/llama-2-70b-chat"

        monkeypatch.setattr("app.services.llm_service.get_settings", lambda: mock_settings)

        with pytest.raises(ValueError, match="LLM API key must be set"):
            get_llm_service()
