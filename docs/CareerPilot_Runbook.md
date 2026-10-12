# CareerPilot workshop runbook

## Local, mocked verification

From the repository root, run `.venv/bin/python -m unittest discover -s tests -v`. No GPU or live inference endpoint is used by these tests.

For a live connectivity probe, set `AI_PROVIDER=vllm`, `VLLM_HOST`, `MODEL_NAME`, and (if required) `VLLM_API_KEY`, then run `python scripts/test_inference.py`. The workshop default `http://vllm:8000/v1` is internal and should be tested from Jupyter or the assigned namespace, not assumed reachable from a laptop. Keep credentials in environment variables or a Kubernetes Secret.

## Akamai smoke test

1. In the assigned Jupyter environment, confirm the actual namespace, endpoint, model name, and GPU allocation using the workshop-provided environment and scoped `kubectl` access. The earlier RTX PRO 6000 reference is unverified; do not change GPU or vLLM resources.
2. Run `python scripts/test_inference.py`. Confirm the response reports `Qwen/Qwen3-4B` and a measured round-trip latency.
3. Start the Flask app with `python app.py`, upload a consented/synthetic resume, review the extracted fields on Profile, and check the profile verification box.
4. Run CareerPilot from the dashboard. Confirm a real posting is returned, match evidence/gaps are grounded in the verified profile, at least one search tool call is logged, and the application package remains in Review with no submission.
5. Inspect dashboard inference numbers and `/metrics` availability. Per-run latency/token usage is measured by the client/Strands; TTFT is not available in the current non-streaming client path. `/metrics` values are server-wide aggregates, not per-task measurements.

## Workshop deployment

`k8s/careerpilot-agent.yaml` is a Deployment template only. Build and publish an application image using the workshop's approved registry/build process first, then replace `REPLACE_WITH_ASSIGNED_NAMESPACE` and `REPLACE_WITH_WORKSHOP_IMAGE`. It intentionally does not create a vLLM workload, GPU request, Service, or Ingress. Create the optional `careerpilot-secrets` Secret in the assigned namespace only if the endpoint requires a key. Review the manifest and apply it with the workshop-scoped credentials; inspect only resources in that namespace.

The template expects the existing in-namespace vLLM service at `http://vllm:8000/v1`. Confirm DNS/service details before applying. Ensure the image includes the repository and dependencies from `requirements.txt`; the repository's current app expects its working directory and local storage files to be writable. The manifest is a starting point, not a verified workshop deployment.

## Short demo

“CareerPilot reuses our existing scrapers and deterministic match scorer. I verified this candidate profile, and the agent is now discovering current roles through our existing pipeline, explaining fit and gaps with Akamai-hosted Qwen3-4B, and preparing a draft package. The metrics distinguish measured request timing from server-wide vLLM aggregates. Nothing is submitted: a human reviews and approves every application.”
