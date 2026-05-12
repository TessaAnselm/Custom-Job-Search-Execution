"""HN Who's Hiring scraper — parses the monthly Ask HN thread."""

import re
import aiohttp
from .base import BaseScraper, Job

HN_SEARCH_API = "https://hn.algolia.com/api/v1/search_by_date"
HN_ITEM_API = "https://hacker-news.firebaseio.com/v0/item/{}.json"


class HNHiringScraper(BaseScraper):
    async def fetch(self) -> list[Job]:
        thread_id = await self._find_latest_thread()
        if not thread_id:
            return []
        return await self._parse_thread(thread_id)

    async def _find_latest_thread(self) -> str | None:
        params = {
            "query": "Ask HN: Who is hiring?",
            "tags": "story,ask_hn",
            "hitsPerPage": 5,
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(HN_SEARCH_API, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    hits = data.get("hits", [])
                    if hits:
                        return hits[0].get("objectID")
            except Exception:
                return None
        return None

    async def _parse_thread(self, thread_id: str) -> list[Job]:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    HN_ITEM_API.format(thread_id),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    thread = await resp.json()
            except Exception:
                return []

            kids = thread.get("kids", [])[:200]  # cap at 200 top-level comments
            jobs = []

            for kid_id in kids:
                job = await self._parse_comment(session, kid_id)
                if job:
                    jobs.append(job)

        return jobs

    async def _parse_comment(self, session: aiohttp.ClientSession, comment_id: int) -> Job | None:
        try:
            async with session.get(
                HN_ITEM_API.format(comment_id),
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                comment = await resp.json()
        except Exception:
            return None

        text = comment.get("text", "") or ""
        if not text or comment.get("dead") or comment.get("deleted"):
            return None

        # First line is usually "Company | Role | Location | Remote/Onsite | Salary"
        lines = text.split("<p>")
        first_line = re.sub(r"<[^>]+>", "", lines[0]).strip()
        parts = [p.strip() for p in first_line.split("|")]

        company = parts[0] if parts else "Unknown"
        title = parts[1] if len(parts) > 1 else "Software Engineer"
        location = parts[2] if len(parts) > 2 else ""
        salary = next((p for p in parts if "$" in p or "k" in p.lower()), "")

        description = re.sub(r"<[^>]+>", " ", text).strip()[:2000]
        url = f"https://news.ycombinator.com/item?id={comment_id}"

        return Job(
            title=title,
            company=company,
            location=location,
            url=url,
            source="hn_hiring",
            description=description,
            salary=salary,
        )
