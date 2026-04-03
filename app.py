from __future__ import annotations

from dataclasses import asdict

import streamlit as st

from tpp_grants.config import GRANT_SOURCES, MINIMUM_PASSING_SCORE
from tpp_grants.corpus import load_uploaded_corpus
from tpp_grants.drafting import build_proposal_draft
from tpp_grants.search import search_and_rank_grants


st.set_page_config(
    page_title="TPP Grants System",
    layout="wide",
)


@st.cache_data(show_spinner=False, ttl=3600)
def run_search(funding_goal: str):
    return search_and_rank_grants(funding_goal)


@st.cache_data(show_spinner=False, ttl=3600)
def generate_draft_payload(opportunity_payload: dict, funding_goal: str) -> dict:
    from tpp_grants.models import GrantOpportunity

    opportunity = GrantOpportunity(**opportunity_payload)
    draft = build_proposal_draft(opportunity, funding_goal)
    return asdict(draft)


@st.cache_data(show_spinner=False, ttl=3600)
def build_uploaded_corpus_payload(
    grant_app_files: tuple[tuple[str, bytes], ...],
    supporting_files: tuple[tuple[str, bytes], ...],
):
    return load_uploaded_corpus(list(grant_app_files), list(supporting_files))


def render_search_audit(source_records: list) -> None:
    st.subheader("Search audit")
    columns = st.columns(3)
    for idx, record in enumerate(source_records):
        with columns[idx % 3]:
            st.markdown(f"**{record.source_name}**")
            st.caption(record.query)
            st.write(f"{record.result_count} result(s)")
            if record.notes:
                st.caption(record.notes)


def render_opportunity_card(index: int, opportunity, funding_goal: str) -> None:
    with st.container(border=True):
        left, right = st.columns([5, 1])
        with left:
            st.caption(opportunity.source_name)
            st.markdown(f"### {opportunity.title}")
        with right:
            st.metric("Score", opportunity.total_score)

        st.write(opportunity.summary)

        meta1, meta2, meta3 = st.columns(3)
        meta1.metric("Deadline", opportunity.deadline)
        meta2.metric("Funding", opportunity.funding_amount)
        meta3.metric("Eligibility", opportunity.eligibility)

        if opportunity.ranking_notes:
            st.markdown("**Why it ranked well**")
            for note in opportunity.ranking_notes:
                st.write(f"- {note}")

        st.link_button("Open source page", opportunity.source_url, use_container_width=True)
        if st.button("Generate writeup", key=f"draft-{index}", use_container_width=True):
            st.session_state["selected_index"] = index
            st.session_state["selected_goal"] = funding_goal


def render_draft(selected_opportunity, funding_goal: str, custom_corpus=None) -> None:
    st.subheader("Proposal workspace")
    payload = {
        "title": selected_opportunity.title,
        "source_name": selected_opportunity.source_name,
        "source_url": selected_opportunity.source_url,
        "search_url": selected_opportunity.search_url,
        "summary": selected_opportunity.summary,
        "deadline": selected_opportunity.deadline,
        "funding_amount": selected_opportunity.funding_amount,
        "eligibility": selected_opportunity.eligibility,
        "location": selected_opportunity.location,
        "status": selected_opportunity.status,
        "opportunity_id": selected_opportunity.opportunity_id,
        "raw_text": selected_opportunity.raw_text,
        "ranking_notes": selected_opportunity.ranking_notes,
        "scoring_breakdown": selected_opportunity.scoring_breakdown,
        "total_score": selected_opportunity.total_score,
    }

    with st.spinner("Grounding the draft with TPP grant applications and impact materials..."):
        if custom_corpus is None:
            draft = generate_draft_payload(payload, funding_goal)
        else:
            from tpp_grants.models import GrantOpportunity

            opportunity = GrantOpportunity(**payload)
            draft = asdict(build_proposal_draft(opportunity, funding_goal, corpus_chunks=custom_corpus))

    st.markdown("**Executive summary**")
    st.write(draft["executive_summary"])

    st.markdown("**Organizational fit**")
    st.write(draft["organization_fit"])

    st.markdown("**Tailored program pitch**")
    st.write(draft["tailored_program_pitch"])

    st.markdown("**Evidence points**")
    for point in draft["evidence_points"]:
        st.write(f"- {point}")

    st.markdown("**Grounding excerpts**")
    for highlight in draft["source_highlights"]:
        with st.container(border=True):
            st.markdown(f"**{highlight['source_file']}**")
            st.caption(highlight["collection"])
            st.write(highlight["excerpt"])


st.title("The Pad Project Grant Discovery and Proposal Workspace")
st.write(
    f"Runs a broad search first, ranks opportunities against TPP's mission and program fit, "
    f"and only returns grants with scores greater than {MINIMUM_PASSING_SCORE}."
)

with st.sidebar:
    st.header("Sources")
    for source in GRANT_SOURCES:
        st.markdown(f"- [{source['name']}]({source['base_url']})")
    st.caption("Zeffy is included in the rotation, but live automated requests may be blocked by that site.")
    st.divider()
    st.subheader("Private source docs")
    st.caption(
        "If the app is deployed without bundled TPP PDFs, upload them here so writeups can still be grounded "
        "in the real grant applications and supporting reports."
    )
    uploaded_grant_apps = st.file_uploader(
        "Grant Apps PDFs",
        type=["pdf"],
        accept_multiple_files=True,
    )
    uploaded_supporting_docs = st.file_uploader(
        "Impact Reports / Decks PDFs",
        type=["pdf"],
        accept_multiple_files=True,
    )

default_goal = st.session_state.get(
    "funding_goal",
    "menstrual health education for girls in underserved communities",
)
funding_goal = st.text_area(
    "Current funding goal",
    value=default_goal,
    height=120,
    help="Describe what TPP wants to fund so the app can search broadly and rank rigorously.",
)

search_clicked = st.button("Run grant search", type="primary")

if search_clicked:
    st.session_state["funding_goal"] = funding_goal
    st.session_state["selected_goal"] = funding_goal
    st.session_state["selected_index"] = None

goal_for_run = st.session_state.get("funding_goal", funding_goal).strip()

if goal_for_run:
    with st.spinner("Searching sources, ranking matches, and filtering to scores above 6..."):
        opportunities, source_records = run_search(goal_for_run)

    render_search_audit(source_records)

    results_col, draft_col = st.columns([1.35, 1])

    with results_col:
        st.subheader("Ranked grants")
        if not opportunities:
            st.warning("No grants scored above the threshold on this run. Try broadening the funding goal.")
        for index, opportunity in enumerate(opportunities):
            render_opportunity_card(index, opportunity, goal_for_run)

    with draft_col:
        selected_index = st.session_state.get("selected_index")
        uploaded_corpus = None
        if uploaded_grant_apps or uploaded_supporting_docs:
            grant_app_payload = tuple((file.name, file.getvalue()) for file in uploaded_grant_apps)
            supporting_payload = tuple((file.name, file.getvalue()) for file in uploaded_supporting_docs)
            uploaded_corpus = build_uploaded_corpus_payload(grant_app_payload, supporting_payload)
        if selected_index is not None and 0 <= selected_index < len(opportunities):
            render_draft(opportunities[selected_index], goal_for_run, custom_corpus=uploaded_corpus)
        else:
            st.subheader("Proposal workspace")
            st.info(
                "Select a ranked grant to generate a grounded writeup using both the Grant Apps "
                "and Impact Reports and Decks folders, or upload those PDFs in the sidebar."
            )
