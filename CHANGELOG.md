# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- Last updated: 2026-05-30 | Covers: Phase 2 & 3 development through Task 36 (Answer Generation) -->

## [Unreleased]

### Added
- LLM service for generating grounded answers from retrieved context
- OpenRouter LLM provider with fallback model support
- Prompt template hierarchy (system, context, user templates) with ABC base class
- Token counting and cost calculation for LLM responses
- Context grounding validation with hallucination detection
- Intelligent context truncation based on token limits
- Configuration factory function (get_llm_service) for proper LLM initialization
- 50 comprehensive unit tests for LLM service with 89% coverage
- Docker setup for development and production environments
- PostgreSQL setup with SQLAlchemy ORM and async support
- Redis setup with async client and cache utilities
- Centralized configuration management with Pydantic v2 and structured logging
- pytest configuration with centralized fixtures
- Vitest testing infrastructure with Angular testing setup
- ComplianceCase ORM model with CRUD endpoints
- Document model with ORM persistence and validation
- Risk assessment model with schema validation
- Document and Audit models for compliance tracking
- SQLAlchemy persistence layer with async context managers
- Alembic migrations with full upgrade/downgrade support
- Case creation API with full CRUD endpoints
- Document upload API with file validation, MIME-type detection, and path traversal prevention
- Job status model with state transitions and async job tracking
- Async job queue with Celery, Redis broker/backend, and monitoring
- File validation service with magic byte detection
- Text extraction from PDF, DOCX, and XLSX files
- Document processing status tracking with GraphQL integration
- Idempotent processing with SHA256-based deduplication
- Retry strategy for document processing
- Processing timeline API with task progress tracking
- Knowledge base structure with file-based document storage, JSON index, and semantic search
- 34 comprehensive unit tests for knowledge base service
- 7 security audit fixes (path traversal, metadata parsing, dict access safety, frontmatter parsing, document ID consistency, exception handling, category validation)
- Regulatory content ingestion service (KBLoader) with comprehensive security hardening
- 23 unit tests for KB document loading with path validation, metadata validation, and DOS prevention
- 12 security audit fixes for regulatory content ingestion (path traversal, metadata type validation, file size limits, CRLF handling, CLI path arguments, error message sanitization, temp file cleanup, UTC timestamps, PyYAML dependency, dead code removal)
- Document chunking strategy with semantic boundary detection and configurable chunk sizes
- 18 unit tests for document chunking with edge cases and performance validation
- Embedding generation service with OpenRouter provider and fallback model support
- Redis-based embedding cache with TTL and batch processing
- 15 unit tests for embedding generation with provider fallback and cache validation
- Vector store integration with pgvector for PostgreSQL and similarity search
- Async vector search with configurable similarity thresholds
- 16 unit tests for vector store operations with concurrency testing
- Retrieval pipeline orchestrator (RetrievalService) composing EmbeddingService + VectorStore
- Async single and batch query operations with configurable parameters
- Metadata filtering by document extraction ID
- Query result ranking by similarity score (descending)
- 22 unit tests for retrieval pipeline with full parameter coverage

### Changed
- Migrated backend to async drivers and implemented scalable FastAPI architecture
- Reorganized frontend app structure with security best practices and Angular 19
- Consolidated dependency management into pyproject.toml
- Enhanced document processing with validation pipeline
- Embedding service layer with service-level query embedding (layer separation)
- Batch operations API to include all query parameters (similarity_threshold, extraction_ids)
- Error handling for invalid retrieval parameters (k must be positive, threshold bounds validation)
- PromptTemplate class now uses ABC with @abstractmethod for consistency
- Removed dead _format_context method (duplicated context_template rendering)

### Fixed
- Path traversal vulnerability with pathlib-based containment validation
- Metadata parsing crashes with None guards
- Frontmatter delimiter ambiguity with regex MULTILINE flag
- Unguarded dictionary access with .get() patterns
- Bare exception handlers with specific exception types
- Category validation brittleness by extracting from index
- Layer violations in retrieval service (embed_query interface)
- Inconsistent error handling for invalid k values (now raises RetrievalError)
- Code duplication in performance metric calculation
- Dead code guard on empty results in batch logging
- Redundant function parameters in asyncio operations
- LLM timeout configuration ignored (now properly wired from LLM_TIMEOUT_SECONDS)
- API key security by accepting SecretStr type to prevent accidental leakage
- Empty OpenRouter API response handling with guards against IndexError
- Status code type safety in error handling (int instead of 'unknown' string)
- Grounding validation term matching improved with punctuation stripping

