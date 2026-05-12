"""
Wellfound (AngelList) scraper — uses Playwright to load job search results.

Wellfound requires JavaScript rendering. This scraper navigates the public
job search pages without authentication.
"""

import re
from .base import BaseScraper, Job

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

SEARCH_URL = "https://wellfound.com/jobs?q={query}&l=San%20Francisco%2C%20CA"


class WellfoundScraper(BaseScraper):
    def __init__(self, queries: list[str]):
        self.queries = queries

    async def fetch(self) -> list[Job]:
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("playwright not installed. Run: pip install playwright && playwright install chromium")

        jobs = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            for query in self.queries:
                jobs.extend(await self._scrape_query(page, query))
            await browser.close()
        return jobs

    async def _scrape_query(self, page, query: str) -> list[Job]:
        url = SEARCH_URL.format(query=query.replace(" ", "%20"))
        try:
            await page.goto(url, timeout=25000)
            await page.wait_for_selector("[data-test='JobListing']", timeout=12000)
        except Exception:
            return []

        cards = await page.query_selector_all("[data-test='JobListing']")
        jobs = []
        for card in cards[:30]:
            try:
                title_el   = await card.query_selector("[data-test='JobTitle']")
                company_el = await card.query_selector("[data-test='CompanyName']")
                loc_el     = await card.query_selector("[data-test='JobLocation']")
                salary_el  = await card.query_selector("[data-test='JobCompensation']")
                link_el    = await card.query_selector("a")

                title   = (await title_el.inner_text()).strip()   if title_el   else ""
                company = (await company_el.inner_text()).strip() if company_el else ""
                location = (await loc_el.inner_text()).strip()    if loc_el     else "San Francisco, CA"
                salary  = (await salary_el.inner_text()).strip()  if salary_el  else ""
                href    = await link_el.get_attribute("href")     if link_el    else ""
                job_url = f"https://wellfound.com{href}" if href and href.startswith("/") else href

                if title and company and job_url:
                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=location,
                        url=job_url,
                        source="wellfound",
                        salary=salary,
                    ))
            except Exception:
                continue
        return jobs
