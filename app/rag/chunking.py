from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import Settings
from app.core.utils import normalize_business_text


def split_business_text(text: str, settings: Settings) -> list[str]:
    normalized = normalize_business_text(text)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    chunks = [chunk.strip() for chunk in splitter.split_text(normalized) if chunk.strip()]
    if not chunks and normalized:
        chunks = [normalized]
    return chunks
