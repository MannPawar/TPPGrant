from __future__ import annotations

import re

from tpp_grants.config import TPP_PROFILE
from tpp_grants.corpus import rank_corpus_chunks
from tpp_grants.models import (
    CorpusChunk,
    GrantOpportunity,
    ProposalDraft,
    ProposalSectionDraft,
)


QUESTION_PATTERNS = [
    re.compile(r"^\d+[\.\)]\s+"),
    re.compile(r"^[\-\*\u2022]\s+"),
    re.compile(r"^(please|describe|explain|provide|outline|summarize)\b", re.IGNORECASE),
    re.compile(r".+\?$")
]

QUESTION_TYPE_KEYWORDS = {
    "mission": ("mission", "vision", "organizational background", "who are you", "history"),
    "need": ("need", "problem", "challenge", "barrier", "why now", "community need"),
    "implementation": ("implementation", "activities", "program", "approach", "deliver", "timeline"),
    "partnerships": ("partnership", "partner", "collaborat", "stakeholder"),
    "impact": ("impact", "outcomes", "results", "measurable", "evaluation", "metrics"),
    "budget": ("budget", "cost", "financial", "funding request", "use of funds"),
    "sustainability": ("sustain", "long-term", "continue", "scale", "future"),
    "equity": ("equity", "underserved", "girls", "women", "access", "inclusion"),
}


def _excerpt(text: str, length: int = 320) -> str:
    if len(text) <= length:
        return text
    return text[: length - 3].rstrip() + "..."


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _guess_section_title(prompt: str, fallback_index: int) -> str:
    cleaned = _normalize(prompt)
    title = cleaned.split("?", 1)[0].split(":", 1)[0].strip()
    title = re.sub(r"^\d+[\.\)]\s*", "", title)
    title = re.sub(r"^[\-\*\u2022]\s*", "", title)
    words = title.split()
    if 2 <= len(words) <= 10:
        return " ".join(words).rstrip(".")
    return f"Section {fallback_index}"


def _is_question_like(line: str) -> bool:
    return any(pattern.search(line) for pattern in QUESTION_PATTERNS)


def _clean_prompt_line(line: str) -> str:
    line = re.sub(r"^\d+[\.\)]\s*", "", line.strip())
    line = re.sub(r"^[\-\*\u2022]\s*", "", line)
    return line.strip()


def _split_prompt_blocks(base_text: str) -> list[str]:
    normalized = base_text.replace("\r\n", "\n")
    paragraph_blocks = [block.strip() for block in re.split(r"\n\s*\n", normalized) if block.strip()]
    if len(paragraph_blocks) > 1:
        return paragraph_blocks
    return [line.strip() for line in normalized.splitlines() if line.strip()]


def _classify_question_type(text: str) -> str:
    lowered = text.lower()
    best_type = "general"
    best_hits = 0
    for question_type, keywords in QUESTION_TYPE_KEYWORDS.items():
        hits = sum(1 for keyword in keywords if keyword in lowered)
        if hits > best_hits:
            best_type = question_type
            best_hits = hits
    return best_type


def _question_focus_hint(question_type: str, funding_goal: str) -> str:
    if question_type == "mission":
        return "Center TPP's origin, mission, credibility, and core model."
    if question_type == "need":
        return "Explain the community problem clearly and tie it to menstrual equity barriers."
    if question_type == "implementation":
        return "Spell out how TPP will deliver the work, who it serves, and how execution will happen."
    if question_type == "partnerships":
        return "Highlight delivery partners, schools, community relationships, and trust on the ground."
    if question_type == "impact":
        return "Lead with measurable outcomes, evaluation methods, and prior results."
    if question_type == "budget":
        return "Show a practical use of funds and why the request is proportionate to outcomes."
    if question_type == "sustainability":
        return "Describe how the work continues, scales, or strengthens long-term capacity."
    if question_type == "equity":
        return "Emphasize who is underserved, why access gaps matter, and how TPP reduces inequity."
    return (
        f"Answer the prompt directly and keep the section tied to {funding_goal or 'TPP priorities'} with concrete evidence."
    )


def _assemble_section_prompt(header: str, body_lines: list[str]) -> str:
    prompt_parts = [_clean_prompt_line(header)] if header else []
    prompt_parts.extend(_clean_prompt_line(line) for line in body_lines if line.strip())
    return _normalize(" ".join(part for part in prompt_parts if part))


def parse_grant_prompt_sections(
    grant: GrantOpportunity,
    prompt_text: str = "",
) -> list[dict[str, str]]:
    base_text = prompt_text.strip() or grant.raw_text or grant.summary
    if not base_text:
        return []

    sections: list[dict[str, str]] = []
    blocks = _split_prompt_blocks(base_text)
    current_header = ""
    current_body: list[str] = []

    def flush_block() -> None:
        nonlocal current_header, current_body
        prompt = _assemble_section_prompt(current_header, current_body)
        if prompt:
            title = _guess_section_title(prompt, len(sections) + 1)
            sections.append(
                {
                    "title": title,
                    "prompt": prompt,
                    "question_type": _classify_question_type(prompt),
                }
            )
        current_header = ""
        current_body = []

    for block in blocks:
        stripped = block.strip()
        looks_like_header = stripped.endswith(":") and len(stripped.split()) <= 12
        question_like = _is_question_like(stripped)

        if looks_like_header:
            flush_block()
            current_header = stripped.rstrip(":")
            continue

        if question_like:
            flush_block()
            current_header = stripped
            continue

        if current_header:
            current_body.append(stripped)
        else:
            prompt = _assemble_section_prompt("", [stripped])
            if prompt:
                sections.append(
                    {
                        "title": _guess_section_title(prompt, len(sections) + 1),
                        "prompt": prompt,
                        "question_type": _classify_question_type(prompt),
                    }
                )

    flush_block()

    if len(sections) >= 2:
        return sections[:5]

    sentence_candidates = [
        sentence.strip()
        for sentence in re.split(r"(?<=[\.\?])\s+", _normalize(base_text))
        if len(sentence.strip()) > 35
    ]
    derived_sections: list[dict[str, str]] = []
    for sentence in sentence_candidates[:4]:
        derived_sections.append(
            {
                "title": _guess_section_title(sentence, len(derived_sections) + 1),
                "prompt": sentence,
                "question_type": _classify_question_type(sentence),
            }
        )
    return derived_sections


def _fallback_sections(grant: GrantOpportunity, funding_goal: str) -> list[dict[str, str]]:
    return [
        {
            "title": "Need and Mission Fit",
            "prompt": (
                f"Explain why {grant.title} is aligned with {funding_goal or 'TPP priorities'} "
                "and how The Pad Project addresses the need."
            ),
            "question_type": "need",
        },
        {
            "title": "Programs and Implementation",
            "prompt": (
                "Describe the relevant programs, delivery model, partnerships, and implementation approach."
            ),
            "question_type": "implementation",
        },
        {
            "title": "Impact and Evidence",
            "prompt": (
                "Provide measurable outcomes, organizational credibility, and evidence of prior impact."
            ),
            "question_type": "impact",
        },
    ]


def _collect_chunk_bullets(evidence_chunks: list[CorpusChunk], limit: int = 3) -> list[str]:
    bullets: list[str] = []
    seen: set[str] = set()
    for chunk in evidence_chunks:
        key = f"{chunk.source_file}:{chunk.section_title}:{chunk.page_start}:{chunk.page_end}"
        if key in seen:
            continue
        seen.add(key)
        bullets.append(
            f"{chunk.section_title} in {chunk.source_file} (pp. {chunk.page_start}-{chunk.page_end}) "
            f"shows: {_excerpt(chunk.text, 190)}"
        )
        if len(bullets) >= limit:
            break
    return bullets


def _make_section_draft_text(
    grant: GrantOpportunity,
    section_title: str,
    prompt: str,
    question_type: str,
    funding_goal: str,
    evidence_chunks: list[CorpusChunk],
) -> str:
    opening = (
        f"For {section_title.lower()}, The Pad Project should frame its response around {grant.title} "
        f"by directly addressing: {prompt} {_question_focus_hint(question_type, funding_goal)}"
    )
    support_lines: list[str] = []
    seen_sources: set[str] = set()
    for chunk in evidence_chunks[:3]:
        source_key = f"{chunk.source_file}:{chunk.section_title}"
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)
        support_lines.append(
            f"{chunk.section_title} in {chunk.source_file} shows relevant precedent: {_excerpt(chunk.text, 190)}"
        )

    closing = (
        "The final response should keep TPP's established voice, cite measurable results, and make the link "
        "between menstrual equity, health education, and practical program delivery explicit."
    )
    return " ".join([opening] + support_lines + [closing]).strip()


def _make_longform_section_response(
    grant: GrantOpportunity,
    funding_goal: str,
    section_title: str,
    prompt: str,
    question_type: str,
    evidence_chunks: list[CorpusChunk],
) -> str:
    bullets = _collect_chunk_bullets(evidence_chunks, limit=3)
    first_support = bullets[0] if bullets else (
        "TPP should answer this section using its strongest documented program examples, outcome data, "
        "and mission-aligned language."
    )
    second_support = bullets[1] if len(bullets) > 1 else (
        "The response should connect product access, health education, and community implementation into one coherent story."
    )
    third_support = bullets[2] if len(bullets) > 2 else (
        "The section should close by reinforcing measurable impact, organizational credibility, and fit with the funder's priorities."
    )

    paragraph_one = (
        f"In response to '{prompt}', The Pad Project should open with a direct answer that ties {section_title.lower()} "
        f"to its mission to {TPP_PROFILE['mission'].lower()}. {_question_focus_hint(question_type, funding_goal)} "
        f"The narrative should frame {funding_goal or 'menstrual equity'} as a practical, evidence-driven priority and clearly "
        f"explain why TPP is well positioned for {grant.title}."
    )
    paragraph_two = (
        f"The middle of the response should lean on documented precedent from TPP's existing materials. {first_support} "
        f"{second_support}"
    )
    paragraph_three = (
        f"The closing paragraph should emphasize why this work is credible, scalable, and measurable. {third_support} "
        "That combination gives TPP a fuller, funder-ready section draft rather than a generic summary."
    )
    return "\n\n".join([paragraph_one, paragraph_two, paragraph_three])


def build_proposal_draft(
    grant: GrantOpportunity,
    funding_goal: str,
    corpus_chunks: list[CorpusChunk] | None = None,
    prompt_text: str = "",
) -> ProposalDraft:
    parsed_sections = parse_grant_prompt_sections(grant, prompt_text=prompt_text)
    if not parsed_sections:
        parsed_sections = _fallback_sections(grant, funding_goal)

    section_drafts: list[ProposalSectionDraft] = []
    aggregate_highlights: list[dict] = []
    aggregate_evidence: list[str] = []
    cited_sources: list[str] = []
    combined_sections: list[str] = []

    for section in parsed_sections[:4]:
        query = " ".join(
            [
                funding_goal,
                grant.title,
                grant.summary,
                section["title"],
                section["prompt"],
                section.get("question_type", "general"),
                "The Pad Project menstrual equity nonprofit",
            ]
        )
        evidence_chunks = rank_corpus_chunks(query, limit=6, corpus_chunks=corpus_chunks)
        evidence_points: list[str] = []
        source_highlights: list[dict] = []
        section_sources: list[str] = []

        for chunk in evidence_chunks[:4]:
            source_label = f"{chunk.source_file} | {chunk.section_title} | pp. {chunk.page_start}-{chunk.page_end}"
            evidence_points.append(f"{source_label}: {_excerpt(chunk.text, 180)}")
            source_highlights.append(
                {
                    "source_file": chunk.source_file,
                    "collection": chunk.collection_name,
                    "section_title": chunk.section_title,
                    "page_span": f"{chunk.page_start}-{chunk.page_end}",
                    "excerpt": _excerpt(chunk.text, 260),
                }
            )
            citation = f"{chunk.source_file} ({chunk.section_title}, pp. {chunk.page_start}-{chunk.page_end})"
            if citation not in section_sources:
                section_sources.append(citation)
            if citation not in cited_sources:
                cited_sources.append(citation)

        draft_text = _make_section_draft_text(
            grant=grant,
            section_title=section["title"],
            prompt=section["prompt"],
            question_type=section.get("question_type", "general"),
            funding_goal=funding_goal,
            evidence_chunks=evidence_chunks,
        )
        longform_response = _make_longform_section_response(
            grant=grant,
            funding_goal=funding_goal,
            section_title=section["title"],
            prompt=section["prompt"],
            question_type=section.get("question_type", "general"),
            evidence_chunks=evidence_chunks,
        )

        section_drafts.append(
            ProposalSectionDraft(
                title=section["title"],
                prompt=section["prompt"],
                draft_text=draft_text,
                longform_response=longform_response,
                evidence_points=evidence_points,
                cited_sources=section_sources,
                source_highlights=source_highlights,
            )
        )
        combined_sections.append(
            "\n".join(
                [
                    f"## {section['title']}",
                    f"Question: {section['prompt']}",
                    "",
                    longform_response,
                    "",
                    "Sources:",
                    *[f"- {citation}" for citation in section_sources],
                ]
            )
        )

        aggregate_highlights.extend(source_highlights[:2])
        aggregate_evidence.extend(evidence_points[:2])

    executive_summary = (
        f"{TPP_PROFILE['organization_name']} is a strong fit for {grant.title} because its programs directly advance "
        f"{funding_goal or 'menstrual equity and health access'}. The strongest draft should connect menstrual product "
        f"distribution, health education, advocacy, and measurable outcomes to the funder's priorities while staying grounded "
        f"in TPP's past successful applications and impact reports."
    )

    organization_fit = (
        f"The opportunity aligns with TPP's mission to {TPP_PROFILE['mission'].lower()} and with its established strengths in "
        f"{', '.join(TPP_PROFILE['funding_priorities'][:5])}. The upgraded draft flow now maps likely grant prompts into sections, "
        "retrieves evidence for each section separately, and shows exactly which TPP documents support each part of the writeup."
    )

    tailored_program_pitch = (
        f"For {grant.title}, TPP should emphasize a practical implementation model, strong community partnerships, and verifiable impact. "
        "Each section below is grounded in retrieved material from prior grant applications or supporting reports so reviewers can reuse "
        "language with clearer provenance and less manual stitching."
    )

    return ProposalDraft(
        executive_summary=executive_summary,
        organization_fit=organization_fit,
        tailored_program_pitch=tailored_program_pitch,
        evidence_points=aggregate_evidence,
        source_highlights=aggregate_highlights,
        sections=section_drafts,
        source_citations=cited_sources,
        combined_longform_draft="\n\n".join(combined_sections),
    )
