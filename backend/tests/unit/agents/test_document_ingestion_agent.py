"""Unit tests for the Document Ingestion Agent (Task 45).

Nodes are tested in isolation with the underlying services mocked so the suite runs
fully offline (no magic-byte detection, no network, no DB). Graph-level tests inject
fake services to exercise routing without real I/O.
"""

from typing import Any

import pytest

from app.agents import document_ingestion_agent as agent
from app.agents.document_ingestion_agent import (
    chunk_node,
    classify_node,
    embed_node,
    extract_node,
    store_node,
    validate_node,
)
from app.exceptions import (
    FileExtensionMismatchError,
    FileSizeTooLargeError,
    MimeTypeNotAllowedError,
)
from app.services.embedding_service import EmbeddingError
from app.services.vector_store import VectorStoreError

PDF_MIME = "application/pdf"
TXT_MIME = "text/plain"


# ===== validate_node =====


def test_validate_node_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "validate_file_size", lambda size: None)
    monkeypatch.setattr(agent, "validate_mime_type", lambda b: PDF_MIME)
    monkeypatch.setattr(agent, "validate_extension", lambda f, m: None)

    result = validate_node({"filename": "doc.pdf", "file_bytes": b"%PDF-1.4 data"})

    assert result["detected_mime"] == PDF_MIME
    assert "error" not in result


def test_validate_node_missing_file_bytes() -> None:
    result = validate_node({"filename": "doc.pdf", "file_bytes": b""})
    assert result["error_type"] == "validation"
    assert "file_bytes" in result["error"]


def test_validate_node_missing_filename() -> None:
    result = validate_node({"filename": "", "file_bytes": b"data"})
    assert result["error_type"] == "validation"
    assert "filename" in result["error"]


def test_validate_node_oversized(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(size: int) -> None:
        raise FileSizeTooLargeError(actual_size=size, max_size=10)

    monkeypatch.setattr(agent, "validate_file_size", _raise)

    result = validate_node({"filename": "doc.pdf", "file_bytes": b"too big"})

    assert result["error_type"] == "validation"
    assert "exceeds maximum" in result["error"]


def test_validate_node_disallowed_mime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "validate_file_size", lambda size: None)

    def _raise(b: bytes) -> str:
        raise MimeTypeNotAllowedError(detected_type="image/png", allowed_types=[PDF_MIME])

    monkeypatch.setattr(agent, "validate_mime_type", _raise)

    result = validate_node({"filename": "doc.png", "file_bytes": b"\x89PNG"})

    assert result["error_type"] == "validation"
    assert "not allowed" in result["error"]


def test_validate_node_extension_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "validate_file_size", lambda size: None)
    monkeypatch.setattr(agent, "validate_mime_type", lambda b: PDF_MIME)

    def _raise(filename: str, mime: str) -> None:
        raise FileExtensionMismatchError(
            expected_mime=mime, found_extension=".txt", filename=filename
        )

    monkeypatch.setattr(agent, "validate_extension", _raise)

    result = validate_node({"filename": "doc.txt", "file_bytes": b"%PDF"})

    assert result["error_type"] == "validation"
    assert "does not match" in result["error"]


# ===== classify_node =====


@pytest.mark.parametrize(
    ("filename", "mime", "expected"),
    [
        ("supplier_declaration.pdf", PDF_MIME, "supplier_declaration"),
        ("invoice.pdf", PDF_MIME, "invoice"),
        ("shipment_note.pdf", PDF_MIME, "shipment_note"),
        ("certificate.pdf", PDF_MIME, "certificate"),
        ("random.pdf", PDF_MIME, "other"),
    ],
)
def test_classify_node_dispatches_to_service(
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    mime: str,
    expected: str,
) -> None:
    captured: dict[str, Any] = {}

    def _classify(fname: str, mtype: str) -> str:
        captured["filename"] = fname
        captured["mime"] = mtype
        return expected

    monkeypatch.setattr(agent, "classify_document_type", _classify)

    result = classify_node({"filename": filename, "detected_mime": mime})

    assert result["document_type"] == expected
    assert captured == {"filename": filename, "mime": mime}


def test_classify_node_defaults_missing_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "classify_document_type", lambda f, m: "other")
    result = classify_node({})
    assert result["document_type"] == "other"


# ===== extract_node =====


def test_extract_node_pdf_returns_text_and_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "extract_from_pdf", lambda b: ("pdf text", 3))

    result = extract_node({"file_bytes": b"%PDF", "detected_mime": PDF_MIME})

    assert result["extracted_text"] == "pdf text"
    assert result["pages"] == 3


@pytest.mark.parametrize(
    ("mime", "func_name"),
    [
        (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "extract_from_docx",
        ),
        ("text/csv", "extract_from_csv"),
        (TXT_MIME, "extract_from_txt"),
        (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "extract_from_xlsx",
        ),
    ],
)
def test_extract_node_non_pdf_formats(
    monkeypatch: pytest.MonkeyPatch, mime: str, func_name: str
) -> None:
    monkeypatch.setattr(agent, func_name, lambda b: "extracted body")

    result = extract_node({"file_bytes": b"data", "detected_mime": mime})

    assert result["extracted_text"] == "extracted body"
    assert result["pages"] is None


def test_extract_node_unsupported_mime() -> None:
    result = extract_node({"file_bytes": b"data", "detected_mime": "image/png"})
    assert result["error_type"] == "extraction"
    assert "Unsupported MIME" in result["error"]


def test_extract_node_missing_file_bytes() -> None:
    result = extract_node({"file_bytes": b"", "detected_mime": PDF_MIME})
    assert result["error_type"] == "extraction"


def test_extract_node_empty_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "extract_from_txt", lambda b: "")
    result = extract_node({"file_bytes": b"data", "detected_mime": TXT_MIME})
    assert result["error_type"] == "extraction"
    assert "No text extracted" in result["error"]


def test_extract_node_whitespace_only_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "extract_from_txt", lambda b: "   \n\t  ")
    result = extract_node({"file_bytes": b"data", "detected_mime": TXT_MIME})
    assert result["error_type"] == "extraction"


def test_extract_node_propagates_extraction_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(b: bytes) -> tuple[str, int]:
        raise agent.ExtractionError("corrupt pdf")

    monkeypatch.setattr(agent, "extract_from_pdf", _raise)

    result = extract_node({"file_bytes": b"%PDF", "detected_mime": PDF_MIME})

    assert result["error_type"] == "extraction"
    assert "corrupt pdf" in result["error"]


# ===== chunk_node =====


def test_chunk_node_produces_chunks() -> None:
    text = "First sentence. Second sentence. Third sentence."
    result = chunk_node({"extracted_text": text, "document_id": "doc-1"})

    assert result["chunk_count"] == len(result["chunks"])
    assert result["chunk_count"] > 0
    assert all("text" in chunk for chunk in result["chunks"])


def test_chunk_node_passes_document_id() -> None:
    result = chunk_node({"extracted_text": "Some text here.", "document_id": "doc-xyz"})
    assert result["chunks"][0]["document_id"] == "doc-xyz"


def test_chunk_node_empty_text_errors() -> None:
    result = chunk_node({"extracted_text": "", "document_id": "doc-1"})
    assert result["error_type"] == "extraction"
    assert "no chunks" in result["error"].lower()


# ===== Fakes for embed/store/graph tests =====


class FakeEmbeddingService:
    """Stand-in for EmbeddingService.embed_chunks (no network)."""

    def __init__(self, *, raise_error: bool = False, dim: int = 4) -> None:
        self.raise_error = raise_error
        self.dim = dim
        self.calls: list[list[dict[str, Any]]] = []

    async def embed_chunks(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.calls.append(chunks)
        if self.raise_error:
            raise EmbeddingError("embedding provider unavailable")
        return [
            {
                "chunk_id": chunk["chunk_id"],
                "vector": [0.1] * self.dim,
                "model_name": "fake-model",
                "embedding_dim": self.dim,
            }
            for chunk in chunks
        ]


class FakeVectorStore:
    """Stand-in for VectorStore.store_embeddings (no DB)."""

    def __init__(self, *, raise_error: bool = False) -> None:
        self.raise_error = raise_error
        self.stored: list[Any] = []

    async def store_embeddings(self, embeddings: list[Any]) -> int:
        if self.raise_error:
            raise VectorStoreError("db write failed")
        self.stored = list(embeddings)
        return len(embeddings)


def _two_chunks() -> list[dict[str, Any]]:
    return [
        {"index": 0, "text": "chunk zero"},
        {"index": 1, "text": "chunk one"},
    ]


# ===== embed_node =====


async def test_embed_node_success() -> None:
    service = FakeEmbeddingService()
    result = await embed_node({"chunks": _two_chunks()}, service)  # type: ignore[arg-type]

    assert len(result["embeddings"]) == 2
    # Adapts chunker 'index' -> embed_chunks 'chunk_id'
    assert service.calls[0][0]["chunk_id"] == "0"
    assert service.calls[0][0]["text"] == "chunk zero"


async def test_embed_node_empty_chunks_returns_empty() -> None:
    service = FakeEmbeddingService()
    result = await embed_node({"chunks": []}, service)  # type: ignore[arg-type]
    assert result["embeddings"] == []
    assert service.calls == []


async def test_embed_node_embedding_error() -> None:
    service = FakeEmbeddingService(raise_error=True)
    result = await embed_node({"chunks": _two_chunks()}, service)  # type: ignore[arg-type]

    assert result["error_type"] == "embedding"
    assert "unavailable" in result["error"]
    assert "embeddings" not in result


# ===== store_node =====


async def test_store_node_persists_embeddings() -> None:
    store = FakeVectorStore()
    embeddings = [
        {"chunk_id": "0", "vector": [0.1, 0.2], "model_name": "m", "embedding_dim": 2},
        {"chunk_id": "1", "vector": [0.3, 0.4], "model_name": "m", "embedding_dim": 2},
    ]
    state = {
        "embeddings": embeddings,
        "chunks": _two_chunks(),
        "document_extraction_id": "ext-99",
    }

    result = await store_node(state, store)  # type: ignore[arg-type]

    assert result["stored_count"] == 2
    assert len(store.stored) == 2
    row = store.stored[0]
    assert row["document_extraction_id"] == "ext-99"
    assert row["chunk_index"] == 0
    assert row["embedding"] == [0.1, 0.2]
    assert row["embedding_model"] == "m"
    assert row["embedding_dim"] == 2
    assert row["chunk_text"] == "chunk zero"


async def test_store_node_requires_extraction_id() -> None:
    store = FakeVectorStore()
    state = {
        "embeddings": [{"chunk_id": "0", "vector": [0.1], "model_name": "m", "embedding_dim": 1}],
        "chunks": _two_chunks(),
    }
    result = await store_node(state, store)  # type: ignore[arg-type]

    assert result["error_type"] == "storage"
    assert "document_extraction_id" in result["error"]
    assert store.stored == []


async def test_store_node_empty_embeddings_noop() -> None:
    store = FakeVectorStore()
    result = await store_node({"embeddings": []}, store)  # type: ignore[arg-type]
    assert result["stored_count"] == 0
    assert store.stored == []


async def test_store_node_propagates_store_error() -> None:
    store = FakeVectorStore(raise_error=True)
    state = {
        "embeddings": [{"chunk_id": "0", "vector": [0.1], "model_name": "m", "embedding_dim": 1}],
        "chunks": _two_chunks(),
        "document_extraction_id": "ext-1",
    }
    result = await store_node(state, store)  # type: ignore[arg-type]

    assert result["error_type"] == "storage"
    assert "db write failed" in result["error"]


# ===== Graph assembly + routing =====


def _patch_successful_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch validate/extract/classify module fns to a happy path."""
    monkeypatch.setattr(agent, "validate_file_size", lambda size: None)
    monkeypatch.setattr(agent, "validate_mime_type", lambda b: TXT_MIME)
    monkeypatch.setattr(agent, "validate_extension", lambda f, m: None)
    monkeypatch.setattr(agent, "classify_document_type", lambda f, m: "invoice")
    monkeypatch.setattr(
        agent,
        "extract_from_txt",
        lambda b: "First sentence. Second sentence. Third sentence.",
    )


def _valid_initial_state() -> dict[str, Any]:
    return {
        "document_id": "doc-1",
        "document_extraction_id": "ext-1",
        "filename": "invoice.txt",
        "file_bytes": b"some bytes",
    }


async def test_graph_happy_path_reaches_store(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_successful_pipeline(monkeypatch)
    embed_service = FakeEmbeddingService()
    store = FakeVectorStore()
    graph = agent.build_document_ingestion_graph(
        embedding_service=embed_service,  # type: ignore[arg-type]
        vector_store=store,  # type: ignore[arg-type]
    )

    final = await graph.ainvoke(_valid_initial_state())

    assert final.get("error") is None
    assert final["detected_mime"] == TXT_MIME
    assert final["document_type"] == "invoice"
    assert final["chunk_count"] > 0
    assert final["stored_count"] >= 1
    assert len(store.stored) >= 1


async def test_graph_run_document_ingestion_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_successful_pipeline(monkeypatch)
    graph = agent.build_document_ingestion_graph(
        embedding_service=FakeEmbeddingService(),  # type: ignore[arg-type]
        vector_store=FakeVectorStore(),  # type: ignore[arg-type]
    )

    final = await agent.run_document_ingestion(_valid_initial_state(), graph=graph)  # type: ignore[arg-type]

    assert final["stored_count"] >= 1


async def test_graph_validation_failure_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_successful_pipeline(monkeypatch)

    def _raise(size: int) -> None:
        raise FileSizeTooLargeError(actual_size=size, max_size=1)

    monkeypatch.setattr(agent, "validate_file_size", _raise)
    embed_service = FakeEmbeddingService()
    store = FakeVectorStore()
    graph = agent.build_document_ingestion_graph(
        embedding_service=embed_service,  # type: ignore[arg-type]
        vector_store=store,  # type: ignore[arg-type]
    )

    final = await graph.ainvoke(_valid_initial_state())

    assert final["error_type"] == "validation"
    # Downstream side effects skipped
    assert "document_type" not in final
    assert "chunks" not in final
    assert embed_service.calls == []
    assert store.stored == []


async def test_graph_extraction_failure_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_successful_pipeline(monkeypatch)
    monkeypatch.setattr(agent, "extract_from_txt", lambda b: "")
    embed_service = FakeEmbeddingService()
    store = FakeVectorStore()
    graph = agent.build_document_ingestion_graph(
        embedding_service=embed_service,  # type: ignore[arg-type]
        vector_store=store,  # type: ignore[arg-type]
    )

    final = await graph.ainvoke(_valid_initial_state())

    assert final["error_type"] == "extraction"
    assert embed_service.calls == []
    assert store.stored == []


async def test_graph_embedding_failure_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_successful_pipeline(monkeypatch)
    store = FakeVectorStore()
    graph = agent.build_document_ingestion_graph(
        embedding_service=FakeEmbeddingService(raise_error=True),  # type: ignore[arg-type]
        vector_store=store,  # type: ignore[arg-type]
    )

    final = await graph.ainvoke(_valid_initial_state())

    assert final["error_type"] == "embedding"
    # store never reached
    assert store.stored == []
    assert "stored_count" not in final


# ===== Hardening / wiring =====


def test_build_graph_defaults_construct_real_services(monkeypatch: pytest.MonkeyPatch) -> None:
    """When no services are injected, the builder constructs real ones (mocked here)."""
    created: dict[str, bool] = {}

    class _FakeEmbeddingService:
        def __init__(self) -> None:
            created["embedding"] = True

    class _FakePostgresVectorStore:
        def __init__(self, session_factory: Any) -> None:
            created["vector"] = True

    monkeypatch.setattr(agent, "EmbeddingService", _FakeEmbeddingService)
    monkeypatch.setattr(agent, "PostgresVectorStore", _FakePostgresVectorStore)
    monkeypatch.setattr(
        "app.tasks.document_tasks._get_engine_and_factory",
        lambda: (object(), object()),
    )

    graph = agent.build_document_ingestion_graph()

    assert created == {"embedding": True, "vector": True}
    assert graph is not None


def test_build_graph_passes_checkpointer(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    stub_graph = object()

    def _spy_compile(self: Any, *args: Any, **kwargs: Any) -> Any:
        captured["checkpointer"] = kwargs.get("checkpointer")
        return stub_graph

    monkeypatch.setattr(agent.StateGraph, "compile", _spy_compile)
    sentinel = object()

    graph = agent.build_document_ingestion_graph(
        embedding_service=FakeEmbeddingService(),  # type: ignore[arg-type]
        vector_store=FakeVectorStore(),  # type: ignore[arg-type]
        checkpointer=sentinel,
    )

    assert captured["checkpointer"] is sentinel
    assert graph is stub_graph


async def test_run_document_ingestion_builds_default_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_document_ingestion builds a default graph when none is injected."""
    _patch_successful_pipeline(monkeypatch)
    built: dict[str, bool] = {}
    real_build = agent.build_document_ingestion_graph

    def _fake_build(**kwargs: Any) -> Any:
        built["called"] = True
        return real_build(
            embedding_service=FakeEmbeddingService(),
            vector_store=FakeVectorStore(),
        )

    monkeypatch.setattr(agent, "build_document_ingestion_graph", _fake_build)

    final = await agent.run_document_ingestion(_valid_initial_state())  # type: ignore[arg-type]

    assert built["called"] is True
    assert final["stored_count"] >= 1


async def test_store_node_non_digit_chunk_id_fails_loud() -> None:
    store = FakeVectorStore()
    state = {
        "embeddings": [
            {"chunk_id": "abc", "vector": [0.5], "model_name": "m", "embedding_dim": 1},
        ],
        "chunks": [{"index": 0, "text": "zero"}],
        "document_extraction_id": "ext-1",
    }

    result = await store_node(state, store)  # type: ignore[arg-type]

    # Non-digit chunk_id triggers immediate failure, no silent fallback
    assert result["error_type"] == "storage"
    assert "invalid chunk_id" in result["error"]
    assert "'abc'" in result["error"]
    assert len(store.stored) == 0  # No rows persisted


async def test_store_node_missing_chunk_id_fails_loud() -> None:
    store = FakeVectorStore()
    state = {
        "embeddings": [
            {"vector": [0.5], "model_name": "m", "embedding_dim": 1},  # Missing chunk_id
        ],
        "chunks": [{"index": 0, "text": "zero"}],
        "document_extraction_id": "ext-1",
    }

    result = await store_node(state, store)  # type: ignore[arg-type]

    # Missing chunk_id triggers immediate failure
    assert result["error_type"] == "storage"
    assert "invalid chunk_id" in result["error"]
    assert len(store.stored) == 0  # No rows persisted


def test_extract_node_none_mime_is_unsupported() -> None:
    result = extract_node({"file_bytes": b"data", "detected_mime": None})
    assert result["error_type"] == "extraction"
    assert "Unsupported MIME" in result["error"]


async def test_embed_node_maps_index_to_chunk_id_order() -> None:
    service = FakeEmbeddingService()
    chunks = [
        {"index": 5, "text": "five"},
        {"index": 9, "text": "nine"},
    ]
    await embed_node({"chunks": chunks}, service)  # type: ignore[arg-type]

    sent = service.calls[0]
    assert [c["chunk_id"] for c in sent] == ["5", "9"]
    assert [c["text"] for c in sent] == ["five", "nine"]
