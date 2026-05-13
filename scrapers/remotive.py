"""Remotive scraper — free remote job board API, no auth required."""

import re
import ssl
import aiohttp
import certifi
from .base import BaseScraper, Job

REMOTIVE_API = "https://remotive.com/api/remote-jobs"

_US_OK = re.compile(
    r'\b(remote|usa|united states|north america|worldwide|anywhere|global)\b'
    r'|\bus\b',
    re.IGNORECASE,
)

_NON_US = re.compile(
    r'\b(uk|united kingdom|europe|eu\b|emea|germany|france|spain|portugal|italy|'
    r'netherlands|belgium|switzerland|austria|sweden|norway|denmark|finland|'
    r'poland|czechia|czech republic|hungary|romania|ukraine|russia|'
    r'india|japan|china|korea|taiwan|hong kong|singapore|indonesia|malaysia|'
    r'philippines|vietnam|thailand|australia|new zealand|'
    r'canada|toronto|vancouver|brazil|mexico|argentina|colombia|'
    r'latin america|south america|africa|middle east)\b',
    re.IGNORECASE,
)


class RemotiveScraper(BaseScraper):
    def __init__(self, queries: list[str]):
        self.queries = queries

    async def fetch(self) -> list[Job]:
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        jobs: list[Job] = []
        seen: set[str] = set()
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_ctx)) as session:
            for query in self.queries:
                for job in await self._fetch_query(session, query):
                    if job.url not in seen:
                        seen.add(job.url)
                        jobs.append(job)
        return jobs

    async def _fetch_query(self, session: aiohttp.ClientSession, query: str) -> list[Job]:
        try:
            async with session.get(
                REMOTIVE_API,
                params={"search": query, "limit": 50},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json(content_type=None)
        except Exception:
            return []

        jobs = []
        for item in data.get("jobs", []):
            loc_raw = (item.get("candidate_required_location") or "").strip()
            loc = loc_raw.lower()
            # Accept: empty (no restriction), "Remote", "Worldwide", or any US signal
            # Reject: clearly non-US geo with no US signal
            if loc and _NON_US.search(loc) and not _US_OK.search(loc):
                continue

            title = item.get("title", "").strip()
            company = item.get("company_name", "").strip()
            url = item.get("url", "").strip()
            if not (title and company and url):
                continue

            description = re.sub(r"<[^>]+>", " ", item.get("description", "")).strip()[:2000]
            jobs.append(Job(
                title=title,
                company=company,
                location=loc_raw or "Remote",
                url=url,
                source="remotive",
                description=description,
                salary=item.get("salary", "") or "",
            ))
        return jobs
