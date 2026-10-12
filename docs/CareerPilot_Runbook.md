# CareerPilot workshop runbook

## Local, mocked verification

From the repository root, run `.venv/bin/python -m unittest discover -s tests -v`. No GPU or live inference endpoint is used by these tests.

For a live connectivity probe, set `AI_PROVIDER=vllm`, `MODEL_NAME`, and (if required) `VLLM_API_KEY`, then run `python scripts/test_inference.py`. `VLLM_HOST=http://vllm:8000/v1` only resolves from inside the workshop namespace (Jupyter, or a deployed pod). From a laptop, run `kubectl port-forward svc/vllm 8000:8000` in a dedicated terminal (using the workshop-issued kubeconfig — `export KUBECONFIG=/path/to/your-kubeconfig.yaml`) and set `VLLM_HOST=http://localhost:8000/v1` instead; this path has been verified end-to-end (see Verified findings below). Keep credentials in environment variables or a Kubernetes Secret — `VLLM_API_KEY` may be left empty if the endpoint has no auth, the client substitutes a non-empty placeholder automatically.

## Akamai smoke test

1. Confirm the actual namespace, endpoint, model name, and GPU allocation using the workshop-provided environment and scoped `kubectl` access, either from Jupyter or a laptop with the issued kubeconfig. The earlier RTX PRO 6000 reference is unverified; do not change GPU or vLLM resources.
2. Run `python scripts/test_inference.py`. Confirm the response reports `Qwen/Qwen3-4B` and a measured round-trip latency.
3. Start the Flask app with `python app.py`, upload a consented/synthetic resume, review the extracted fields on Profile, and check the profile verification box.
4. Run CareerPilot from the dashboard. Confirm a real posting is returned, match evidence/gaps are grounded in the verified profile, at least one search tool call is logged, and the application package remains in Review with no submission.
5. Inspect dashboard inference numbers and `/metrics` availability. Per-run latency/token usage is measured by the client/Strands; TTFT is not available in the current non-streaming client path. `/metrics` values are server-wide aggregates, not per-task measurements.

## Verified findings (live runs against the workshop's Qwen3-4B, synthetic profile/job data)

- **Tool-calling works.** The Strands agent's full `search_and_match_jobs` → `prepare_application_package` → structured-answer chain runs correctly through this vLLM deployment's OpenAI-compatible endpoint. This was the project's biggest open risk and is resolved.
- **Small-model tool sequencing is not fully reliable on its own.** In early testing, Qwen3-4B sometimes produced its final answer without calling `prepare_application_package`, leaving no application package. Root cause confirmed by reading the installed `strands` library source — not an API/compatibility bug (Strands already strips the `reasoningContent` warning it logs from outgoing multi-turn requests) — just a smaller model under-following a multi-step system prompt. Mitigated two ways: the system prompt now explicitly requires the tool call before finalizing, and `run_careerpilot()` in `careerpilot/agent.py` deterministically generates the package in code if the model still skips it, so a reviewable package is guaranteed regardless of model behavior. Covered by regression tests in `tests/test_careerpilot_agent.py`.
- **Qwen3's "thinking" mode: keep it on.** Tested disabling it via `extra_body: {"chat_template_kwargs": {"enable_thinking": false}}`. Result: ~2x faster (30–40s vs 75–86s per full agent run) but it consistently produced an empty `gaps_or_unknowns` list across all tested runs — the field that flags unsupported requirements, which is the project's explicit anti-hallucination safeguard. The latency win isn't worth losing that, so thinking mode stays on by default. If the live demo is time-constrained, this is a known, quantified trade-off to revisit deliberately, not a default to flip silently.
- **Typical full-run latency with thinking mode on:** 75–86 seconds for one search + one package-prep + final structured answer, measured across 3 consecutive live runs.

## Workshop deployment

`k8s/careerpilot-agent.yaml` is a Deployment template only. Build and publish an application image using the workshop's approved registry/build process first, then replace `REPLACE_WITH_ASSIGNED_NAMESPACE` and `REPLACE_WITH_WORKSHOP_IMAGE`. It intentionally does not create a vLLM workload, GPU request, Service, or Ingress. Create the optional `careerpilot-secrets` Secret in the assigned namespace only if the endpoint requires a key. Review the manifest and apply it with the workshop-scoped credentials; inspect only resources in that namespace.

The template expects the existing in-namespace vLLM service at `http://vllm:8000/v1`. Confirm DNS/service details before applying. Ensure the image includes the repository and dependencies from `requirements.txt`; the repository's current app expects its working directory and local storage files to be writable. The manifest is a starting point, not a verified workshop deployment.

## Short demo

“CareerPilot reuses our existing scrapers and deterministic match scorer. I verified this candidate profile, and the agent is now discovering current roles through our existing pipeline, explaining fit and gaps with Akamai-hosted Qwen3-4B, and preparing a draft package. The metrics distinguish measured request timing from server-wide vLLM aggregates. Nothing is submitted: a human reviews and approves every application.”
