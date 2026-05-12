"""
MCP server — exposes job search agent capabilities to Claude and other MCP clients.
Wraps Temporal workflow signals and queries.

Run with: python mcp/server.py
"""

import asyncio
import os
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from temporalio.client import Client
from temporal.workflows.job_search_workflow import (
    JobSearchWorkflow,
    JobProcessingWorkflow,
    JobSearchParams,
    JobApprovalSignal,
    ApprovalDecision,
)
from sheets.client import SheetsClient
import uuid

app = Server("job-search-agent")
TASK_QUEUE = "job-search-queue"


async def get_temporal_client() -> Client:
    return await Client.connect(
        os.getenv("TEMPORAL_HOST", "localhost:7233"),
        namespace=os.getenv("TEMPORAL_NAMESPACE", "job-search"),
    )


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_jobs",
            description="Trigger a new job search run across all configured sources.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, scrape and score but don't write to sheet or send alerts.",
                        "default": False,
                    }
                },
            },
        ),
        Tool(
            name="list_jobs",
            description="List jobs from the tracker, optionally filtered by status or minimum score.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter by status (e.g. 'Review', 'Ready to Apply')"},
                    "min_score": {"type": "integer", "description": "Minimum match score (0-100)"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        ),
        Tool(
            name="approve_job",
            description="Approve a job for application. Sends the approval signal to Temporal.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job ID from the tracker"},
                    "notes": {"type": "string", "description": "Optional notes about the decision"},
                },
                "required": ["job_id"],
            },
        ),
        Tool(
            name="skip_job",
            description="Skip a job (mark as not interested).",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job ID from the tracker"},
                    "notes": {"type": "string"},
                },
                "required": ["job_id"],
            },
        ),
        Tool(
            name="update_status",
            description="Update the status of a job in the tracker.",
            inputSchema={
                "type": "object",
                "properties": {
                    "row_id": {"type": "string"},
                    "status": {"type": "string", "description": "New status"},
                    "notes": {"type": "string"},
                },
                "required": ["row_id", "status"],
            },
        ),
        Tool(
            name="get_stats",
            description="Get pipeline statistics: how many jobs at each stage.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    client = await get_temporal_client()

    if name == "search_jobs":
        run_id = str(uuid.uuid4())[:8]
        params = JobSearchParams(
            run_id=run_id,
            dry_run=arguments.get("dry_run", False),
        )
        handle = await client.start_workflow(
            JobSearchWorkflow.run,
            params,
            id=f"job-search-{run_id}",
            task_queue="job-search-queue",
        )
        return [TextContent(
            type="text",
            text=f"Job search started. Workflow ID: job-search-{run_id}\n"
                 f"I'll alert you when strong matches are found and ready for your review."
        )]

    elif name == "approve_job":
        job_id = arguments["job_id"]
        signal = JobApprovalSignal(
            job_id=job_id,
            decision=ApprovalDecision.APPLY,
            notes=arguments.get("notes"),
        )
        handle = client.get_workflow_handle(f"job-{job_id}")
        await handle.signal(JobProcessingWorkflow.decide, ApprovalDecision.APPLY, arguments.get("notes"))
        return [TextContent(type="text", text=f"✅ Job {job_id} approved for application. Status updated to 'Ready to Apply'.")]

    elif name == "skip_job":
        job_id = arguments["job_id"]
        handle = client.get_workflow_handle(f"job-{job_id}")
        await handle.signal(JobProcessingWorkflow.decide, ApprovalDecision.SKIP, arguments.get("notes"))
        return [TextContent(type="text", text=f"⏭️ Job {job_id} skipped.")]

    elif name == "update_status":
        sheets = SheetsClient()
        await sheets.update_status(
            arguments["row_id"],
            arguments["status"],
            arguments.get("notes"),
        )
        return [TextContent(type="text", text=f"Updated row {arguments['row_id']} → {arguments['status']}")]

    elif name == "get_stats":
        # In a real implementation, query the sheet for status counts
        return [TextContent(type="text", text="Stats: Connect to Google Sheets to retrieve live counts.")]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
