import unittest

from tpp_grants.config import MINIMUM_PASSING_SCORE
from tpp_grants.models import GrantOpportunity
from tpp_grants.search import rank_opportunity


class RankingSmokeTest(unittest.TestCase):
    def test_nonprofit_health_grant_scores_above_threshold(self):
        opportunity = GrantOpportunity(
            title="Women and Girls Health Education Grant",
            source_name="Test Source",
            source_url="https://example.com/grant",
            search_url="https://example.com/search",
            summary=(
                "Funds nonprofit programs supporting women, girls, education, community health, "
                "and equitable access to essential care."
            ),
            deadline="Ongoing",
            funding_amount="$100,000",
            eligibility="501(c)(3) nonprofit organizations",
            raw_text="menstrual equity women girls health education nonprofit community",
        )

        ranked = rank_opportunity(opportunity, "menstrual health education for girls")
        self.assertGreater(ranked.total_score, MINIMUM_PASSING_SCORE)


if __name__ == "__main__":
    unittest.main()
