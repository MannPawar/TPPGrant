from __future__ import annotations

from tpp_grants.config import TPP_PROFILE
from tpp_grants.corpus import rank_corpus_chunks
from tpp_grants.models import CorpusChunk, GrantOpportunity, ProposalDraft


def _excerpt(text: str, length: int = 320) -> str:
    if len(text) <= length:
        return text
    return text[: length - 3].rstrip() + "..."


def build_proposal_draft(
    grant: GrantOpportunity,
    funding_goal: str,
    corpus_chunks: list[CorpusChunk] | None = None,
) -> ProposalDraft:
    query = " ".join(
        [
            funding_goal,
            grant.title,
            grant.summary,
            grant.eligibility,
            "The Pad Project menstrual equity nonprofit",
        ]
    )
    chunks = rank_corpus_chunks(query, limit=8, corpus_chunks=corpus_chunks)

    grant_app_chunks = [chunk for chunk in chunks if chunk.collection_name == "Grant Apps"][:4]
    support_chunks = [chunk for chunk in chunks if chunk.collection_name != "Grant Apps"][:4]
    narrative_basis = grant_app_chunks[:2] or chunks[:2]
    evidence_basis = support_chunks[:3] or chunks[2:5]

    executive_summary = (
        f"{TPP_PROFILE['organization_name']} is a strong fit for {grant.title} because its "
        f"programs directly advance {funding_goal or 'menstrual equity and health access'}. "
        f"The organization combines menstrual product distribution, health education, and advocacy "
        f"to reduce stigma and expand access for women and girls across U.S. and international programs. "
        f"This application should emphasize measurable reach, community partnerships, and a scalable model "
        f"for sustained impact."
    )

    organization_fit = (
        f"The opportunity appears aligned with TPP's mission to {TPP_PROFILE['mission'].lower()} "
        f"and with its existing strengths in {', '.join(TPP_PROFILE['funding_priorities'][:5])}. "
        f"The writeup should explicitly connect the grant's stated focus areas to TPP's product distribution, "
        f"education, and advocacy model while confirming nonprofit eligibility and deadline requirements."
    )

    tailored_program_pitch = (
        f"For this grant, frame the proposed work around {funding_goal or 'high-impact menstrual health programming'} "
        f"with clear outputs, a target population, implementation partners, and measurable outcomes. "
        f"Use TPP's past application language for organizational voice, then reinforce the case with concrete impact data "
        f"and program examples drawn from the supporting materials."
    )

    evidence_points = []
    for chunk in evidence_basis:
        evidence_points.append(f"{chunk.source_file}: {_excerpt(chunk.text, 220)}")

    source_highlights = []
    for chunk in narrative_basis + evidence_basis:
        source_highlights.append(
            {
                "source_file": chunk.source_file,
                "collection": chunk.collection_name,
                "excerpt": _excerpt(chunk.text, 280),
            }
        )

    return ProposalDraft(
        executive_summary=executive_summary,
        organization_fit=organization_fit,
        tailored_program_pitch=tailored_program_pitch,
        evidence_points=evidence_points,
        source_highlights=source_highlights,
    )
