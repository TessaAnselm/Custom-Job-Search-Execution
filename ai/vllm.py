"""Configuration and helpers for the workshop's OpenAI-compatible vLLM API."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from urllib.parse import urlsplit


DEFAULT_VLLM_HOST = "http://vllm:8000/v1"
DEFAULT_MODEL_NAME = "Qwen/Qwen3-4B"


class VLLMConfigurationError(ValueError):
    """Raised when the vLLM environment configuration is invalid."""


class VLLMUnavailableError(ConnectionError):
    """Raised when a request cannot reach or complete against vLLM."""


class VLLMRequestError(RuntimeError):
    """Raised when vLLM returns an API error for a request."""


@dataclass(frozen=True)
class VLLMConfig:
    base_url: str
    model: str
    api_key: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> "VLLMConfig":
        base_url = os.getenv("VLLM_HOST", DEFAULT_VLLM_HOST).strip().rstrip("/")
        model = os.getenv("MODEL_NAME", DEFAULT_MODEL_NAME).strip()
        api_key = os.getenv("VLLM_API_KEY", "")
        try:
            timeout_seconds = float(os.getenv("VLLM_TIMEOUT_SECONDS", "30"))
        except ValueError as exc:
            raise VLLMConfigurationError("VLLM_TIMEOUT_SECONDS must be a number") from exc

        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise VLLMConfigurationError("VLLM_HOST must be an http(s) URL")
        if parsed.username or parsed.password:
            raise VLLMConfigurationError("Do not place credentials in VLLM_HOST; use VLLM_API_KEY")
        if not model:
            raise VLLMConfigurationError("MODEL_NAME must not be empty")
        if timeout_seconds <= 0:
            raise VLLMConfigurationError("VLLM_TIMEOUT_SECONDS must be greater than zero")

        return cls(base_url, model, api_key, timeout_seconds)

    def client_options(self) -> dict:
        return {
            "api_key": self.api_key,
            "base_url": self.base_url,
            "timeout": self.timeout_seconds,
        }


def complete_sync(prompt: str, max_tokens: int = 800) -> str:
    """Run a non-streaming completion against the configured vLLM model."""
    from openai import APIConnectionError, APIError, APITimeoutError, OpenAI

    config = VLLMConfig.from_env()
    from ai.telemetry import record_inference_request
    client = OpenAI(**config.client_options())
    started_at = time.perf_counter()
    success = False
    try:
        response = client.chat.completions.create(
            model=config.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        success = True
        return response.choices[0].message.content or ""
    except (APIConnectionError, APITimeoutError) as exc:
        raise VLLMUnavailableError(
            f"Could not complete a request against the configured vLLM endpoint ({config.base_url}). "
            "Check that this runtime can reach the endpoint and that the service is ready."
        ) from exc
    except APIError as exc:
        raise VLLMRequestError(
            f"The configured vLLM endpoint returned an API error ({type(exc).__name__}). "
            "Check the model name, endpoint configuration, and API key."
        ) from exc
    finally:
        record_inference_request(config.model, success, (time.perf_counter() - started_at) * 1000)
        client.close()


async def complete_async(prompt: str, max_tokens: int = 600) -> str:
    """Run an asynchronous non-streaming completion against vLLM."""
    from openai import APIConnectionError, APIError, APITimeoutError, AsyncOpenAI

    config = VLLMConfig.from_env()
    from ai.telemetry import record_inference_request
    client = AsyncOpenAI(**config.client_options())
    started_at = time.perf_counter()
    success = False
    try:
        response = await client.chat.completions.create(
            model=config.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        success = True
        return response.choices[0].message.content or ""
    except (APIConnectionError, APITimeoutError) as exc:
        raise VLLMUnavailableError(
            f"Could not complete a request against the configured vLLM endpoint ({config.base_url}). "
            "Check that this runtime can reach the endpoint and that the service is ready."
        ) from exc
    except APIError as exc:
        raise VLLMRequestError(
            f"The configured vLLM endpoint returned an API error ({type(exc).__name__}). "
            "Check the model name, endpoint configuration, and API key."
        ) from exc
    finally:
        record_inference_request(config.model, success, (time.perf_counter() - started_at) * 1000)
        await client.close()


def check_connection(prompt: str = "Reply with exactly: vLLM connection OK") -> dict:
    """Make one small live request and return measured request latency."""
    config = VLLMConfig.from_env()
    started_at = time.perf_counter()
    response = complete_sync(prompt, max_tokens=16)
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    return {
        "ok": True,
        "model": config.model,
        "base_url": config.base_url,
        "latency_ms": elapsed_ms,
        "response": response,
    }
