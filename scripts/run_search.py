"""Trigger a job search run via Temporal."""

import asyncio
import argparse
import os
import uuid
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from temporalio.client import Client
from temporal.workflows.job_search_workflow import JobSearchWorkflow, JobSearchParams


async def main():
    parser = argparse.ArgumentParser(description="Trigger a job search run")
    parser.add_argument("--dry-run", action="store_true", help="Scrape and score but don't write to sheet or alert")
    parser.add_argument("--profile", default="config/profile.yaml")
    parser.add_argument("--sources", default="config/sources.yaml")
    parser.add_argument("--min-score", type=int, default=65)
    args = parser.parse_args()

    client = await Client.connect(
        os.getenv("TEMPORAL_HOST", "localhost:7233"),
        namespace=os.getenv("TEMPORAL_NAMESPACE", "default"),
    )

    run_id = str(uuid.uuid4())[:8]
    params = JobSearchParams(
        run_id=run_id,
        profile_path=args.profile,
        sources_path=args.sources,
        minimum_score=args.min_score,
        dry_run=args.dry_run,
    )

    print(f"Starting job search run {run_id}...")
    handle = await client.start_workflow(
        JobSearchWorkflow.run,
        params,
        id=f"job-search-{run_id}",
        task_queue="job-search-queue",
    )

    print(f"Workflow started: {handle.id}")
    if args.dry_run:
        print("Dry run — waiting for result...")
        result = await handle.result()
        print(f"Result: {result}")
    else:
        print("Running in background. You'll be alerted when strong matches are found.")
        print(f"Check status: python scripts/approve.py --list")


if __name__ == "__main__":
    asyncio.run(main())
