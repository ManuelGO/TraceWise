"""LLM service for generating grounded answers from retrieved context.

This module provides LLM integration for RAG answer generation:
1. Prompt templating: System, context, and user prompt assembly
2. LLM API calls: Provider abstraction with fallback support
3. Token tracking: Count and cost calculation
4. Response formatting: Structured answer output

The service supports multiple LLM providers (currently OpenRouter) with
configurable models, temperature, and context limits.
"""

import logging
import string
from abc import ABC, abstractmethod
from typing import Any, ClassVar, TypedDict

import httpx
from pydantic import SecretStr

from app.config import get_settings
from app.models.vector_embedding import SearchResult
from app.monitoring.retry_metrics import _sanitize_log

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when LLM service operations fail."""

    pass


class GeneratedAnswer(TypedDict):
    """Structured response from LLM service.

    Attributes:
        answer: Generated answer text
        tokens: Dict with 'input', 'output', and 'total' token counts
        cost: Estimated cost in USD
        model: Model name used for generation
    """

    answer: str
    tokens: dict[str, int]
    cost: float
    model: str


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate(
        self, prompt: str, temperature: float, max_tokens: int
    ) -> dict[str, Any]:
        """Generate response from LLM.

        Args:
            prompt: Full assembled prompt (system + context + user)
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens in response

        Returns:
            Dict with 'text' (response), 'tokens' (dict), 'cost' (float), 'model' (str)

        Raises:
            LLMError: If API request fails
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Get the current model name.

        Returns:
            Model name
        """
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Args:
            text: Text to count tokens for

        Returns:
            Estimated token count
        """
        pass


class LLMProviderFactory:
    """Factory for creating LLM providers."""

    _providers: ClassVar[dict[str, type[LLMProvider]]] = {}

    @classmethod
    def register(cls, name: str, provider_class: type[LLMProvider]) -> None:
        """Register a provider class.

        Args:
            name: Provider name
            provider_class: Provider class
        """
        cls._providers[name] = provider_class

    @classmethod
    def create(cls, provider_name: str, **kwargs: Any) -> LLMProvider:
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
                f"Unknown LLM provider: {provider_name}. "
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


class OpenRouterLLMProvider(LLMProvider):
    """OpenRouter LLM provider with fallback support."""

    def __init__(
        self,
        api_key: str | SecretStr,
        primary_model: str = "openai/gpt-4o-mini",
        fallback_model: str = "meta-llama/llama-2-70b-chat",
    ) -> None:
        """Initialize OpenRouter LLM provider.

        Args:
            api_key: OpenRouter API key
            primary_model: Primary model name (OpenRouter format)
            fallback_model: Fallback model name (OpenRouter format)

        Raises:
            ValueError: If API key is empty
        """
        api_key_str = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        if not api_key_str.strip():
            raise ValueError("OpenRouter API key cannot be empty")

        self.api_key = api_key_str
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.base_url = "https://openrouter.ai/api/v1"
        settings = get_settings()
        self.timeout = settings.LLM_TIMEOUT_SECONDS
        self.current_model = primary_model

        # Model pricing (input/output tokens per million)
        self.pricing = {
            "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
            "meta-llama/llama-2-70b-chat": {"input": 0.70, "output": 0.90},
        }

    async def generate(
        self, prompt: str, temperature: float, max_tokens: int
    ) -> dict[str, Any]:
        """Generate response using OpenRouter API with fallback.

        Args:
            prompt: Full assembled prompt
            temperature: Sampling temperature
            max_tokens: Maximum response tokens

        Returns:
            Dict with response text, token usage, cost, and model

        Raises:
            LLMError: If both primary and fallback fail
        """
        try:
            return await self._generate_with_model(
                prompt, temperature, max_tokens, self.primary_model
            )
        except LLMError as e:
            logger.warning(
                f"Primary model {self.primary_model} failed: {_sanitize_log(str(e))}. "
                f"Attempting fallback model {self.fallback_model}"
            )
            try:
                return await self._generate_with_model(
                    prompt, temperature, max_tokens, self.fallback_model
                )
            except LLMError as fallback_error:
                raise LLMError(
                    f"Both primary and fallback LLM models failed. "
                    f"Primary: {self.primary_model}, Fallback: {self.fallback_model}"
                ) from fallback_error

    async def _generate_with_model(
        self, prompt: str, temperature: float, max_tokens: int, model: str
    ) -> dict[str, Any]:
        """Generate response with a specific model.

        Args:
            prompt: Full assembled prompt
            temperature: Sampling temperature
            max_tokens: Maximum response tokens
            model: Model name to use

        Returns:
            Dict with response text, tokens, cost, and model

        Raises:
            LLMError: If API request fails
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()

                data = response.json()
                if not data.get("choices"):
                    raise LLMError(f"No completion choices returned from {model}")
                answer_text = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)

                # Calculate cost
                cost = self._calculate_cost(model, input_tokens, output_tokens)
                self.current_model = model

                return {
                    "text": answer_text,
                    "tokens": {
                        "input": input_tokens,
                        "output": output_tokens,
                        "total": input_tokens + output_tokens,
                    },
                    "cost": cost,
                    "model": model,
                }

        except httpx.TimeoutException as e:
            raise LLMError(f"LLM API timeout after {self.timeout}s (model={model})") from e
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if hasattr(e, "response") else -1
            error_msg = f"LLM API error: {status_code}"

            # Handle rate limit errors specially
            if status_code == 429:
                error_msg = "Rate limit exceeded - too many requests to LLM API"
            elif status_code >= 500:
                error_msg = f"LLM API server error ({status_code})"

            try:
                if hasattr(e, "response"):
                    error_detail = e.response.json().get("error", {})
                    if isinstance(error_detail, dict):
                        error_msg += f" - {error_detail.get('message', 'Unknown error')}"
            except Exception:
                pass
            raise LLMError(error_msg) from e
        except Exception as e:
            raise LLMError(f"Failed to generate with {model}: {e!s}") from e

    def _calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for tokens using model pricing.

        Args:
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Estimated cost in USD
        """
        if model not in self.pricing:
            logger.warning(f"Unknown model {model} for pricing, estimating")
            return 0.0

        rates = self.pricing[model]
        input_cost = (input_tokens / 1_000_000) * rates["input"]
        output_cost = (output_tokens / 1_000_000) * rates["output"]
        return input_cost + output_cost

    def get_model_name(self) -> str:
        """Get the current model name.

        Returns:
            Model name
        """
        return self.current_model

    def count_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Uses a heuristic estimation based on character count.
        Actual token counts are obtained from API responses in _generate_with_model().

        Args:
            text: Text to count tokens for

        Returns:
            Estimated token count (roughly 1 token per 4 characters)
        """
        return max(1, len(text) // 4)


class PromptTemplate(ABC):
    """Base class for prompt templates."""

    @abstractmethod
    def render(self, **kwargs: Any) -> str:
        """Render the template with given parameters.

        Args:
            **kwargs: Template parameters

        Returns:
            Rendered template string
        """


class SystemPromptTemplate(PromptTemplate):
    """System prompt for grounded answer generation."""

    def render(self, **kwargs: Any) -> str:
        """Render system prompt."""
        return (
            "You are a helpful assistant that answers questions based on provided context. "
            "Only use information from the context documents to answer. "
            "If the context does not contain enough information to answer, "
            "clearly state that you cannot answer based on the provided context. "
            "Always cite the source document when providing information."
        )


class ContextPromptTemplate(PromptTemplate):
    """Template for formatting context documents."""

    def render(self, search_results: list[SearchResult] | None = None, **kwargs: Any) -> str:
        """Render context from search results.

        Args:
            search_results: List of SearchResult documents
            **kwargs: Additional parameters (unused)

        Returns:
            Formatted context section
        """
        if not search_results:
            return "## Context\n\n(No context documents provided)"

        parts = ["## Context Documents\n"]
        for i, result in enumerate(search_results, 1):
            chunk_text = result.get("chunk_text", "")
            similarity = result.get("similarity_score", 0.0)
            doc_id = result.get("document_extraction_id", "unknown")

            parts.append(f"### Document {i} (Relevance: {similarity:.1%})")
            parts.append(f"Source: {doc_id}\n")
            parts.append(f"{chunk_text}\n")
            parts.append("---\n")

        return "\n".join(parts)


class UserPromptTemplate(PromptTemplate):
    """Template for user query with context."""

    def render(self, query: str = "", context: str = "", **kwargs: Any) -> str:
        """Render user prompt with query and context.

        Args:
            query: User question
            context: Formatted context documents
            **kwargs: Additional parameters (unused)

        Returns:
            User prompt section
        """
        if not context:
            context = "## Context\n\n(No context documents provided)"

        return (
            f"{context}\n\n"
            f"## Question\n\n{query}\n\n"
            f"Based on the context documents provided above, please answer the question. "
            f"If the answer is not in the context, explicitly state that."
        )


class LLMService:
    """Orchestrator for LLM-based answer generation.

    Composes LLMProvider to generate answers grounded in retrieved context.
    Handles prompt assembly, token tracking, cost estimation, and error handling.
    """

    def __init__(self, provider: LLMProvider):
        """Initialize LLM service.

        Args:
            provider: LLM provider instance

        Raises:
            ValueError: If provider is not properly initialized
        """
        if not provider:
            raise ValueError("provider cannot be None")

        self.provider = provider
        self.settings = get_settings()
        self.system_template = SystemPromptTemplate()
        self.context_template = ContextPromptTemplate()
        self.user_template = UserPromptTemplate()

    async def generate_answer(
        self,
        query: str,
        search_results: list[SearchResult],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> GeneratedAnswer:
        """Generate answer grounded in retrieved context.

        Args:
            query: User question
            search_results: List of SearchResult from retrieval
            temperature: Sampling temperature (uses default if None)
            max_tokens: Maximum response tokens (uses default if None)

        Returns:
            GeneratedAnswer with answer text, tokens, cost, and model

        Raises:
            LLMError: If answer generation fails
        """
        if not query or not query.strip():
            raise LLMError("Query cannot be empty")

        if temperature is None:
            temperature = self.settings.LLM_TEMPERATURE
        if max_tokens is None:
            max_tokens = self.settings.LLM_MAX_TOKENS

        try:
            # Validate context size and truncate if necessary
            truncated_results = self._truncate_context(search_results)

            # Assemble prompt
            prompt = self._assemble_prompt(query, truncated_results)

            # Generate answer
            result = await self.provider.generate(prompt, temperature, max_tokens)

            # Validate grounding (heuristic check)
            self._validate_grounding(result["text"], truncated_results)

            # Log metrics
            logger.info(
                f"Answer generated: {result['tokens']['total']} tokens, "
                f"${result['cost']:.4f} cost",
                extra={
                    "query_length": len(query),
                    "context_docs": len(truncated_results),
                    "input_tokens": result["tokens"]["input"],
                    "output_tokens": result["tokens"]["output"],
                    "total_tokens": result["tokens"]["total"],
                    "cost": result["cost"],
                    "model": result["model"],
                },
            )

            return {
                "answer": result["text"],
                "tokens": result["tokens"],
                "cost": result["cost"],
                "model": result["model"],
            }

        except LLMError:
            raise
        except Exception as e:
            logger.error("Failed to generate answer", exc_info=True)
            raise LLMError(f"Answer generation failed: {e!s}") from e

    def _truncate_context(
        self, search_results: list[SearchResult]
    ) -> list[SearchResult]:
        """Truncate context to fit within token limits.

        Args:
            search_results: List of search results to truncate

        Returns:
            Truncated list of search results
        """
        if not search_results:
            return []

        max_context_tokens = self.settings.LLM_CONTEXT_MAX_TOKENS
        total_tokens = 0
        truncated = []

        for result in search_results:
            chunk_text = result.get("chunk_text", "")
            tokens = self.provider.count_tokens(chunk_text)

            if total_tokens + tokens <= max_context_tokens:
                truncated.append(result)
                total_tokens += tokens
            else:
                # Context would exceed limit, truncate here
                break

        if len(truncated) < len(search_results):
            logger.warning(
                f"Context truncated: {len(truncated)}/{len(search_results)} documents "
                f"({total_tokens}/{max_context_tokens} tokens)"
            )

        return truncated

    def _validate_grounding(self, answer: str, search_results: list[SearchResult]) -> None:
        """Validate that answer appears grounded in context (heuristic).

        Args:
            answer: Generated answer text
            search_results: Context documents used
        """
        if not search_results:
            # No context provided, answer may be hallucinated
            logger.warning("Answer generated with no context - may be hallucinated")
            return

        # Heuristic: check if answer mentions key terms from context
        answer_lower = answer.lower()
        context_terms = set()

        for result in search_results:
            chunk_text = result.get("chunk_text", "").lower()
            # Extract meaningful terms (words > 3 chars after stripping punctuation)
            words = chunk_text.split()
            terms = [w.strip(string.punctuation) for w in words if len(w.strip(string.punctuation)) > 3]
            context_terms.update(terms)

        # Check if answer contains any context terms
        answer_words = answer_lower.split()
        answer_terms = set(w.strip(string.punctuation) for w in answer_words if len(w.strip(string.punctuation)) > 3)
        overlap = answer_terms & context_terms

        if not overlap and len(context_terms) > 0:
            logger.warning(
                "Answer may not be grounded in context - "
                "consider reviewing for hallucination"
            )

    def _assemble_prompt(self, query: str, search_results: list[SearchResult]) -> str:
        """Assemble complete prompt from components.

        Args:
            query: User question
            search_results: Retrieved context documents

        Returns:
            Complete prompt ready for LLM
        """
        system_prompt = self.system_template.render()
        context_text = self.context_template.render(search_results=search_results)
        user_prompt = self.user_template.render(query=query, context=context_text)

        return f"{system_prompt}\n\n{user_prompt}"


# Register providers with factory
LLMProviderFactory.register("openrouter", OpenRouterLLMProvider)


def get_llm_service() -> LLMService:
    """Factory function to create LLMService with configured provider.

    Reads LLM configuration from settings and initializes the provider
    with the appropriate API key and model settings.

    Returns:
        LLMService instance configured from environment

    Raises:
        ValueError: If required LLM configuration is missing
    """
    settings = get_settings()

    # Use LLM_API_KEY if set, otherwise fall back to OPENROUTER_API_KEY
    api_key = settings.LLM_API_KEY
    if not api_key or not api_key.get_secret_value().strip():
        api_key = settings.OPENROUTER_API_KEY

    if not api_key or not api_key.get_secret_value().strip():
        raise ValueError(
            "LLM API key must be set via LLM_API_KEY or OPENROUTER_API_KEY environment variable"
        )

    provider = LLMProviderFactory.create(
        settings.LLM_PROVIDER,
        api_key=api_key,
        primary_model=settings.LLM_PRIMARY_MODEL,
        fallback_model=settings.LLM_FALLBACK_MODEL,
    )

    return LLMService(provider)
