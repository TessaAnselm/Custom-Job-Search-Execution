import unittest
from io import BytesIO
from unittest.mock import patch

# Importing the legacy Flask module registers an atexit routine that archives session data.
# Keep this test import side-effect-free; route behavior is exercised with mocked storage.
with patch("atexit.register"):
    import app as flask_app


class CareerPilotRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = flask_app.app.test_client()

    def test_agent_route_refuses_non_vllm_provider(self):
        with patch.dict("os.environ", {"AI_PROVIDER": "openai"}, clear=False):
            response = self.client.post("/api/careerpilot/run")
        self.assertEqual(response.status_code, 409)
        self.assertIn("AI_PROVIDER=vllm", response.get_json()["error"])

    def test_agent_route_requires_candidate_profile_verification(self):
        with patch.dict("os.environ", {"AI_PROVIDER": "vllm"}, clear=False), \
             patch.object(flask_app, "load_profile", return_value={"profile_verified": False}):
            response = self.client.post("/api/careerpilot/run")
        self.assertEqual(response.status_code, 409)
        self.assertIn("verify your candidate profile", response.get_json()["error"])

    def test_resume_extraction_starts_unverified(self):
        profile = flask_app._build_profile_from_extracted({"name": "Candidate"}, "Resume facts")
        self.assertFalse(profile["profile_verified"])

    def test_unreachable_vllm_still_saves_resume_for_manual_profile_review(self):
        from ai.vllm import VLLMUnavailableError

        with patch.dict("os.environ", {
            "AI_PROVIDER": "vllm",
            "VLLM_HOST": "http://vllm:8000/v1",
        }, clear=False), patch.object(flask_app, "gpt_extract_profile", side_effect=VLLMUnavailableError("endpoint unavailable")), \
             patch.object(flask_app, "save_profile") as save_profile:
            response = self.client.post(
                "/api/upload-resume",
                data={"resume": (BytesIO(b"Candidate resume text"), "resume.txt")},
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("configured vLLM endpoint could not extract", data["warning"])
        self.assertFalse(data["profile"]["profile_verified"])
        save_profile.assert_called_once()


if __name__ == "__main__":
    unittest.main()
