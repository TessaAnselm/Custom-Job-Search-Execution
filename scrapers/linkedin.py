"""
LinkedIn scraper — uses Playwright with a session cookie.

Requires LINKEDIN_LI_AT env var (your li_at session cookie).
LinkedIn aggressively blocks scrapers; this is best-effort.
"""

import os
import re
from .base import BaseScraper, Job

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

LINKEDIN_JOBS_URL = (
    "https://www.linkedin.com/jobs/search/?keywords={keywords}"
    "&location={location}&f_TPR=r86400&sortBy=DD"
)


class LinkedInScraper(BaseScraper):
    def __init__(self, keywords: list[str], location: str = "Remote", li_at: str = ""):
        self.keywords = keywords
        self.location = location
        self.li_at = li_at or os.getenv("LINKEDIN_LI_AT", "")

    async def fetch(self) -> list[Job]:
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("playwright not installed. Run: pip install playwright && playwright install chromium")
        if not self.li_at:
            raise RuntimeError("LINKEDIN_LI_AT env var not set — LinkedIn scraping requires a session cookie.")

        jobs = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context()
            await context.add_cookies([{
                "name": "li_at",
                "value": self.li_at,
                "domain": ".linkedin.com",
                "path": "/",
            }])
            page = await context.new_page()

            for keyword in self.keywords:
                url = LINKEDIN_JOBS_URL.format(
                    keywords=keyword.replace(" ", "%20"),
                    location=self.location.replace(" ", "%20"),
                )
                jobs.extend(await self._scrape_page(page, url))

            await browser.close()
        return jobs

    async def _scrape_page(self, page, url: str) -> list[Job]:
        try:
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_selector(".job-card-container", timeout=10000)
        except Exception:
            return []

        cards = await page.query_selector_all(".job-card-container")
        jobs = []
        for card in cards[:25]:
            try:
                title_el    = await card.query_selector("a.job-card-container__link strong")
                company_el  = await card.query_selector(".artdeco-entity-lockup__subtitle")
                location_el = await card.query_selector(".job-card-container__metadata-wrapper li")
                link_el     = await card.query_selector("a.job-card-container__link")

                title    = (await title_el.inner_text()).strip()    if title_el    else ""
                company  = (await company_el.inner_text()).strip()  if company_el  else ""
                location = (await location_el.inner_text()).strip() if location_el else ""
                href     = await link_el.get_attribute("href")      if link_el     else ""
                job_url  = f"https://www.linkedin.com{href}" if href and href.startswith("/") else href

                if title and company and job_url:
                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=location,
                        url=job_url,
                        source="linkedin",
                    ))
            except Exception:
                continue
        return jobs
