"""Telegram alert — sends a formatted job match notification."""

import os
import aiohttp

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramAlert:
    def __init__(self):
        self.token = os.environ["TELEGRAM_BOT_TOKEN"]
        self.chat_id = os.environ["TELEGRAM_CHAT_ID"]

    async def send_job_alert(self, job: dict, ai_docs: dict, row_id: str):
        score = job.get("score", "?")
        title = job.get("title", "")
        company = job.get("company", "")
        location = job.get("location", "Remote")
        salary = job.get("salary", "not listed")
        url = job.get("url", "")
        explanation = ai_docs.get("explanation", "")

        text = (
            f"*New Job Match — {score}/100*\n\n"
            f"*{title}* at *{company}*\n"
            f"Location: {location}\n"
            f"Salary: {salary}\n\n"
            f"{explanation}\n\n"
            f"[View posting]({url})\n\n"
            f"Reply with:\n"
            f"`/approve {row_id}` — mark Ready to Apply\n"
            f"`/skip {row_id}` — skip this one\n"
            f"`/later {row_id}` — save for later"
        )
        await self._send(text, parse_mode="Markdown")

    async def send_followup_reminder(self, job: dict, row_id: str):
        title = job.get("title", "")
        company = job.get("company", "")
        text = (
            f"*Follow-up reminder*\n\n"
            f"You applied to *{title}* at *{company}* 7 days ago.\n"
            f"No response recorded. Consider following up.\n\n"
            f"Row: {row_id}"
        )
        await self._send(text, parse_mode="Markdown")

    async def send_text(self, message: str):
        await self._send(message)

    async def _send(self, text: str, parse_mode: str = ""):
        url = TELEGRAM_API.format(token=self.token)
        payload: dict = {"chat_id": self.chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"Telegram send failed ({resp.status}): {body}")
