"""
Built In SF scraper — fetches tech jobs from builtinsf.com.

Built In SF is a curated directory of San Francisco tech companies.
Uses aiohttp to hit their JSON search API.
"""

import aiohttp
from .base import BaseScraper, Job

BUILTIN_API = "https://api.builtin.com/builtin/jobs"
BUILTIN_JOB_BASE = "https://www.builtinsf.com/job/{slug}"

HEADERS = {
    "Accept": "application/json",
    "Origin": "https://www.builtinsf.com",
    "Referer": "https://www.builtinsf.com/jobs",
}


class BuiltInSFScraper(BaseScraper):
    def __init__(self, keywords: list[str], remote: bool = False):
        self.keywords = keywords
        self.remote = remote

    async def fetch(self) -> list[Job]:
        jobs = []
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            for keyword in self.keywords:
                jobs.extend(await self._fetch_keyword(session, keyword))
        return jobs

    async def _fetch_keyword(self, session: aiohttp.ClientSession, keyword: str) -> list[Job]:
        params = {
            "search": keyword,
            "city": "san-francisco",
            "limit": 25,
            "offset": 0,
        }
        if self.remote:
            params["remote"] = "true"

        try:
            async with session.get(BUILTIN_API, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return await self._fallback_rss(session, keyword)
                data = await resp.json(content_type=None)
        except Exception:
            return []

        items = data if isinstance(data, list) else data.get("jobs", data.get("results", []))
        jobs = []
        for item in items:
            title   = item.get("title", "") or item.get("name", "")
            company = item.get("company", {})
            company_name = company.get("name", "") if isinstance(company, dict) else str(company)
            location = item.get("location", "San Francisco, CA")
            salary  = _format_salary(item)
            slug    = item.get("slug", "") or str(item.get("id", ""))
            job_url = item.get("url", "") or (BUILTIN_JOB_BASE.format(slug=slug) if slug else "")
            description = item.get("description", "")[:2000]

            if title and company_name and job_url:
                jobs.append(Job(
                    title=title,
                    company=company_name,
                    location=location,
                    url=job_url,
                    source="builtin_sf",
                    description=description,
                    salary=salary,
                ))
        return jobs

    async def _fallback_rss(self, session: aiohttp.ClientSession, keyword: str) -> list[Job]:
        """Fallback: parse the Built In SF jobs page HTML for job listings."""
        import re
        url = f"https://www.builtinsf.com/jobs?search={keyword.replace(' ', '+')}"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
        except Exception:
            return []

        # Extract job data from JSON embedded in the page (Next.js __NEXT_DATA__)
        match = re.search(r'"jobs"\s*:\s*(\[.*?\])\s*[,}]', html, re.DOTALL)
        if not match:
            return []
        import json
        try:
            items = json.loads(match.group(1))
        except Exception:
            return []

        jobs = []
        for item in items[:25]:
            title = item.get("title", "")
            company = item.get("companyName", "") or item.get("company", "")
            job_url = item.get("url", "") or item.get("canonicalUrl", "")
            if title and company and job_url:
                jobs.append(Job(
                    title=title,
                    company=company,
                    location="San Francisco, CA",
                    url=job_url,
                    source="builtin_sf",
                ))
        return jobs


def _format_salary(item: dict) -> str:
    low = item.get("salary_min") or item.get("salaryMin")
    high = item.get("salary_max") or item.get("salaryMax")
    if low and high:
        return f"${int(low):,}–${int(high):,}"
    if low:
        return f"${int(low):,}+"
    return ""
