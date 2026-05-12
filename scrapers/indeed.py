"""Indeed scraper — parses the public RSS feed. No API key required."""

import re
import aiohttp
import xml.etree.ElementTree as ET
from .base import BaseScraper, Job

RSS_URL = "https://www.indeed.com/rss?q={query}&l={location}&sort=date&fromage=7"


class IndeedScraper(BaseScraper):
    def __init__(self, queries: list[str], location: str = "San Francisco, CA"):
        self.queries = queries
        self.location = location

    async def fetch(self) -> list[Job]:
        jobs = []
        async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
            for query in self.queries:
                jobs.extend(await self._fetch_query(session, query))
        return jobs

    async def _fetch_query(self, session: aiohttp.ClientSession, query: str) -> list[Job]:
        url = RSS_URL.format(
            query=query.replace(" ", "+"),
            location=self.location.replace(" ", "+").replace(",", "%2C"),
        )
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return []
                text = await resp.text()
        except Exception:
            return []

        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []

        ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
        jobs = []
        for item in root.findall(".//item"):
            title = _text(item, "title")
            link = _text(item, "link")
            description_raw = _text(item, "description") or _text(item, "content:encoded", ns)
            company = _extract_company(description_raw or "")
            location = _text(item, "source") or self.location
            salary = _extract_salary(description_raw or "")
            description = re.sub(r"<[^>]+>", " ", description_raw or "").strip()[:2000]

            if title and link:
                jobs.append(Job(
                    title=title,
                    company=company,
                    location=location,
                    url=link,
                    source="indeed",
                    description=description,
                    salary=salary,
                ))
        return jobs


def _text(element, tag: str, ns: dict | None = None) -> str:
    child = element.find(tag, ns or {})
    return (child.text or "").strip() if child is not None else ""


def _extract_company(text: str) -> str:
    match = re.search(r"<b>([^<]+)</b>", text)
    return match.group(1).strip() if match else "Unknown"


def _extract_salary(text: str) -> str:
    match = re.search(r"\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?(?:\s*(?:a year|/yr|/year|an hour|/hr))?", text)
    return match.group(0).strip() if match else ""
