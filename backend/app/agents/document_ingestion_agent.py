"""Document Ingestion Agent (Task 45, Phase 6).

A LangGraph ``StateGraph`` that orchestrates the document ingestion pipeline by
wrapping existing Phase 1-5 services. The agent does NOT reimplement any extraction,
validation, chunking, or embedding logic -- it is a thin orchestration layer.

Pipeline::

    START -> validate -> classify -> extract -> chunk -> embed -> store -> END
                 |         |        (no text)             (embed err)
                 +--------+--------+------------------+--------------> END (error set)

Each node is a function ``state -> dict`` returning a partial update to
``DocumentIngestionState``. Permanent errors (validation, unsupported MIME, empty
text, embedding failure) set ``state["error"]`` and route straight to ``END`` -- they
do not raise out of the graph. This mirrors the "fail immediately, no retry" semantics
of the existing Celery pipeline (``app.tasks.document_tasks``).

Design notes (coordinator-confirmed, 2026-06-16):
- store_node persists vectors to ``PostgresVectorStore`` (decision A).
- The graph core is DB-free: callers pass ``file_bytes``/``filename``/``document_id``
  in the initial state (decision B). When persistence is enabled the caller also
  supplies ``document_extraction_id``.
- Errors set state and route to END; nodes never raise for permanent errors (decision C).

This task does NOT configure a checkpointer; ``build_document_ingestion_graph`` accepts
an optional ``checkpointer`` so Task 52 (workflow state persistence) is a drop-in.
"""

import logging
from collections.abc import Callable
from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.exceptions import (
    FileExtensionMismatchError,
    FileSizeTooLargeError,
    MimeTypeNotAllowedError,
)
from app.models.vector_embedding import EmbeddingData
from app.monitoring.retry_metrics import _sanitize_log
from app.services.embedding_service import EmbeddingError, EmbeddingService
from app.services.file_handler import classify_document_type
from app.services.file_validator import (
    validate_extension,
    validate_file_size,
    validate_mime_type,
)
from app.services.text_chunker import TextChunker
from app.services.text_extractor import (
    ExtractionError,
    extract_from_csv,
    extract_from_docx,
    extract_from_pdf,
    extract_from_txt,
    extract_from_xlsx,
)
from app.services.vector_store import PostgresVectorStore, VectorStore, VectorStoreError

logger = logging.getLogger(__name__)


# MIME type -> extractor dispatch. PDF returns (text, pages); the rest return text only.
_PDF_MIME = "application/pdf"
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_CSV_MIME = "text/csv"
_TXT_MIME = "text/plain"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ===== State contract =====


class DocumentIngestionState(TypedDict, total=False):
    """Shared state threaded through the document ingestion graph.

    ``total=False`` so each node may return a partial update without re-declaring
    every key. Inputs (``document_id``, ``filename``, ``file_bytes``) are supplied by
    the caller; later keys are filled in by successive nodes.
    """

    # Inputs (caller-supplied)
    document_id: str
    filename: str
    file_bytes: bytes
    # Optional: required only when vector persistence is enabled (decision A).
    document_extraction_id: str

    # validate_node
    detected_mime: str
    # classify_node
    document_type: str
    # extract_node
    extracted_text: str
    pages: int | None
    # chunk_node
    chunks: list[dict[str, Any]]
    chunk_count: int
    # embed_node
    embeddings: list[dict[str, Any]]
    # store_node
    stored_count: int

    # Error channel: when ``error`` is set the graph short-circuits to END.
    error: str | None
    error_type: str | None


def _fail(error_type: str, message: str) -> dict[str, Any]:
    """Build a partial state update representing a permanent failure."""
    logger.warning("Document ingestion failed (%s): %s", error_type, _sanitize_log(message))
    return {"error": message, "error_type": error_type}


def _has_error(state: DocumentIngestionState) -> bool:
    """True when an upstream node has already recorded a permanent error."""
    return bool(state.get("error"))


# ===== Nodes =====


def validate_node(state: DocumentIngestionState) -> dict[str, Any]:
    """Validate file size, MIME type (magic bytes), and extension consistency.

    Reuses ``app.services.file_validator`` in the same order as the Celery
    ``_validate_document`` path so both agree on what "valid" means. On success
    records ``detected_mime``; on failure records ``error``/``error_type``.
    """
    file_bytes = state.get("file_bytes")
    filename = state.get("filename")
    if not file_bytes:
        return _fail("validation", "No file_bytes provided for validation")
    if not filename:
        return _fail("validation", "No filename provided for validation")

    try:
        validate_file_size(len(file_bytes))
        detected_mime = validate_mime_type(file_bytes)
        validate_extension(filename, detected_mime)
    except (
        FileSizeTooLargeError,
        MimeTypeNotAllowedError,
        FileExtensionMismatchError,
    ) as exc:
        return _fail("validation", str(exc))

    logger.info("Validation passed; detected MIME %s", detected_mime)
    return {"detected_mime": detected_mime}


def classify_node(state: DocumentIngestionState) -> dict[str, Any]:
    """Classify the document type from filename + detected MIME.

    Wraps ``file_handler.classify_document_type``; always returns a valid
    ``DocumentType`` value (defaulting to ``other``).
    """
    filename = state.get("filename", "")
    detected_mime = state.get("detected_mime", "")
    document_type = classify_document_type(filename, detected_mime)
    logger.info("Classified document as %s", document_type)
    return {"document_type": document_type}


def extract_node(state: DocumentIngestionState) -> dict[str, Any]:
    """Extract raw text from the file, dispatching on detected MIME type.

    PDF additionally yields a page count. Empty/whitespace-only output and
    unsupported MIME types are treated as permanent extraction errors.
    """
    file_bytes = state.get("file_bytes")
    detected_mime = state.get("detected_mime")
    if not file_bytes:
        return _fail("extraction", "No file_bytes available for extraction")

    pages: int | None = None
    try:
        if detected_mime == _PDF_MIME:
            extracted_text, pages = extract_from_pdf(file_bytes)
        elif detected_mime == _DOCX_MIME:
            extracted_text = extract_from_docx(file_bytes)
        elif detected_mime == _CSV_MIME:
            extracted_text = extract_from_csv(file_bytes)
        elif detected_mime == _TXT_MIME:
            extracted_text = extract_from_txt(file_bytes)
        elif detected_mime == _XLSX_MIME:
            extracted_text = extract_from_xlsx(file_bytes)
        else:
            return _fail("extraction", f"Unsupported MIME type for extraction: {detected_mime}")
    except ExtractionError as exc:
        return _fail("extraction", str(exc))

    if not extracted_text or not extracted_text.strip():
        return _fail("extraction", "No text extracted from document")

    logger.info(
        "Extracted %d chars (pages=%s) from %s",
        len(extracted_text),
        pages,
        detected_mime,
    )
    return {"extracted_text": extracted_text, "pages": pages}


def chunk_node(state: DocumentIngestionState) -> dict[str, Any]:
    """Split extracted text into overlapping chunks via ``TextChunker``.

    Uses the same defaults as the Celery extraction path
    (chunk_size=1000, overlap=150, sentence_aware).
    """
    extracted_text = state.get("extracted_text", "")
    document_id = state.get("document_id")
    chunker = TextChunker(chunk_size=1000, overlap=150, strategy="sentence_aware")
    chunks = chunker.chunk(extracted_text, document_id=document_id)
    if not chunks:
        return _fail("extraction", "Chunking produced no chunks")
    logger.info("Produced %d chunks", len(chunks))
    return {"chunks": chunks, "chunk_count": len(chunks)}


async def embed_node(
    state: DocumentIngestionState,
    embedding_service: EmbeddingService,
) -> dict[str, Any]:
    """Generate vector embeddings for the document chunks.

    ``EmbeddingService.embed_chunks`` expects dicts keyed by ``chunk_id``/``text``;
    chunker output uses ``index``/``text``, so we adapt here (orchestration glue).
    """
    chunks = state.get("chunks") or []
    if not chunks:
        return {"embeddings": []}

    embed_inputs = [{"chunk_id": str(chunk["index"]), "text": chunk["text"]} for chunk in chunks]
    try:
        embeddings = await embedding_service.embed_chunks(embed_inputs)
    except EmbeddingError as exc:
        return _fail("embedding", str(exc))

    logger.info("Generated %d embeddings", len(embeddings))
    return {"embeddings": embeddings}


async def store_node(
    state: DocumentIngestionState,
    vector_store: VectorStore,
) -> dict[str, Any]:
    """Persist embeddings to the vector store (decision A).

    Maps each embedding to an ``EmbeddingData`` row and calls
    ``vector_store.store_embeddings``. Requires ``document_extraction_id`` in state.
    """
    embeddings = state.get("embeddings") or []
    if not embeddings:
        return {"stored_count": 0}

    extraction_id = state.get("document_extraction_id")
    if not extraction_id:
        return _fail(
            "storage",
            "document_extraction_id required to persist embeddings",
        )

    chunks = state.get("chunks") or []
    text_by_index = {str(chunk["index"]): chunk["text"] for chunk in chunks}

    rows: list[EmbeddingData] = []
    for position, embedding in enumerate(embeddings):
        chunk_id = embedding.get("chunk_id")
        if chunk_id is None or not chunk_id.isdigit():
            return _fail(
                "storage", f"Embedding at position {position} has invalid chunk_id {chunk_id!r}"
            )
        chunk_index = int(chunk_id)
        rows.append(
            EmbeddingData(
                document_extraction_id=extraction_id,
                chunk_index=chunk_index,
                embedding=embedding["vector"],
                embedding_model=embedding["model_name"],
                embedding_dim=embedding["embedding_dim"],
                chunk_text=text_by_index.get(chunk_id, ""),
            )
        )

    try:
        stored_count = await vector_store.store_embeddings(rows)
    except VectorStoreError as exc:
        return _fail("storage", str(exc))

    logger.info("Stored %d embeddings for extraction %s", stored_count, extraction_id)
    return {"stored_count": stored_count}


# ===== Graph assembly =====


def _route_after(node_name: str) -> Callable[[DocumentIngestionState], str]:
    """Build a conditional-edge router that goes to END on error, else to ``node_name``."""

    def router(state: DocumentIngestionState) -> str:
        return END if _has_error(state) else node_name

    return router


def build_document_ingestion_graph(
    *,
    embedding_service: EmbeddingService | None = None,
    vector_store: VectorStore | None = None,
    checkpointer: Any | None = None,
) -> CompiledStateGraph:
    """Build and compile the document ingestion ``StateGraph``.

    Args:
        embedding_service: Embedding service (injected for testing). Defaults to a
            real ``EmbeddingService`` constructed lazily.
        vector_store: Vector store (injected for testing). Defaults to a real
            ``PostgresVectorStore``.
        checkpointer: Optional LangGraph checkpointer (forward-compat for Task 52).

    Returns:
        A compiled graph supporting ``ainvoke``.
    """
    if embedding_service is None:
        embedding_service = EmbeddingService()
    if vector_store is None:
        from app.tasks.document_tasks import _get_engine_and_factory

        _, session_factory = _get_engine_and_factory()
        vector_store = PostgresVectorStore(session_factory)

    async def _embed(state: DocumentIngestionState) -> dict[str, Any]:
        return await embed_node(state, embedding_service)

    async def _store(state: DocumentIngestionState) -> dict[str, Any]:
        return await store_node(state, vector_store)

    builder: StateGraph = StateGraph(DocumentIngestionState)
    builder.add_node("validate", validate_node)
    builder.add_node("classify", classify_node)
    builder.add_node("extract", extract_node)
    builder.add_node("chunk", chunk_node)
    builder.add_node("embed", _embed)
    builder.add_node("store", _store)

    builder.add_edge(START, "validate")
    # Each step routes to END if a permanent error was recorded, else to the next node.
    builder.add_conditional_edges("validate", _route_after("classify"))
    builder.add_conditional_edges("classify", _route_after("extract"))
    builder.add_conditional_edges("extract", _route_after("chunk"))
    builder.add_conditional_edges("chunk", _route_after("embed"))
    builder.add_conditional_edges("embed", _route_after("store"))
    builder.add_edge("store", END)

    return builder.compile(checkpointer=checkpointer)


async def run_document_ingestion(
    initial_state: DocumentIngestionState,
    *,
    graph: CompiledStateGraph | None = None,
) -> DocumentIngestionState:
    """Run the document ingestion graph over ``initial_state``.

    Args:
        initial_state: Caller-supplied state with at least ``document_id``,
            ``filename``, and ``file_bytes`` (plus ``document_extraction_id`` when
            persisting embeddings).
        graph: Optional pre-built compiled graph (injected for testing). When omitted
            a default graph is built with real services.

    Returns:
        The final ``DocumentIngestionState`` after execution.
    """
    if graph is None:
        graph = build_document_ingestion_graph()
    result = await graph.ainvoke(initial_state)
    return cast(DocumentIngestionState, result)
