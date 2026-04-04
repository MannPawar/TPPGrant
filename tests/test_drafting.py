import unittest

from tpp_grants.drafting import build_proposal_draft, parse_grant_prompt_sections
from tpp_grants.models import CorpusChunk, GrantOpportunity


class DraftingUpgradeTests(unittest.TestCase):
    def test_parse_grant_prompt_sections_splits_structured_prompt(self):
        grant = GrantOpportunity(
            title="Test Grant",
            source_name="Test",
            source_url="https://example.com/grant",
            search_url="https://example.com/search",
            summary="Please describe your mission. Please explain your impact.",
        )

        sections = parse_grant_prompt_sections(
            grant,
            prompt_text=(
                "1. Describe your mission and organizational background.\n"
                "2. Explain your implementation plan and partnerships.\n"
                "3. Provide measurable outcomes and evaluation methods."
            ),
        )

        self.assertGreaterEqual(len(sections), 3)
        self.assertEqual(sections[0]["question_type"], "mission")
        self.assertEqual(sections[2]["question_type"], "impact")

    def test_parse_grant_prompt_sections_keeps_header_bodies_together(self):
        grant = GrantOpportunity(
            title="Test Grant",
            source_name="Test",
            source_url="https://example.com/grant",
            search_url="https://example.com/search",
            summary="Application prompt",
        )

        sections = parse_grant_prompt_sections(
            grant,
            prompt_text=(
                "Organization Background:\n"
                "Describe your mission, history, and the communities you serve.\n\n"
                "Evaluation Plan:\n"
                "Explain how outcomes will be measured and reported."
            ),
        )

        self.assertEqual(len(sections), 2)
        self.assertIn("mission", sections[0]["question_type"])
        self.assertIn("impact", sections[1]["question_type"])

    def test_build_proposal_draft_returns_section_citations(self):
        grant = GrantOpportunity(
            title="Women and Girls Health Grant",
            source_name="Test",
            source_url="https://example.com/grant",
            search_url="https://example.com/search",
            summary="Please describe your organizational background and expected outcomes.",
        )
        corpus = [
            CorpusChunk(
                text="The Pad Project expands menstrual health access through education, product distribution, and advocacy.",
                source_file="Aerie Foundation Grant Application 2025 (1).pdf",
                collection_name="Grant Apps",
                priority=1.15,
                section_title="Organizational Background",
                page_start=1,
                page_end=2,
            ),
            CorpusChunk(
                text="Since 2020, the organization has distributed millions of menstrual products and served communities across the United States.",
                source_file="Copy of Jan - Jun 2025 Impact Data.pdf",
                collection_name="Impact Reports and Decks",
                priority=1.0,
                section_title="Impact Data",
                page_start=2,
                page_end=3,
            ),
        ]

        draft = build_proposal_draft(
            grant,
            "menstrual health education for girls",
            corpus_chunks=corpus,
            prompt_text=(
                "Describe your organizational background.\n"
                "Provide measurable outcomes."
            ),
        )

        self.assertTrue(draft.sections)
        self.assertGreaterEqual(len(draft.sections), 2)
        self.assertTrue(draft.source_citations)
        self.assertIn("Aerie Foundation Grant Application 2025 (1).pdf", " ".join(draft.source_citations))
        self.assertTrue(draft.combined_longform_draft)
        self.assertTrue(draft.sections[0].longform_response)


if __name__ == "__main__":
    unittest.main()
