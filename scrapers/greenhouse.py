"""Greenhouse API scraper — fetches open jobs for a list of company slugs."""

import aiohttp
from .base import BaseScraper, Job

GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true"


class GreenhouseScraper(BaseScraper):
    def __init__(self, companies: list[str]):
        self.companies = companies

    async def fetch(self) -> list[Job]:
        jobs = []
        async with aiohttp.ClientSession() as session:
            for company in self.companies:
                jobs.extend(await self._fetch_company(session, company))
        return jobs

    async def _fetch_company(self, session: aiohttp.ClientSession, company: str) -> list[Job]:
        url = GREENHOUSE_API.format(company=company)
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except Exception:
            return []

        jobs = []
        for item in data.get("jobs", []):
            location = ""
            offices = item.get("offices", [])
            if offices:
                location = offices[0].get("name", "")

            salary = ""
            compensation = item.get("compensation", {})
            if compensation:
                min_val = compensation.get("min_value", "")
                max_val = compensation.get("max_value", "")
                currency = compensation.get("currency", "USD")
                if min_val and max_val:
                    salary = f"{currency} {min_val}–{max_val}"

            description = ""
            content = item.get("content", "")
            if content:
                # Strip basic HTML tags for plain text
                import re
                description = re.sub(r"<[^>]+>", " ", content).strip()[:2000]

            jobs.append(Job(
                title=item.get("title", ""),
                company=company.capitalize(),
                location=location,
                url=item.get("absolute_url", ""),
                source="greenhouse",
                description=description,
                salary=salary,
            ))
        return jobs
