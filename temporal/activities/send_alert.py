"""Temporal activities: send job alerts and follow-up reminders."""

import os
from temporalio import activity
from alerts.telegram import TelegramAlert
from alerts.gmail import GmailAlert


def _alert_channels():
    """Return whichever alert channels are configured."""
    channels = []
    if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
        channels.append("telegram")
    if os.getenv("GMAIL_USER") and os.getenv("GMAIL_APP_PASSWORD"):
        channels.append("gmail")
    return channels


@activity.defn(name="send_job_alert")
async def send_job_alert(job: dict, ai_docs: dict, row_id: str) -> None:
    channels = _alert_channels()
    if not channels:
        activity.logger.warning("No alert channels configured — skipping alert.")
        return

    for channel in channels:
        try:
            if channel == "telegram":
                tg = TelegramAlert()
                await tg.send_job_alert(job, ai_docs, row_id)
            elif channel == "gmail":
                gmail = GmailAlert()
                gmail.send_job_alert(job, ai_docs, row_id)
            activity.logger.info(f"Alert sent via {channel} for job {job.get('id')}")
        except Exception as e:
            activity.logger.error(f"Alert via {channel} failed: {e}")


@activity.defn(name="send_followup_reminder")
async def send_followup_reminder(job: dict, row_id: str) -> None:
    channels = _alert_channels()
    for channel in channels:
        try:
            if channel == "telegram":
                tg = TelegramAlert()
                await tg.send_followup_reminder(job, row_id)
            elif channel == "gmail":
                gmail = GmailAlert()
                gmail.send_followup_reminder(job, row_id)
        except Exception as e:
            activity.logger.error(f"Follow-up alert via {channel} failed: {e}")
