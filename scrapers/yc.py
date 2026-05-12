"""
Y Combinator job scraper — fetches from workatastartup.com.

Uses the public JSON API that the site itself calls. No auth required.
Great for SF-area startup roles since most YC companies are Bay Area based.
"""

import aiohttp
from .base import BaseScraper, Job

# Public JSON endpoint the site uses for job search
YC_JOBS_API = "https://www.workatastartup.com/jobs/list"
YC_JOB_BASE = "https://www.workatastartup.com/jobs/{job_id}"
YC_COMPANY_BASE = "https://www.workatastartup.com/companies/{slug}"


class YCScraper(BaseScraper):
    def __init__(self, queries: list[str], remote: bool = True):
        self.queries = queries
        self.remote = remote

    async def fetch(self) -> list[Job]:
        jobs = []
        async with aiohttp.ClientSession(headers={
            "Accept": "application/json",
            "Referer": "https://www.workatastartup.com/jobs",
            "X-Requested-With": "XMLHttpRequest",
        }) as session:
            for query in self.queries:
                jobs.extend(await self._fetch_query(session, query))
        return jobs

    async def _fetch_query(self, session: aiohttp.ClientSession, query: str) -> list[Job]:
        params = {
            "q": query,
            "remote": "true" if self.remote else "false",
        }
        try:
            async with session.get(YC_JOBS_API, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json(content_type=None)
        except Exception:
            return []

        jobs_data = data if isinstance(data, list) else data.get("jobs", [])
        jobs = []
        for item in jobs_data[:50]:
            job_id   = item.get("id", "")
            title    = item.get("title", "") or item.get("role", "")
            company  = item.get("company", {})
            company_name = company.get("name", "") if isinstance(company, dict) else str(company)
            company_slug = company.get("slug", "") if isinstance(company, dict) else ""
            location = item.get("location", "")
            salary   = _format_salary(item)
            description = item.get("description", "")[:2000]
            job_url  = YC_JOB_BASE.format(job_id=job_id) if job_id else ""

            if not location:
                location = "Remote" if item.get("remote") else "San Francisco, CA"

            if title and company_name and job_url:
                jobs.append(Job(
                    title=title,
                    company=company_name,
                    location=location,
                    url=job_url,
                    source="yc",
                    description=description,
                    salary=salary,
                ))
        return jobs


def _format_salary(item: dict) -> str:
    low = item.get("salary_min") or item.get("comp_min")
    high = item.get("salary_max") or item.get("comp_max")
    if low and high:
        return f"${int(low):,}–${int(high):,}"
    if low:
        return f"${int(low):,}+"
    return ""
