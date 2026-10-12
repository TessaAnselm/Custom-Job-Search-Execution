"""Small process-local inference counters for the live demo."""

from __future__ import annotations

import re
import threading


_LOCK = threading.Lock()
_INFERENCE = {"requests": 0, "succeeded": 0, "failed": 0, "latency_ms_total": 0.0}
_METRIC_NAMES = {
    "vllm:time_to_first_token_seconds_count",
    "vllm:time_to_first_token_seconds_sum",
    "vllm:e2e_request_latency_seconds_count",
    "vllm:e2e_request_latency_seconds_sum",
    "vllm:request_generation_tokens_sum",
    "vllm:request_inference_time_seconds_sum",
}


def record_inference_request(model: str, success: bool, latency_ms: float) -> None:
    with _LOCK:
        _INFERENCE["requests"] += 1
        _INFERENCE["succeeded" if success else "failed"] += 1
        _INFERENCE["latency_ms_total"] += latency_ms


def inference_snapshot() -> dict:
    with _LOCK:
        snapshot = dict(_INFERENCE)
    count = snapshot["requests"]
    snapshot["latency_ms_average"] = snapshot["latency_ms_total"] / count if count else None
    return snapshot


def inference_delta(before: dict, after: dict) -> dict:
    delta = {
        key: after.get(key, 0) - before.get(key, 0)
        for key in ("requests", "succeeded", "failed", "latency_ms_total")
    }
    count = delta["requests"]
    delta["latency_ms_average"] = delta["latency_ms_total"] / count if count else None
    return delta


def fetch_vllm_metrics(config) -> dict:
    """Read selected server-aggregate Prometheus series; return unavailable on failure."""
    try:
        import httpx

        root = config.base_url.rstrip("/")
        if root.endswith("/v1"):
            root = root[:-3]
        url = root + "/metrics"
        headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
        with httpx.Client(timeout=config.timeout_seconds) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
        series: dict[str, dict[str, float]] = {}
        for line in response.text.splitlines():
            if not line or line.startswith("#"):
                continue
            match = re.match(r'([^\s{]+)(?:\{([^}]*)\})?\s+([-+0-9.eE]+)', line)
            if not match:
                continue
            name, labels, raw_value = match.groups()
            if name not in _METRIC_NAMES:
                continue
            model_match = re.search(r'(?:^|,)model_name="([^"]+)"', labels or "")
            model_name = model_match.group(1) if model_match else "unspecified"
            series.setdefault(name, {})[model_name] = (
                series.setdefault(name, {}).get(model_name, 0.0) + float(raw_value)
            )
        return {"available": True, "url": url, "series": series}
    except Exception as exc:
        return {
            "available": False,
            "error_type": type(exc).__name__,
            "series": {},
        }


def prometheus_delta(before: dict, after: dict, model_name: str) -> dict:
    """Compute interval deltas for the named model from aggregate server counters."""
    result = {"available": False, "source": "vLLM /metrics server aggregates", "model": model_name}
    if not before.get("available") or not after.get("available"):
        result["reason"] = "Prometheus metrics were not reachable for both snapshots."
        return result

    deltas = {}
    for name in _METRIC_NAMES:
        start = before.get("series", {}).get(name, {}).get(model_name)
        finish = after.get("series", {}).get(name, {}).get(model_name)
        if start is not None and finish is not None and finish >= start:
            deltas[name] = finish - start

    result.update({"available": True, "series_delta": deltas})
    ttft_count = deltas.get("vllm:time_to_first_token_seconds_count", 0)
    ttft_sum = deltas.get("vllm:time_to_first_token_seconds_sum", 0)
    latency_count = deltas.get("vllm:e2e_request_latency_seconds_count", 0)
    latency_sum = deltas.get("vllm:e2e_request_latency_seconds_sum", 0)
    generated = deltas.get("vllm:request_generation_tokens_sum")
    inference_time = deltas.get("vllm:request_inference_time_seconds_sum")
    result["time_to_first_token_ms_average"] = (
        round(ttft_sum / ttft_count * 1000, 2) if ttft_count else None
    )
    result["request_latency_ms_average"] = (
        round(latency_sum / latency_count * 1000, 2) if latency_count else None
    )
    result["generated_tokens"] = int(generated) if generated is not None else None
    result["aggregate_tokens_per_second"] = (
        round(generated / inference_time, 2) if generated is not None and inference_time and inference_time > 0 else None
    )
    return result


def prometheus_current(snapshot: dict, model_name: str) -> dict:
    """Summarize cumulative server metrics without mislabeling them as per-run values."""
    result = {
        "available": bool(snapshot.get("available")),
        "source": "vLLM /metrics; aggregate for this model since the server started",
        "model": model_name,
        "time_to_first_token_ms_average": None,
        "request_latency_ms_average": None,
        "generated_tokens_total": None,
        "aggregate_tokens_per_second": None,
    }
    if not snapshot.get("available"):
        result["reason"] = "Prometheus metrics endpoint was not reachable."
        return result
    series = snapshot.get("series", {})
    def value(metric):
        return series.get(metric, {}).get(model_name)

    ttft_count, ttft_sum = value("vllm:time_to_first_token_seconds_count"), value("vllm:time_to_first_token_seconds_sum")
    latency_count, latency_sum = value("vllm:e2e_request_latency_seconds_count"), value("vllm:e2e_request_latency_seconds_sum")
    generated, inference_time = value("vllm:request_generation_tokens_sum"), value("vllm:request_inference_time_seconds_sum")
    if ttft_count and ttft_sum is not None:
        result["time_to_first_token_ms_average"] = round(ttft_sum / ttft_count * 1000, 2)
    if latency_count and latency_sum is not None:
        result["request_latency_ms_average"] = round(latency_sum / latency_count * 1000, 2)
    if generated is not None:
        result["generated_tokens_total"] = int(generated)
    if generated is not None and inference_time and inference_time > 0:
        result["aggregate_tokens_per_second"] = round(generated / inference_time, 2)
    return result
