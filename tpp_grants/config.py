from __future__ import annotations

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
TPP_ROOT = BASE_DIR / "W&M MSBA x TPP"
GRANT_APPS_DIR = TPP_ROOT / "Grant Apps"
SUPPORTING_DOCS_DIR = TPP_ROOT / "Impact Reports and Decks"

MINIMUM_PASSING_SCORE = 6.0
MAX_RESULTS = 12

TPP_PROFILE = {
    "organization_name": "The Pad Project",
    "mission": (
        "Expand access to menstrual care products, combat period stigma, and champion "
        "menstrual equity for all."
    ),
    "funding_priorities": [
        "menstrual health",
        "menstrual equity",
        "period poverty",
        "girls education",
        "women and girls",
        "health access",
        "youth empowerment",
        "global health",
        "reproductive health",
        "community education",
        "product distribution",
        "advocacy",
        "social enterprise",
    ],
    "program_footprint": [
        "United States",
        "India",
        "Guatemala",
        "global",
        "international",
    ],
    "eligibility_terms": [
        "nonprofit",
        "501(c)(3)",
        "education",
        "health",
        "community-based",
    ],
    "keywords": [
        "menstrual",
        "period",
        "women",
        "girls",
        "health",
        "equity",
        "education",
        "nonprofit",
        "global",
        "advocacy",
        "distribution",
        "youth",
    ],
}

GRANT_SOURCES = [
    {
        "name": "Simpler.Grants.gov",
        "base_url": "https://simpler.grants.gov/search",
        "enabled": True,
    },
    {
        "name": "The Grant Portal",
        "base_url": "https://www.thegrantportal.com/grants-for-nonprofits",
        "enabled": True,
    },
    {
        "name": "Zeffy Grant Finder",
        "base_url": "https://www.zeffy.com/home/grants-for-nonprofits",
        "enabled": True,
    },
]
