import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from careerpilot import agent as agent_module
from careerpilot.agent import _verified_profile_facts, create_careerpilot_agent


class CareerPilotToolTests(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict(os.environ, {
            "VLLM_HOST": "http://workshop-vllm:8000/v1",
            "MODEL_NAME": "Qwen/Qwen3-4B",
            "VLLM_API_KEY": "",
        }, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_search_tool_reuses_existing_ranked_results_and_profile_facts(self):
        profile = {
            "profile_verified": True,
            "name": "Demo Candidate",
            "skills": ["Python", "Kubernetes"],
            "base_resume": "Private source resume",
        }
        row = {
            "_row_id": "job-1",
            "Company": "Example Co",
            "Job Title": "Security Engineer",
            "Job URL": "https://example.test/job/1",
            "Match Score": "88",
            "Why It Fits": "Existing score explanation",
            "_agent_context": {
                "job": {
                    "id": "job-1",
                    "title": "Security Engineer",
                    "company": "Example Co",
                    "description": "Python and Kubernetes required.",
                },
                "breakdown": {"skills_match": 100.0},
            },
        }

        async def search():
            return [row]

        agent, context = create_careerpilot_agent(search, lambda: profile)
        result = agent.tool.search_and_match_jobs()

        self.assertEqual(result["status"], "success")
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["matches"][0]["score"], 88)
        self.assertEqual(payload["matches"][0]["score_breakdown"]["skills_match"], 100.0)
        self.assertEqual(payload["candidate_profile_facts"]["skills"], ["Python", "Kubernetes"])
        self.assertIn("job-1", context["jobs"])

    def test_agent_tools_require_profile_verification(self):
        async def search():
            self.fail("Search must not run before profile verification")

        agent, _ = create_careerpilot_agent(search, lambda: {"profile_verified": False})
        result = agent.tool.search_and_match_jobs()

        self.assertEqual(result["status"], "error")
        self.assertIn("verify their profile", result["content"][0]["text"])

    def test_package_tool_returns_review_only_drafts_from_existing_generators(self):
        profile = {"profile_verified": True, "skills": ["Python"], "base_resume": "Python engineer"}
        row = {
            "_row_id": "job-1",
            "Company": "Example Co",
            "Job Title": "Security Engineer",
            "Job URL": "https://example.test/job/1",
            "Match Score": "88",
            "Why It Fits": "Strong skills overlap",
            "_agent_context": {"job": {
                "id": "job-1", "title": "Security Engineer", "company": "Example Co",
                "description": "Python required.",
            }, "breakdown": {"skills_match": 100.0}},
        }

        async def search():
            return [row]

        agent, _ = create_careerpilot_agent(search, lambda: profile)
        agent.tool.search_and_match_jobs()
        with patch("ai.resume_tailor.ResumeTailor.tailor", new=AsyncMock(return_value="resume draft")), \
             patch("ai.cover_note.CoverNoteGenerator.generate", new=AsyncMock(return_value="cover draft")):
            result = agent.tool.prepare_application_package(job_id="job-1")

        self.assertEqual(result["status"], "success")
        package = json.loads(result["content"][0]["text"])
        self.assertEqual(package["resume_draft"], "resume draft")
        self.assertEqual(package["cover_note_draft"], "cover draft")
        self.assertEqual(package["approval_status"], "Review")
        self.assertTrue(package["requires_human_review"])

    def test_verified_profile_passes_only_profile_fields_used_by_career_tools(self):
        facts = _verified_profile_facts({
            "name": "Candidate",
            "skills": ["Python"],
            "base_resume": "Source resume",
            "unrelated_secret": "should not be forwarded",
        })
        self.assertEqual(facts["skills"], ["Python"])
        self.assertNotIn("unrelated_secret", facts)


class RunCareerPilotFallbackTests(unittest.IsolatedAsyncioTestCase):
    """Regression test for the live finding: Qwen3-4B sometimes finalizes its
    answer without calling prepare_application_package. run_careerpilot must
    still produce a reviewable package deterministically in that case."""

    async def test_fallback_generates_package_when_model_skips_the_tool(self):
        context = {
            "jobs": {
                "job-1": {
                    "row": {"_row_id": "job-1", "Match Score": "88", "Why It Fits": "Strong overlap"},
                    "job": {
                        "id": "job-1", "title": "Security Engineer", "company": "Example Co",
                        "description": "Python required.",
                    },
                    "breakdown": {"skills_match": 100.0},
                },
            },
            "profile": {"skills": ["Python"], "base_resume": "Python engineer"},
            "package": None,
        }

        class StubResult:
            structured_output = SimpleNamespace(model_dump=lambda mode="json": {"summary": "ok", "assessments": []})
            stop_reason = "end_turn"
            metrics = SimpleNamespace(get_summary=lambda: {})

        class StubAgent:
            async def invoke_async(self, _prompt):
                # Simulates the model producing a final answer without ever
                # calling prepare_application_package — context["package"]
                # stays None, exactly as observed against the live endpoint.
                return StubResult()

        async def search():
            return []

        with patch.object(agent_module, "create_careerpilot_agent", return_value=(StubAgent(), context)), \
             patch("ai.resume_tailor.ResumeTailor.tailor", new=AsyncMock(return_value="resume draft")), \
             patch("ai.cover_note.CoverNoteGenerator.generate", new=AsyncMock(return_value="cover draft")):
            result = await agent_module.run_careerpilot(search, lambda: {"profile_verified": True})

        package = result["application_package"]
        self.assertIsNotNone(package)
        self.assertEqual(package["job_id"], "job-1")
        self.assertEqual(package["resume_draft"], "resume draft")
        self.assertEqual(package["cover_note_draft"], "cover draft")
        self.assertTrue(package["requires_human_review"])

    async def test_fallback_is_a_noop_when_the_model_already_produced_a_package(self):
        existing_package = {"job_id": "job-1", "resume_draft": "already here"}
        context = {
            "jobs": {"job-1": {"row": {"Match Score": "88"}, "job": {}, "breakdown": {}}},
            "profile": {},
            "package": existing_package,
        }

        class StubResult:
            structured_output = SimpleNamespace(model_dump=lambda mode="json": {"summary": "ok", "assessments": []})
            stop_reason = "end_turn"
            metrics = SimpleNamespace(get_summary=lambda: {})

        class StubAgent:
            async def invoke_async(self, _prompt):
                return StubResult()

        async def search():
            return []

        with patch.object(agent_module, "create_careerpilot_agent", return_value=(StubAgent(), context)), \
             patch("ai.resume_tailor.ResumeTailor.tailor", new=AsyncMock(side_effect=AssertionError("should not run"))):
            result = await agent_module.run_careerpilot(search, lambda: {"profile_verified": True})

        self.assertIs(result["application_package"], existing_package)


if __name__ == "__main__":
    unittest.main()
