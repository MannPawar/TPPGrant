from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

from tpp_grants.config import MAX_RESULTS, MINIMUM_PASSING_SCORE, TPP_PROFILE
from tpp_grants.models import GrantOpportunity, SourceSearchRecord


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> set[str]:
    return set(TOKEN_PATTERN.findall(text.lower()))


def compact(text: str) -> str:
    return " ".join(text.split())


def parse_money_value(text: str) -> float:
    digits = re.sub(r"[^0-9.]", "", text.replace(",", ""))
    if not digits:
        return 0.0
    try:
        return float(digits)
    except ValueError:
        return 0.0


def _safe_text(node: BeautifulSoup | None) -> str:
    if not node:
        return ""
    return compact(node.get_text(" ", strip=True))


def generate_search_queries(funding_goal: str) -> list[str]:
    base_goal = compact(funding_goal or "menstrual equity grants")
    queries = [
        "",
        base_goal,
        f"{base_goal} women girls health education nonprofit",
        f"{base_goal} menstrual equity period poverty nonprofit",
        f"{base_goal} community health education 501c3",
        "menstrual health nonprofit grants",
        "girls education women health nonprofit grants",
        "global health menstrual equity grants",
    ]
    unique: list[str] = []
    for query in queries:
        if query not in unique:
            unique.append(query)
    return unique


@dataclass(slots=True)
class SearchContext:
    session: requests.Session
    funding_goal: str


class BaseSourceAdapter:
    source_name = ""
    base_url = ""

    def search(self, context: SearchContext, query: str) -> tuple[list[GrantOpportunity], SourceSearchRecord]:
        raise NotImplementedError


class SimplerGrantsAdapter(BaseSourceAdapter):
    source_name = "Simpler.Grants.gov"
    base_url = "https://simpler.grants.gov/search"

    def search(self, context: SearchContext, query: str) -> tuple[list[GrantOpportunity], SourceSearchRecord]:
        search_url = f"{self.base_url}?status=forecasted&status=posted"
        if query:
            search_url += f"&query={quote_plus(query)}"
        response = context.session.get(search_url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        results: list[GrantOpportunity] = []
        seen_links: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            title = _safe_text(anchor)
            if not href.startswith("/opportunity/") or not title or href in seen_links:
                continue
            seen_links.add(href)
            detail_url = urljoin(self.base_url, href)
            detail = self._fetch_detail(context, detail_url)
            if detail:
                detail.search_url = search_url
                results.append(detail)
            if len(results) >= 8:
                break

        return results, SourceSearchRecord(
            source_name=self.source_name,
            query=query or "broad open + forecasted scan",
            attempted=True,
            result_count=len(results),
        )

    def _fetch_detail(self, context: SearchContext, detail_url: str) -> GrantOpportunity | None:
        detail_response = context.session.get(detail_url, timeout=30)
        detail_response.raise_for_status()
        soup = BeautifulSoup(detail_response.text, "html.parser")

        title = _safe_text(soup.find("h1"))
        if not title:
            for heading in soup.find_all("h2"):
                heading_text = _safe_text(heading)
                if heading_text and heading_text not in {
                    "Description",
                    "Eligibility",
                    "Grantor contact information",
                    "Documents",
                    "Award",
                }:
                    title = heading_text
                    break
        if not title:
            return None
        page_text = compact(soup.get_text(" ", strip=True))
        description_bits = page_text.split("Description", 1)
        summary = description_bits[-1][:1200] if len(description_bits) > 1 else page_text[:900]

        deadline_match = re.search(r"Closing:\s*(.+?)Application process", page_text)
        eligibility_match = re.search(r"Eligible applicants\s*(.+?)Grantor contact information", page_text)
        money_values = re.findall(r"\$[\d,]+", page_text)
        money_choice = max(money_values, key=parse_money_value) if money_values else "Unknown"

        return GrantOpportunity(
            title=title,
            source_name=self.source_name,
            source_url=detail_url,
            search_url=self.base_url,
            summary=compact(summary)[:900],
            deadline=compact(deadline_match.group(1)) if deadline_match else "Unknown",
            funding_amount=money_choice,
            eligibility=compact(eligibility_match.group(1))[:350] if eligibility_match else "Unknown",
            status="Open or forecasted",
            raw_text=page_text[:4000],
        )


class GrantPortalAdapter(BaseSourceAdapter):
    source_name = "The Grant Portal"
    base_url = "https://www.thegrantportal.com/grants-for-nonprofits"

    def search(self, context: SearchContext, query: str) -> tuple[list[GrantOpportunity], SourceSearchRecord]:
        results: list[GrantOpportunity] = []
        seen_links: set[str] = set()
        for page in range(1, 3):
            search_url = f"{self.base_url}?sort_by=updated_at&filter=0&page={page}"
            if query:
                search_url += f"&search={quote_plus(query)}"
            response = context.session.get(search_url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            for anchor in soup.find_all("a", href=True):
                href = anchor["href"]
                if "/grant-details/" not in href or href in seen_links:
                    continue
                seen_links.add(href)
                detail = self._fetch_detail(context, href)
                if detail:
                    detail.search_url = search_url
                    results.append(detail)
                if len(results) >= 8:
                    break
            if len(results) >= 8:
                break

        return results, SourceSearchRecord(
            source_name=self.source_name,
            query=query or "broad nonprofit grants scan",
            attempted=True,
            result_count=len(results),
            notes="Grant provider URLs may remain behind a subscription wall.",
        )

    def _fetch_detail(self, context: SearchContext, detail_url: str) -> GrantOpportunity | None:
        response = context.session.get(detail_url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        page_text = compact(soup.get_text(" ", strip=True))

        title = ""
        meta_title = soup.find("meta", attrs={"property": "og:title"})
        if meta_title and meta_title.get("content"):
            title = compact(meta_title["content"])
        if not title:
            for heading in soup.find_all("h1"):
                heading_text = _safe_text(heading)
                if heading_text and len(heading_text) < 180:
                    title = heading_text
                    break
        if not title:
            title = _safe_text(soup.find("title"))
        if not title:
            return None

        meta_description = soup.find("meta", attrs={"name": "description"})
        summary = compact(meta_description.get("content", "")) if meta_description else ""
        if not summary:
            body_h1 = soup.find_all("h1")
            if len(body_h1) > 1:
                summary = _safe_text(body_h1[1])
        if not summary:
            summary = page_text[:700]

        money_values = re.findall(r"\$[\d,]+", page_text)
        money_choice = "Unknown"
        if money_values:
            money_choice = max(money_values, key=parse_money_value)

        deadline_match = re.search(r"\b(Ongoing|Deadline:? [A-Za-z0-9, ]+|Proposal Deadlines [A-Za-z0-9, ]+)\b", page_text)
        eligibility = "501(c)(3) nonprofit" if "501(c)(3)" in page_text else "Nonprofit"

        return GrantOpportunity(
            title=compact(title),
            source_name=self.source_name,
            source_url=detail_url,
            search_url=self.base_url,
            summary=summary,
            deadline=deadline_match.group(1) if deadline_match else "Unknown",
            funding_amount=money_choice,
            eligibility=eligibility,
            status="Listed",
            raw_text=page_text[:3500],
        )


class ZeffyAdapter(BaseSourceAdapter):
    source_name = "Zeffy Grant Finder"
    base_url = "https://www.zeffy.com/home/grants-for-nonprofits"

    def search(self, context: SearchContext, query: str) -> tuple[list[GrantOpportunity], SourceSearchRecord]:
        notes = (
            "Zeffy exposes a public grant-finder landing page, but individual grant matches are loaded dynamically "
            "and may block automated requests."
        )
        try:
            response = context.session.get(self.base_url, timeout=30)
            response.raise_for_status()
            page_text = compact(BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True))
            if any(term in page_text.lower() for term in ("grant finder", "find 2026 grants")):
                notes += " Source kept in the search rotation for manual follow-up."
        except requests.RequestException as exc:
            notes += f" Request blocked during verification: {exc.__class__.__name__}."
        return [], SourceSearchRecord(
            source_name=self.source_name,
            query=query or "broad Zeffy grant finder check",
            attempted=True,
            result_count=0,
            notes=notes,
        )


def rank_opportunity(opportunity: GrantOpportunity, funding_goal: str) -> GrantOpportunity:
    haystack = " ".join(
        [
            opportunity.title,
            opportunity.summary,
            opportunity.eligibility,
            opportunity.location,
            opportunity.raw_text,
        ]
    ).lower()
    haystack_tokens = tokenize(haystack)

    goal_tokens = tokenize(funding_goal)
    mission_tokens = tokenize(" ".join(TPP_PROFILE["funding_priorities"] + TPP_PROFILE["keywords"]))
    eligibility_tokens = tokenize(" ".join(TPP_PROFILE["eligibility_terms"]))

    goal_overlap = len(goal_tokens.intersection(haystack_tokens))
    mission_overlap = len(mission_tokens.intersection(haystack_tokens))

    goal_score = min(10.0, goal_overlap * 2.2 + (2.0 if goal_overlap >= 2 else 0.0))
    mission_score = min(10.0, mission_overlap * 0.9)
    applicant_fit_score = 8.0 if "nonprofit" in haystack else 3.5
    if "501(c)(3)" in haystack:
        applicant_fit_score += 1.0

    deadline_score = 6.0 if opportunity.deadline != "Unknown" else 3.0
    if opportunity.deadline.lower() == "ongoing":
        deadline_score = 8.5
    if "closed" in opportunity.status.lower():
        deadline_score = 0.5

    funding_value = parse_money_value(opportunity.funding_amount)
    funding_score = 5.0
    if funding_value >= 50000:
        funding_score = 8.5
    elif funding_value >= 10000:
        funding_score = 7.0
    elif funding_value > 0:
        funding_score = 6.0

    evidence_score = 3.5
    for phrase in (
        "women",
        "girls",
        "health",
        "education",
        "equity",
        "community",
        "stigma",
    ):
        if phrase in haystack:
            evidence_score += 0.8
    evidence_score = min(10.0, evidence_score)

    weighted_total = (
        goal_score * 0.28
        + mission_score * 0.24
        + applicant_fit_score * 0.16
        + deadline_score * 0.12
        + funding_score * 0.08
        + evidence_score * 0.12
    )
    total_score = round(min(10.0, weighted_total), 2)

    notes: list[str] = []
    if goal_score >= 7:
        notes.append("Strong topical overlap with the funding goal.")
    if applicant_fit_score >= 8:
        notes.append("Nonprofit eligibility language looks promising for TPP.")
    if deadline_score >= 8:
        notes.append("Deadline handling appears favorable or ongoing.")
    if evidence_score >= 7:
        notes.append("Opportunity language aligns with TPP's health, education, and equity framing.")

    opportunity.scoring_breakdown = {
        "goal_alignment": round(goal_score, 2),
        "mission_alignment": round(mission_score, 2),
        "applicant_fit": round(applicant_fit_score, 2),
        "deadline_quality": round(deadline_score, 2),
        "funding_level": round(funding_score, 2),
        "evidence_alignment": round(evidence_score, 2),
    }
    opportunity.ranking_notes = notes
    opportunity.total_score = total_score
    return opportunity


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        }
    )
    return session


def _adapter_instances() -> Iterable[BaseSourceAdapter]:
    yield SimplerGrantsAdapter()
    yield GrantPortalAdapter()
    yield ZeffyAdapter()


def search_and_rank_grants(funding_goal: str) -> tuple[list[GrantOpportunity], list[SourceSearchRecord]]:
    context = SearchContext(session=build_session(), funding_goal=funding_goal)
    opportunities: OrderedDict[str, GrantOpportunity] = OrderedDict()
    source_records: list[SourceSearchRecord] = []

    for query in generate_search_queries(funding_goal):
        for adapter in _adapter_instances():
            try:
                results, record = adapter.search(context, query)
            except requests.RequestException as exc:
                results = []
                record = SourceSearchRecord(
                    source_name=adapter.source_name,
                    query=query,
                    attempted=True,
                    result_count=0,
                    notes=f"Search failed: {exc.__class__.__name__}.",
                )
            source_records.append(record)
            for opportunity in results:
                rank_opportunity(opportunity, funding_goal)
                current = opportunities.get(opportunity.dedupe_key())
                if current is None or opportunity.total_score > current.total_score:
                    opportunities[opportunity.dedupe_key()] = opportunity

    ranked = sorted(opportunities.values(), key=lambda item: item.total_score, reverse=True)
    filtered = [item for item in ranked if item.total_score > MINIMUM_PASSING_SCORE]
    return filtered[:MAX_RESULTS], source_records
