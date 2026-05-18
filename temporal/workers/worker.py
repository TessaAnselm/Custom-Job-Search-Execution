"""Temporal worker — registers all activities and starts polling."""

import asyncio
import os
import logging
from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.worker import Worker

load_dotenv()

from temporal.workflows.job_search_workflow import (
    JobSearchWorkflow,
    JobProcessingWorkflow,
    FollowUpWorkflow,
)
from temporal.activities.scrape_jobs import scrape_all_sources, deduplicate_jobs
from temporal.activities.score_jobs import score_jobs
from temporal.activities.generate_docs import generate_ai_docs
from temporal.activities.update_sheet import (
    write_jobs_to_sheet,
    write_job_to_sheet,
    update_job_status,
    get_job_status,
)
from temporal.activities.send_alert import send_job_alert, send_followup_reminder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TASK_QUEUE = "job-search-queue"


async def main():
    client = await Client.connect(
        os.getenv("TEMPORAL_HOST", "localhost:7233"),
        namespace=os.getenv("TEMPORAL_NAMESPACE", "default"),
    )

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[JobSearchWorkflow, JobProcessingWorkflow, FollowUpWorkflow],
        activities=[
            scrape_all_sources,
            deduplicate_jobs,
            score_jobs,
            generate_ai_docs,
            write_jobs_to_sheet,
            write_job_to_sheet,
            update_job_status,
            get_job_status,
            send_job_alert,
            send_followup_reminder,
        ],
    )

    logger.info(f"Worker started — polling task queue: {TASK_QUEUE}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
