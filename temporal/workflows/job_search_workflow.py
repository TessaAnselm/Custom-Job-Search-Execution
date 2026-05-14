"""
Job Search Workflow — the main Temporal orchestration.

This workflow:
1. Scrapes job sources
2. Deduplicates against existing sheet rows
3. Scores each job against the user profile
4. Filters below-threshold jobs
5. Generates tailored resume + cover note for strong matches
6. Writes everything to Google Sheets
7. Sends an alert to the user
8. Waits for human approval signal (forever if needed)
9. Marks final status based on approval decision
"""

from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy
import asyncio

with workflow.unsafe.imports_passed_through():
    from dataclasses import dataclass, field
    from typing import Optional
    from enum import Enum

class ApprovalDecision(str, Enum):
    APPLY = "apply"
    SKIP = "skip"
    LATER = "later"

@dataclass
class JobSearchParams:
    run_id: str
    profile_path: str = "config/profile.yaml"
    sources_path: str = "config/sources.yaml"
    minimum_score: int = 65
    dry_run: bool = False

@dataclass
class JobApprovalSignal:
    job_id: str
    decision: ApprovalDecision
    notes: Optional[str] = None

@workflow.defn
class JobSearchWorkflow:
    """
    Top-level workflow. Scheduled to run on a cron or triggered manually.
    Spawns a child JobProcessingWorkflow per new job found.
    """

    def __init__(self):
        self._approval_signals: dict[str, ApprovalDecision] = {}

    @workflow.signal
    async def approve_job(self, signal: JobApprovalSignal):
        self._approval_signals[signal.job_id] = signal.decision
        workflow.logger.info(f"Received approval signal: {signal.job_id} → {signal.decision}")

    @workflow.run
    async def run(self, params: JobSearchParams):
        workflow.logger.info(f"Starting job search run: {params.run_id}")

        # Step 1: Scrape all sources
        raw_jobs = await workflow.execute_activity(
            "scrape_all_sources",
            args=[params.sources_path, params.profile_path],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        workflow.logger.info(f"Scraped {len(raw_jobs)} raw jobs")

        # Step 2: Deduplicate against sheet
        new_jobs = await workflow.execute_activity(
            "deduplicate_jobs",
            args=[raw_jobs],
            start_to_close_timeout=timedelta(minutes=2),
        )
        workflow.logger.info(f"{len(new_jobs)} new jobs after deduplication")

        if not new_jobs:
            workflow.logger.info("No new jobs found. Run complete.")
            return {"run_id": params.run_id, "new_jobs": 0, "processed": 0}

        # Step 3: Score all jobs against profile
        scored_jobs = await workflow.execute_activity(
            "score_jobs",
            args=[new_jobs, params.profile_path],
            start_to_close_timeout=timedelta(minutes=5),
        )

        # Step 4: Filter below threshold
        strong_matches = [j for j in scored_jobs if j["score"] >= params.minimum_score]
        weak_matches = [j for j in scored_jobs if j["score"] < params.minimum_score]

        workflow.logger.info(
            f"Scoring complete: {len(strong_matches)} strong, {len(weak_matches)} weak"
        )

        # Step 5: Write weak matches to sheet as "Skip" (no AI doc generation)
        if weak_matches:
            await workflow.execute_activity(
                "write_jobs_to_sheet",
                args=[weak_matches, "Skip"],
                start_to_close_timeout=timedelta(minutes=3),
            )

        # Step 6: Process strong matches — generate docs, write sheet, alert, wait for approval
        processing_tasks = [
            workflow.execute_child_workflow(
                JobProcessingWorkflow.run,
                args=[job, params],
                id=f"job-{job['id']}-{params.run_id}",
            )
            for job in strong_matches
        ]

        results = await asyncio.gather(*processing_tasks, return_exceptions=True)

        successes = [r for r in results if not isinstance(r, Exception)]
        failures = [r for r in results if isinstance(r, Exception)]

        if failures:
            workflow.logger.error(f"{len(failures)} job workflows failed: {failures}")

        return {
            "run_id": params.run_id,
            "scraped": len(raw_jobs),
            "new": len(new_jobs),
            "strong_matches": len(strong_matches),
            "weak_matches": len(weak_matches),
            "processed": len(successes),
            "failed": len(failures),
        }


@workflow.defn
class JobProcessingWorkflow:
    """
    Per-job workflow. Handles the full lifecycle of a single job:
    generate docs → write sheet → alert → wait for approval → update status.

    Pauses indefinitely waiting for the human approval signal.
    Temporal handles the durability — this survives worker restarts.
    """

    def __init__(self):
        self._decision: Optional[ApprovalDecision] = None
        self._notes: Optional[str] = None

    @workflow.signal
    async def decide(self, decision: ApprovalDecision, notes: Optional[str] = None):
        self._decision = decision
        self._notes = notes

    @workflow.run
    async def run(self, job: dict, params: JobSearchParams):
        job_id = job["id"]
        workflow.logger.info(f"Processing job: {job_id} — {job['company']} / {job['title']}")

        # Generate tailored resume + cover note
        ai_docs = await workflow.execute_activity(
            "generate_ai_docs",
            args=[job, params.profile_path],
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        # Write full job row to sheet with status "Review"
        sheet_row = {**job, **ai_docs, "status": "Review"}
        row_id = await workflow.execute_activity(
            "write_job_to_sheet",
            args=[sheet_row],
            start_to_close_timeout=timedelta(minutes=1),
        )

        # Alert the user
        await workflow.execute_activity(
            "send_job_alert",
            args=[job, ai_docs, row_id],
            start_to_close_timeout=timedelta(minutes=1),
        )

        # ⏸️ Wait for human approval — no timeout, durable pause
        workflow.logger.info(f"Waiting for approval signal on job {job_id}")
        await workflow.wait_condition(lambda: self._decision is not None)

        decision = self._decision
        workflow.logger.info(f"Received decision for {job_id}: {decision}")

        # Map decision to final status
        status_map = {
            ApprovalDecision.APPLY: "Ready to Apply",
            ApprovalDecision.SKIP: "Skip",
            ApprovalDecision.LATER: "Tailor Resume",
        }
        final_status = status_map[decision]

        # Update sheet with final status
        await workflow.execute_activity(
            "update_job_status",
            args=[row_id, final_status, self._notes],
            start_to_close_timeout=timedelta(minutes=1),
        )

        # If approved to apply, schedule a follow-up reminder
        if decision == ApprovalDecision.APPLY:
            await workflow.execute_child_workflow(
                FollowUpWorkflow.run,
                args=[{"job_id": job_id, "row_id": row_id, "job": job}],
                id=f"followup-{job_id}",
            )

        return {
            "job_id": job_id,
            "decision": decision,
            "status": final_status,
            "row_id": row_id,
        }


@workflow.defn
class FollowUpWorkflow:
    """
    Scheduled after a job is approved to apply.
    Waits N days, then sends a follow-up reminder if status hasn't moved to Interview/Rejected.
    """

    @workflow.run
    async def run(self, params: dict):
        job_id = params["job_id"]
        row_id = params["row_id"]

        # Wait 7 days after applying
        await asyncio.sleep(timedelta(days=7).total_seconds())

        current_status = await workflow.execute_activity(
            "get_job_status",
            args=[row_id],
            start_to_close_timeout=timedelta(minutes=1),
        )

        terminal_statuses = {"Interview", "Rejected", "Offer", "Skip"}
        if current_status not in terminal_statuses:
            await workflow.execute_activity(
                "send_followup_reminder",
                args=[params["job"], row_id],
                start_to_close_timeout=timedelta(minutes=1),
            )
            await workflow.execute_activity(
                "update_job_status",
                args=[row_id, "Follow Up", "Auto follow-up reminder sent"],
                start_to_close_timeout=timedelta(minutes=1),
            )

        return {"job_id": job_id, "follow_up_sent": current_status not in terminal_statuses}
