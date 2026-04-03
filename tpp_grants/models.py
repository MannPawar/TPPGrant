from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SourceSearchRecord:
    source_name: str
    query: str
    attempted: bool
    result_count: int = 0
    notes: str = ""


@dataclass(slots=True)
class GrantOpportunity:
    title: str
    source_name: str
    source_url: str
    search_url: str
    summary: str
    deadline: str = "Unknown"
    funding_amount: str = "Unknown"
    eligibility: str = "Unknown"
    location: str = "Unspecified"
    status: str = "Unknown"
    opportunity_id: str = ""
    raw_text: str = ""
    ranking_notes: list[str] = field(default_factory=list)
    scoring_breakdown: dict[str, float] = field(default_factory=dict)
    total_score: float = 0.0

    def dedupe_key(self) -> str:
        cleaned = "".join(ch.lower() for ch in self.title if ch.isalnum())
        amount = "".join(ch.lower() for ch in self.funding_amount if ch.isalnum())
        return f"{self.source_name}:{cleaned}:{amount}"


@dataclass(slots=True)
class CorpusChunk:
    text: str
    source_file: str
    collection_name: str
    priority: float


@dataclass(slots=True)
class ProposalDraft:
    executive_summary: str
    organization_fit: str
    tailored_program_pitch: str
    evidence_points: list[str]
    source_highlights: list[dict[str, Any]]
