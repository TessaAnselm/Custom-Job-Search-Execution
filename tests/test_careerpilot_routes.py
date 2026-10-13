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

    def test_vllm_check_requires_selected_provider(self):
        with patch.dict("os.environ", {"AI_PROVIDER": "openai"}, clear=False):
            response = self.client.post("/api/vllm/check")
        self.assertEqual(response.status_code, 409)
        self.assertIn("AI_PROVIDER=vllm", response.get_json()["error"])

    def test_vllm_check_returns_only_safe_connection_details(self):
        with patch.dict("os.environ", {"AI_PROVIDER": "vllm"}, clear=False), \
             patch("ai.vllm.check_connection", return_value={
                 "model": "Qwen/Qwen3-4B", "latency_ms": 123.4,
                 "response": "vLLM connection OK", "base_url": "http://private-service:8000/v1",
             }):
            response = self.client.post("/api/vllm/check")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "ok": True, "model": "Qwen/Qwen3-4B", "latency_ms": 123.4,
            "message": "vLLM connection OK",
        })

    def test_vllm_check_error_does_not_return_exception_details(self):
        with patch.dict("os.environ", {"AI_PROVIDER": "vllm"}, clear=False), \
             patch("ai.vllm.check_connection", side_effect=TimeoutError("secret token leaked")):
            response = self.client.post("/api/vllm/check")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret token leaked", response.get_data(as_text=True))

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

    def test_unconfigured_extractor_warns_instead_of_silently_skipping_fields(self):
        with patch.dict("os.environ", {"AI_PROVIDER": "openai", "OPENAI_API_KEY": ""}, clear=False), \
             patch.object(flask_app, "gpt_extract_profile") as extract, \
             patch.object(flask_app, "save_profile"):
            response = self.client.post(
                "/api/upload-resume",
                data={"resume": (BytesIO(b"Candidate resume text"), "resume.txt")},
                content_type="multipart/form-data",
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("No AI profile extractor is configured", data["warning"])
        self.assertEqual(data["profile"]["base_resume"].strip(), "Candidate resume text")
        extract.assert_not_called()

    def test_resume_upload_maps_extracted_facts_into_profile_fields(self):
        extracted = {
            "name": "Candidate", "experience_years": 5, "skills": ["Python", "Kubernetes"],
            "target_titles": ["Platform Engineer"], "salary_minimum": 0,
        }
        with patch.dict("os.environ", {"AI_PROVIDER": "vllm", "VLLM_HOST": "http://localhost:8000/v1"}, clear=False), \
             patch.object(flask_app, "gpt_extract_profile", return_value=extracted), \
             patch.object(flask_app, "save_profile"):
            response = self.client.post(
                "/api/upload-resume",
                data={"resume": (BytesIO(b"Candidate resume text"), "resume.txt")},
                content_type="multipart/form-data",
            )

        profile = response.get_json()["profile"]
        self.assertEqual(profile["name"], "Candidate")
        self.assertEqual(profile["experience_years"], 5)
        self.assertEqual(profile["skills"], ["Python", "Kubernetes"])
        self.assertEqual(profile["target_titles"], ["Platform Engineer"])
        self.assertEqual(profile["salary"]["minimum"], 0)

    def test_resume_upload_normalizes_common_name_and_experience_aliases(self):
        with patch.dict("os.environ", {"AI_PROVIDER": "vllm", "VLLM_HOST": "http://localhost:8000/v1"}, clear=False), \
             patch.object(flask_app, "gpt_extract_profile", return_value={
                 "full_name": "Candidate Name", "years_of_experience": "8+ years",
             }), patch.object(flask_app, "save_profile"):
            response = self.client.post(
                "/api/upload-resume",
                data={"resume": (BytesIO(b"Candidate resume text"), "resume.txt")},
                content_type="multipart/form-data",
            )

        profile = response.get_json()["profile"]
        self.assertEqual(profile["name"], "Candidate Name")
        self.assertEqual(profile["experience_years"], 8)

    def test_profile_extractor_parses_qwen_thinking_and_markdown_wrappers(self):
        response_text = (
            "<think>I'll organize the candidate details first.</think>\n"
            "```json\n{\"name\": \"Candidate Name\", \"experience_years\": 8}\n```"
        )
        with patch.dict("os.environ", {"AI_PROVIDER": "vllm"}, clear=False), \
             patch("ai.client.complete_sync", return_value=response_text) as complete:
            extracted = flask_app.gpt_extract_profile("Candidate resume text")

        self.assertEqual(extracted, {"name": "Candidate Name", "experience_years": 8})
        complete.assert_called_once()
        # 800, not a larger budget: once /no_think is sent (below), Qwen3 produces no
        # reasoning tokens, so a small budget is reliable AND fast — measured live,
        # 800+/no_think succeeds in ~10s where 3000 without it still failed at 93s.
        self.assertEqual(complete.call_args.kwargs["max_tokens"], 800)
        prompt_sent = complete.call_args.args[0]
        self.assertTrue(prompt_sent.rstrip().endswith("/no_think"))

    def test_profile_extractor_does_not_send_no_think_to_other_providers(self):
        response_text = '{"name": "Candidate Name", "experience_years": 8}'
        with patch.dict("os.environ", {"AI_PROVIDER": "openai"}, clear=False), \
             patch("ai.client.complete_sync", return_value=response_text) as complete:
            flask_app.gpt_extract_profile("Candidate resume text")

        prompt_sent = complete.call_args.args[0]
        self.assertNotIn("/no_think", prompt_sent)

    def test_docx_text_is_extracted_without_an_additional_package(self):
        import zipfile

        document = BytesIO()
        with zipfile.ZipFile(document, "w") as archive:
            archive.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:body><w:p><w:r><w:t>Candidate Name</w:t></w:r></w:p></w:body></w:document>',
            )
        document.seek(0)
        upload = BytesIO(document.read())
        upload.filename = "resume.docx"
        self.assertEqual(flask_app.extract_text_from_upload(upload), "Candidate Name")


if __name__ == "__main__":
    unittest.main()
