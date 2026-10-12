import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from ai import client as unified_client
from ai.vllm import (
    DEFAULT_MODEL_NAME,
    DEFAULT_VLLM_HOST,
    VLLMConfig,
    VLLMConfigurationError,
    VLLMUnavailableError,
)


class VLLMConfigTests(unittest.TestCase):
    def test_workshop_defaults_are_internal_and_configurable(self):
        with patch.dict(os.environ, {}, clear=True):
            config = VLLMConfig.from_env()
        self.assertEqual(config.base_url, DEFAULT_VLLM_HOST)
        self.assertEqual(config.model, DEFAULT_MODEL_NAME)
        self.assertEqual(config.api_key, "")

        with patch.dict(os.environ, {
            "VLLM_HOST": "https://inference.example/v1/",
            "MODEL_NAME": "Qwen/Qwen3-4B",
            "VLLM_API_KEY": "test-secret",
            "VLLM_TIMEOUT_SECONDS": "12.5",
        }, clear=True):
            config = VLLMConfig.from_env()
        self.assertEqual(config.base_url, "https://inference.example/v1")
        self.assertEqual(config.model, "Qwen/Qwen3-4B")
        self.assertEqual(config.api_key, "test-secret")
        self.assertEqual(config.timeout_seconds, 12.5)

    def test_invalid_endpoint_or_timeout_is_rejected(self):
        for env in (
            {"VLLM_HOST": "vllm:8000/v1"},
            {"VLLM_TIMEOUT_SECONDS": "not-a-number"},
            {"VLLM_TIMEOUT_SECONDS": "0"},
            {"VLLM_HOST": "http://user:secret@vllm:8000/v1"},
        ):
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True):
                with self.assertRaises(VLLMConfigurationError):
                    VLLMConfig.from_env()


class VLLMClientTests(unittest.TestCase):
    def test_connectivity_probe_reports_measured_mock_response(self):
        with patch.dict(os.environ, {
            "VLLM_HOST": "http://workshop-vllm:8000/v1",
            "MODEL_NAME": "Qwen/Qwen3-4B",
        }, clear=True), patch("ai.vllm.complete_sync", return_value="vLLM connection OK"):
            from ai.vllm import check_connection
            result = check_connection()

        self.assertTrue(result["ok"])
        self.assertEqual(result["model"], "Qwen/Qwen3-4B")
        self.assertEqual(result["base_url"], "http://workshop-vllm:8000/v1")
        self.assertGreaterEqual(result["latency_ms"], 0)
        self.assertEqual(result["response"], "vLLM connection OK")

    def test_sync_provider_uses_configured_model_and_endpoint(self):
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="mock answer"))])
        client = MagicMock()
        client.chat.completions.create.return_value = response
        with patch.dict(os.environ, {
            "AI_PROVIDER": "vllm",
            "VLLM_HOST": "http://workshop-vllm:8000/v1",
            "MODEL_NAME": "Qwen/Qwen3-4B",
            "VLLM_API_KEY": "test-secret",
        }, clear=True), patch("openai.OpenAI", return_value=client) as openai:
            self.assertEqual(unified_client.complete_sync("hello", max_tokens=23), "mock answer")

        openai.assert_called_once_with(
            api_key="test-secret", base_url="http://workshop-vllm:8000/v1", timeout=30.0
        )
        client.chat.completions.create.assert_called_once_with(
            model="Qwen/Qwen3-4B", messages=[{"role": "user", "content": "hello"}], max_tokens=23
        )
        client.close.assert_called_once()

    def test_async_provider_uses_configured_model_and_endpoint(self):
        async def run():
            response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="mock async"))])
            client = MagicMock()
            client.chat.completions.create = AsyncMock(return_value=response)
            client.close = AsyncMock()
            with patch.dict(os.environ, {
                "AI_PROVIDER": "vllm",
                "VLLM_HOST": "http://workshop-vllm:8000/v1",
                "MODEL_NAME": "Qwen/Qwen3-4B",
                "VLLM_API_KEY": "test-secret",
            }, clear=True), patch("openai.AsyncOpenAI", return_value=client) as openai:
                self.assertEqual(await unified_client.complete_async("hello", max_tokens=19), "mock async")
            openai.assert_called_once_with(
                api_key="test-secret", base_url="http://workshop-vllm:8000/v1", timeout=30.0
            )
            client.chat.completions.create.assert_awaited_once_with(
                model="Qwen/Qwen3-4B", messages=[{"role": "user", "content": "hello"}], max_tokens=19
            )
            client.close.assert_awaited_once()

        import asyncio
        asyncio.run(run())

    def test_sync_unavailable_endpoint_raises_sanitized_error(self):
        from openai import APIConnectionError

        client = MagicMock()
        client.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())
        with patch.dict(os.environ, {"AI_PROVIDER": "vllm", "VLLM_HOST": "http://inside-workshop:8000/v1"}, clear=True), \
             patch("openai.OpenAI", return_value=client):
            with self.assertRaises(VLLMUnavailableError) as raised:
                unified_client.complete_sync("hello")
        self.assertIn("inside-workshop", str(raised.exception))
        self.assertNotIn("test-secret", str(raised.exception))

    def test_existing_provider_dispatch_is_preserved(self):
        with patch.dict(os.environ, {"AI_PROVIDER": "openai", "OPENAI_API_KEY": "existing"}, clear=True), \
             patch("openai.OpenAI") as openai:
            openai.return_value.chat.completions.create.return_value = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="existing provider"))]
            )
            self.assertEqual(unified_client.complete_sync("hello"), "existing provider")
        openai.assert_called_once_with(api_key="existing")


if __name__ == "__main__":
    unittest.main()
