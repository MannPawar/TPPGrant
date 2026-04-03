from __future__ import annotations

import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from tpp_grants.config import GRANT_APPS_DIR, SUPPORTING_DOCS_DIR
from tpp_grants.models import CorpusChunk


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            continue
    return _normalize_whitespace("\n".join(pages))


def extract_pdf_text_from_bytes(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            continue
    return _normalize_whitespace("\n".join(pages))


def chunk_text(text: str, chunk_size: int = 1400, overlap: int = 250) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(text_length, start + chunk_size)
        chunks.append(text[start:end].strip())
        if end == text_length:
            break
        start = max(0, end - overlap)
    return [chunk for chunk in chunks if chunk]


def _load_collection(folder: Path, collection_name: str, priority: float) -> list[CorpusChunk]:
    chunks: list[CorpusChunk] = []
    if not folder.exists():
        return chunks
    for path in sorted(folder.glob("*.pdf")):
        text = extract_pdf_text(path)
        for chunk in chunk_text(text):
            chunks.append(
                CorpusChunk(
                    text=chunk,
                    source_file=path.name,
                    collection_name=collection_name,
                    priority=priority,
                )
            )
    return chunks


def load_uploaded_corpus(
    grant_app_files: list[tuple[str, bytes]],
    supporting_files: list[tuple[str, bytes]],
) -> list[CorpusChunk]:
    corpus: list[CorpusChunk] = []
    for name, file_bytes in grant_app_files:
        text = extract_pdf_text_from_bytes(file_bytes)
        for chunk in chunk_text(text):
            corpus.append(
                CorpusChunk(
                    text=chunk,
                    source_file=name,
                    collection_name="Grant Apps",
                    priority=1.15,
                )
            )
    for name, file_bytes in supporting_files:
        text = extract_pdf_text_from_bytes(file_bytes)
        for chunk in chunk_text(text):
            corpus.append(
                CorpusChunk(
                    text=chunk,
                    source_file=name,
                    collection_name="Impact Reports and Decks",
                    priority=1.0,
                )
            )
    return corpus


@lru_cache(maxsize=1)
def load_corpus() -> list[CorpusChunk]:
    corpus: list[CorpusChunk] = []
    corpus.extend(_load_collection(GRANT_APPS_DIR, "Grant Apps", 1.15))
    corpus.extend(_load_collection(SUPPORTING_DOCS_DIR, "Impact Reports and Decks", 1.0))
    return corpus


def rank_corpus_chunks(
    query: str,
    limit: int = 8,
    corpus_chunks: list[CorpusChunk] | None = None,
) -> list[CorpusChunk]:
    query_tokens = set(tokenize(query))
    scored: list[tuple[float, CorpusChunk]] = []
    candidate_chunks = corpus_chunks if corpus_chunks is not None else load_corpus()
    for chunk in candidate_chunks:
        tokens = tokenize(chunk.text)
        if not tokens:
            continue
        overlap = len(query_tokens.intersection(tokens))
        if overlap == 0:
            continue
        phrase_bonus = 0.0
        lowered = chunk.text.lower()
        for phrase in (
            "menstrual equity",
            "period poverty",
            "health education",
            "product distribution",
            "executive summary",
            "impact data",
        ):
            if phrase in lowered and phrase in query.lower():
                phrase_bonus += 0.8
        density = overlap / max(len(query_tokens), 1)
        score = (density * 8.0 + phrase_bonus) * chunk.priority
        scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:limit]]
