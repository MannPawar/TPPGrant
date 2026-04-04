from __future__ import annotations

import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from tpp_grants.config import GRANT_APPS_DIR, SUPPORTING_DOCS_DIR
from tpp_grants.models import CorpusChunk


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
HEADER_PATTERNS = [
    re.compile(r"^[A-Z][A-Z\s,&/\-\(\)]{4,}$"),
    re.compile(r"^\d+[\.\)]\s+[A-Z]"),
    re.compile(r"^\d+\.\d+[\.\)]?\s+[A-Z]"),
    re.compile(r"^[A-Z][A-Za-z0-9/&,\-\s]{3,80}:$"),
    re.compile(r"^(Section|Program|Overview|Budget|Impact|Question)\b", re.IGNORECASE),
]


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def _extract_pages(reader: PdfReader) -> list[tuple[int, str]]:
    pages: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append((index, text))
    return pages


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return _normalize_whitespace("\n".join(text for _, text in _extract_pages(reader)))


def extract_pdf_text_from_bytes(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    return _normalize_whitespace("\n".join(text for _, text in _extract_pages(reader)))


def _looks_like_header(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) < 4 or len(stripped) > 120:
        return False
    return any(pattern.match(stripped) for pattern in HEADER_PATTERNS)


def _estimate_level(line: str) -> int:
    stripped = line.strip()
    if re.match(r"^\d+\.\d+\.\d+", stripped):
        return 3
    if re.match(r"^\d+\.\d+", stripped):
        return 2
    if re.match(r"^\d+[\.\)]", stripped):
        return 1
    return 1


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


def _segment_sections(pages: list[tuple[int, str]]) -> list[dict]:
    sections: list[dict] = []
    current_title = "General"
    current_level = 1
    current_page_start = pages[0][0] if pages else 1
    current_lines: list[str] = []
    level_stack: dict[int, str] = {1: ""}

    def flush(end_page: int) -> None:
        nonlocal current_lines, current_title, current_page_start, current_level
        content = "\n".join(current_lines).strip()
        if content:
            sections.append(
                {
                    "title": current_title,
                    "parent_title": level_stack.get(current_level - 1, ""),
                    "level": current_level,
                    "page_start": current_page_start,
                    "page_end": end_page,
                    "content": content,
                }
            )
        current_lines = []

    for page_num, page_text in pages:
        for line in page_text.splitlines():
            stripped = line.strip()
            if not stripped:
                if current_lines:
                    current_lines.append("")
                continue

            if _looks_like_header(stripped):
                flush(page_num)
                level = _estimate_level(stripped)
                level_stack[level] = stripped.rstrip(":")
                for key in list(level_stack):
                    if key > level:
                        del level_stack[key]
                current_title = stripped.rstrip(":")
                current_level = level
                current_page_start = page_num
            else:
                current_lines.append(stripped)

    flush(pages[-1][0] if pages else 1)
    return sections


def _chunks_from_pages(
    pages: list[tuple[int, str]],
    source_file: str,
    collection_name: str,
    priority: float,
) -> list[CorpusChunk]:
    chunks: list[CorpusChunk] = []
    for section in _segment_sections(pages):
        section_chunks = chunk_text(section["content"])
        for chunk in section_chunks:
            chunks.append(
                CorpusChunk(
                    text=chunk,
                    source_file=source_file,
                    collection_name=collection_name,
                    priority=priority,
                    section_title=section["title"],
                    parent_section=section["parent_title"],
                    page_start=section["page_start"],
                    page_end=section["page_end"],
                )
            )
    return chunks


def _load_collection(folder: Path, collection_name: str, priority: float) -> list[CorpusChunk]:
    chunks: list[CorpusChunk] = []
    if not folder.exists():
        return chunks
    for path in sorted(folder.glob("*.pdf")):
        reader = PdfReader(str(path))
        pages = _extract_pages(reader)
        chunks.extend(_chunks_from_pages(pages, path.name, collection_name, priority))
    return chunks


def load_uploaded_corpus(
    grant_app_files: list[tuple[str, bytes]],
    supporting_files: list[tuple[str, bytes]],
) -> list[CorpusChunk]:
    corpus: list[CorpusChunk] = []
    for name, file_bytes in grant_app_files:
        reader = PdfReader(BytesIO(file_bytes))
        pages = _extract_pages(reader)
        corpus.extend(_chunks_from_pages(pages, name, "Grant Apps", 1.15))
    for name, file_bytes in supporting_files:
        reader = PdfReader(BytesIO(file_bytes))
        pages = _extract_pages(reader)
        corpus.extend(_chunks_from_pages(pages, name, "Impact Reports and Decks", 1.0))
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
        section_text = " ".join(
            [
                chunk.section_title,
                chunk.parent_section,
                chunk.text,
                chunk.collection_name,
            ]
        )
        tokens = tokenize(section_text)
        if not tokens:
            continue
        overlap = len(query_tokens.intersection(tokens))
        if overlap == 0:
            continue
        phrase_bonus = 0.0
        lowered = section_text.lower()
        for phrase in (
            "menstrual equity",
            "period poverty",
            "health education",
            "product distribution",
            "executive summary",
            "impact data",
            "budget",
            "organizational background",
        ):
            if phrase in lowered and phrase in query.lower():
                phrase_bonus += 0.8
        section_bonus = 0.0
        if chunk.collection_name == "Grant Apps":
            section_bonus += 0.5
        if chunk.section_title.lower() in query.lower():
            section_bonus += 1.0
        density = overlap / max(len(query_tokens), 1)
        score = (density * 8.0 + phrase_bonus + section_bonus) * chunk.priority
        scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:limit]]
