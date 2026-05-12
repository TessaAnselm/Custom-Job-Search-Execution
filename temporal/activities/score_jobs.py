"""Temporal activity: score jobs against the user profile."""

import yaml
from temporalio import activity
from scoring.scorer import JobScorer


@activity.defn(name="score_jobs")
async def score_jobs(jobs: list[dict], profile_path: str) -> list[dict]:
    with open(profile_path) as f:
        profile = yaml.safe_load(f)

    scorer = JobScorer(profile)
    scored = []
    for job in jobs:
        try:
            result = await scorer.score(job)
            scored.append({**job, **result})
        except Exception as e:
            activity.logger.error(f"Scoring failed for {job.get('id')}: {e}")
            scored.append({**job, "score": 0, "breakdown": {}, "explanation": ""})

    return scored
