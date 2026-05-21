# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- Last updated: 2026-05-21 | Covers: Phase 2 & 3 development through Task 30 -->

## [Unreleased]

### Added
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

### Changed
- Migrated backend to async drivers and implemented scalable FastAPI architecture
- Reorganized frontend app structure with security best practices and Angular 19
- Consolidated dependency management into pyproject.toml
- Enhanced document processing with validation pipeline

### Fixed
- Path traversal vulnerability with pathlib-based containment validation
- Metadata parsing crashes with None guards
- Frontmatter delimiter ambiguity with regex MULTILINE flag
- Unguarded dictionary access with .get() patterns
- Bare exception handlers with specific exception types
- Category validation brittleness by extracting from index

