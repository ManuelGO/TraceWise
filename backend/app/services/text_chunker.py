"""Text chunking service with semantic overlap."""

import logging

logger = logging.getLogger(__name__)


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 50,
    page_number: int | None = None,
) -> list[dict]:
    """Chunk text with semantic overlap.

    Splits text into chunks of roughly chunk_size characters, with
    overlap characters carried over to preserve context continuity.

    Args:
        text: Full extracted text
        chunk_size: Target characters per chunk (default 512)
        overlap: Overlap between consecutive chunks (default 50)
        page_number: Optional page number for PDF chunks (default None)

    Returns:
        List of chunk dicts: [{"text": "...", "index": 0, "page": None}]
    """
    if not text or not text.strip():
        return []

    if len(text) <= chunk_size:
        return [
            {
                "text": text,
                "index": 0,
                "page": page_number,
            }
        ]

    chunks = []
    index = 0
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            chunk_text = text[start:]
        else:
            end = min(end, len(text))
            last_space = text.rfind(" ", start, end)

            if last_space > start + chunk_size // 2:
                end = last_space + 1
            else:
                end = min(end, len(text))

        chunk_text = text[start:end].strip()

        if chunk_text:
            chunks.append(
                {
                    "text": chunk_text,
                    "index": index,
                    "page": page_number,
                }
            )
            index += 1

        start = end - overlap if end < len(text) else end

    return chunks


__all__ = ["chunk_text"]
