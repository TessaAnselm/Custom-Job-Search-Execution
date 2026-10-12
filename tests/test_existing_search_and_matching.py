import unittest
from unittest.mock import patch

from scoring.scorer import JobScorer
from scrapers.base import Job
from utils.search_config import build_search_config


class ExistingSearchRegressionTests(unittest.TestCase):
    def test_search_config_uses_profile_queries_and_city_before_remote(self):
        profile = {
            "target_titles": ["Security Engineer", "security engineer", "Cloud Security Engineer"],
            "skills": ["Python", "Kubernetes"],
            "location": {"preferred": ["San Francisco", "Remote"]},
        }

        config = build_search_config(profile)

        self.assertEqual(
            config["queries"],
            ["Security Engineer", "Cloud Security Engineer", "Python", "Kubernetes"],
        )
        self.assertEqual(config["locations"], ["San Francisco", "Remote"])
        self.assertEqual(config["location"], "San Francisco")
        self.assertIn("security", config["tags"])

    def test_job_ids_remain_stable_and_serializable(self):
        first = Job(
            title="Security Engineer",
            company="Example",
            location="Remote",
            url="https://jobs.example/role/1",
            source="example",
        )
        second = Job(
            title="Different title",
            company="Different company",
            location="New York",
            url="https://jobs.example/role/1",
            source="another-source",
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.to_dict()["url"], "https://jobs.example/role/1")


class ExistingMatchingRegressionTests(unittest.TestCase):
    def test_fast_score_preserves_weighted_signals_without_inference(self):
        profile = {
            "target_titles": ["Senior Security Engineer"],
            "skills": ["Python", "Kubernetes"],
            "salary": {"minimum": 100000, "target": 150000},
            "location": {"preferred": ["Remote"], "hard_no": []},
            "industries": {"preferred": ["cybersecurity"], "avoid": []},
            "scoring_weights": {
                "title_match": 0.30,
                "skills_match": 0.25,
                "salary_match": 0.20,
                "location_match": 0.15,
                "industry_match": 0.10,
            },
        }
        job = {
            "title": "Senior Security Engineer",
            "company": "Example Security",
            "location": "Remote",
            "salary": "$120,000 - $150,000",
            "description": "Python, Kubernetes, and cybersecurity operations.",
        }

        with patch("ai.client.complete_async") as complete:
            result = JobScorer(profile).score_fast(job)

        self.assertEqual(result["score"], 100)
        self.assertEqual(set(result["breakdown"]), {
            "title_match", "skills_match", "salary_match", "location_match", "industry_match"
        })
        complete.assert_not_called()

    def test_explicit_location_exclusion_and_missing_salary_are_handled(self):
        profile = {
            "target_titles": ["Engineer"],
            "skills": ["Python"],
            "salary": {"minimum": 100000, "target": 150000},
            "location": {"preferred": ["Remote"], "hard_no": ["Requires relocation"]},
            "industries": {"preferred": [], "avoid": []},
        }
        scorer = JobScorer(profile)

        result = scorer.score_fast({
            "title": "Engineer",
            "company": "Example",
            "location": "Requires relocation",
            "salary": "Not listed",
            "description": "Python required",
        })

        self.assertEqual(result["breakdown"]["location_match"], 0.0)
        self.assertEqual(result["breakdown"]["salary_match"], 50.0)


if __name__ == "__main__":
    unittest.main()
