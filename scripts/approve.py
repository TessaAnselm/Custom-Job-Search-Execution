"""CLI to approve, skip, or defer jobs waiting for your decision."""

import asyncio
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from temporalio.client import Client
from temporal.workflows.job_search_workflow import JobProcessingWorkflow, ApprovalDecision
from sheets.client import SheetsClient


async def approve(client: Client, job_id: str, decision: ApprovalDecision, notes: str = ""):
    handle = client.get_workflow_handle(f"job-{job_id}")
    await handle.signal(JobProcessingWorkflow.decide, decision, notes or None)
    label = {
        ApprovalDecision.APPLY: "Ready to Apply",
        ApprovalDecision.SKIP: "Skipped",
        ApprovalDecision.LATER: "Saved for later",
    }[decision]
    print(f"Job {job_id} → {label}")


async def list_jobs(status: str = "Review"):
    sheets = SheetsClient()
    jobs = sheets.list_jobs(status_filter=status)
    if not jobs:
        print(f"No jobs with status: {status}")
        return
    print(f"\n{'Row':<5} {'Score':<7} {'Company':<20} {'Title':<35} {'Status'}")
    print("-" * 80)
    for job in jobs:
        print(
            f"{job.get('_row_id', ''):<5} "
            f"{job.get('Match Score', ''):<7} "
            f"{job.get('Company', '')[:18]:<20} "
            f"{job.get('Job Title', '')[:33]:<35} "
            f"{job.get('Status', '')}"
        )


async def main():
    parser = argparse.ArgumentParser(description="Approve or skip jobs")
    sub = parser.add_subparsers(dest="command")

    apply_p = sub.add_parser("apply", help="Approve a job for application")
    apply_p.add_argument("job_id")
    apply_p.add_argument("--notes", default="")

    skip_p = sub.add_parser("skip", help="Skip a job")
    skip_p.add_argument("job_id")
    skip_p.add_argument("--notes", default="")

    later_p = sub.add_parser("later", help="Defer a job for later review")
    later_p.add_argument("job_id")

    list_p = sub.add_parser("list", help="List jobs by status")
    list_p.add_argument("--status", default="Review")

    args = parser.parse_args()

    if args.command == "list" or args.command is None:
        status = getattr(args, "status", "Review")
        await list_jobs(status)
        return

    client = await Client.connect(
        os.getenv("TEMPORAL_HOST", "localhost:7233"),
        namespace=os.getenv("TEMPORAL_NAMESPACE", "default"),
    )

    if args.command == "apply":
        await approve(client, args.job_id, ApprovalDecision.APPLY, args.notes)
    elif args.command == "skip":
        await approve(client, args.job_id, ApprovalDecision.SKIP, args.notes)
    elif args.command == "later":
        await approve(client, args.job_id, ApprovalDecision.LATER)


if __name__ == "__main__":
    asyncio.run(main())
