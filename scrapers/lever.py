"""Lever API scraper — fetches open jobs for a list of company slugs."""

import aiohttp
from .base import BaseScraper, Job

LEVER_API = "https://api.lever.co/v0/postings/{company}?mode=json"


class LeverScraper(BaseScraper):
    def __init__(self, companies: list[str]):
        self.companies = companies

    async def fetch(self) -> list[Job]:
        jobs = []
        async with aiohttp.ClientSession() as session:
            for company in self.companies:
                jobs.extend(await self._fetch_company(session, company))
        return jobs

    async def _fetch_company(self, session: aiohttp.ClientSession, company: str) -> list[Job]:
        url = LEVER_API.format(company=company)
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except Exception:
            return []

        jobs = []
        for item in data:
            categories = item.get("categories", {})
            location = categories.get("location", "") or categories.get("allLocations", [""])[0]
            commitment = categories.get("commitment", "")

            description_parts = []
            for section in item.get("descriptionBody", {}).get("content", []):
                for child in section.get("content", []):
                    if child.get("type") == "text":
                        description_parts.append(child.get("text", ""))
            description = " ".join(description_parts)[:2000]

            jobs.append(Job(
                title=item.get("text", ""),
                company=company.capitalize(),
                location=location,
                url=item.get("hostedUrl", ""),
                source="lever",
                description=description,
                role_type=_map_commitment(commitment),
            ))
        return jobs


def _map_commitment(commitment: str) -> str:
    c = commitment.lower()
    if "full" in c:
        return "Full-time"
    if "contract" in c:
        return "Contract"
    if "part" in c:
        return "Part-time"
    return commitment
