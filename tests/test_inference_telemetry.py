import unittest
from unittest.mock import MagicMock, patch

from ai.telemetry import inference_delta, prometheus_current, fetch_vllm_metrics


class InferenceTelemetryTests(unittest.TestCase):
    def test_inference_delta_reports_only_observed_process_counter_change(self):
        before = {"requests": 8, "succeeded": 7, "failed": 1, "latency_ms_total": 800.0}
        after = {"requests": 11, "succeeded": 9, "failed": 2, "latency_ms_total": 1400.0}

        delta = inference_delta(before, after)

        self.assertEqual(delta["requests"], 3)
        self.assertEqual(delta["succeeded"], 2)
        self.assertEqual(delta["failed"], 1)
        self.assertEqual(delta["latency_ms_average"], 200.0)

    def test_prometheus_current_labels_server_values_as_aggregate(self):
        snapshot = {
            "available": True,
            "series": {
                "vllm:time_to_first_token_seconds_count": {"Qwen/Qwen3-4B": 10.0},
                "vllm:time_to_first_token_seconds_sum": {"Qwen/Qwen3-4B": 2.0},
                "vllm:e2e_request_latency_seconds_count": {"Qwen/Qwen3-4B": 5.0},
                "vllm:e2e_request_latency_seconds_sum": {"Qwen/Qwen3-4B": 12.5},
                "vllm:request_generation_tokens_sum": {"Qwen/Qwen3-4B": 200.0},
                "vllm:request_inference_time_seconds_sum": {"Qwen/Qwen3-4B": 10.0},
            },
        }

        result = prometheus_current(snapshot, "Qwen/Qwen3-4B")

        self.assertIn("aggregate", result["source"])
        self.assertEqual(result["time_to_first_token_ms_average"], 200.0)
        self.assertEqual(result["request_latency_ms_average"], 2500.0)
        self.assertEqual(result["generated_tokens_total"], 200)
        self.assertEqual(result["aggregate_tokens_per_second"], 20.0)

    def test_metrics_fetch_parses_selected_series_and_uses_secret_header(self):
        response = MagicMock()
        response.text = (
            '# HELP vllm:time_to_first_token_seconds_count count\n'
            'vllm:time_to_first_token_seconds_count{model_name="Qwen/Qwen3-4B",engine="0"} 3\n'
            'vllm:unrelated_metric{model_name="Qwen/Qwen3-4B"} 999\n'
        )
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.return_value = response
        config = type("Config", (), {
            "base_url": "http://vllm:8000/v1", "api_key": "secret", "timeout_seconds": 3
        })()
        with patch("httpx.Client", return_value=client):
            result = fetch_vllm_metrics(config)

        self.assertTrue(result["available"])
        self.assertEqual(result["url"], "http://vllm:8000/metrics")
        self.assertEqual(result["series"]["vllm:time_to_first_token_seconds_count"]["Qwen/Qwen3-4B"], 3.0)
        self.assertNotIn("vllm:unrelated_metric", result["series"])
        client.get.assert_called_once_with(
            "http://vllm:8000/metrics", headers={"Authorization": "Bearer secret"}
        )


if __name__ == "__main__":
    unittest.main()
