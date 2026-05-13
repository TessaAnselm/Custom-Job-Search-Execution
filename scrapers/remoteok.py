"""RemoteOK scraper — free remote job board API, no auth required."""

import re
import ssl
import aiohttp
import certifi
from .base import BaseScraper, Job

REMOTEOK_API = "https://remoteok.com/api"

_NON_US = re.compile(
    r'\b(uk|united kingdom|europe|eu\b|emea|germany|france|'
    r'india|canada|australia|asia|apac|latin america|brazil|'
    r'toronto|london|berlin|paris|sydney|melbourne)\b',
    re.IGNORECASE,
)
_US_OK = re.compile(
    r'\b(remote|us|usa|united states|north america|worldwide|anywhere)\b',
    re.IGNORECASE,
)


class RemoteOKScraper(BaseScraper):
    def __init__(self, tags: list[str], title_keywords: list[str] | None = None):
        self.tags = tags
        self._title_re = (
            re.compile("|".join(re.escape(k) for k in title_keywords), re.IGNORECASE)
            if title_keywords else None
        )

    async def fetch(self) -> list[Job]:
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        jobs: list[Job] = []
        seen: set[str] = set()
        async with aiohttp.ClientSession(
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            connector=aiohttp.TCPConnector(ssl=ssl_ctx),
        ) as session:
            for tag in self.tags:
                for job in await self._fetch_tag(session, tag):
                    if job.url not in seen:
                        seen.add(job.url)
                        jobs.append(job)
        return jobs

    async def _fetch_tag(self, session: aiohttp.ClientSession, tag: str) -> list[Job]:
        try:
            async with session.get(
                f"{REMOTEOK_API}?tag={tag}",
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json(content_type=None)
        except Exception:
            return []

        jobs = []
        for item in data:
            if not isinstance(item, dict) or not item.get("position"):
                continue

            # If title keywords are configured, skip jobs whose title doesn't match
            if self._title_re and not self._title_re.search(item.get("position", "")):
                continue

            loc_raw = (item.get("location") or "").strip()
            loc = loc_raw.lower()
            # Has a specific non-US location and no US signal → skip
            if loc and _NON_US.search(loc) and not _US_OK.search(loc):
                continue

            title = item.get("position", "").strip()
            company = item.get("company", "").strip()
            job_id = item.get("id", "")
            url = item.get("url", "") or (f"https://remoteok.com/l/{job_id}" if job_id else "")
            if not (title and company and url):
                continue

            description = re.sub(r"<[^>]+>", " ", item.get("description", "")).strip()[:2000]
            salary = _format_salary(item)

            jobs.append(Job(
                title=title,
                company=company,
                location=loc_raw or "Remote",
                url=url,
                source="remoteok",
                description=description,
                salary=salary,
            ))
        return jobs


def _format_salary(item: dict) -> str:
    low = item.get("salary_min") or item.get("salary")
    high = item.get("salary_max")
    try:
        if low and high:
            return f"${int(low):,}–${int(high):,}"
        if low:
            return f"${int(low):,}+"
    except (ValueError, TypeError):
        pass
    return ""
