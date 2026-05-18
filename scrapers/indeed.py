"""Indeed scraper — uses Playwright to scrape the job search page."""

import re
from .base import BaseScraper, Job

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

INDEED_URL = "https://www.indeed.com/jobs?q={query}&l={location}&sort=date&fromage=7"


class IndeedScraper(BaseScraper):
    def __init__(self, queries: list[str], location: str = "Remote"):
        self.queries = queries
        self.location = location

    async def fetch(self) -> list[Job]:
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("playwright not installed. Run: python3 -m playwright install chromium")

        jobs = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/124.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            for query in self.queries:
                jobs.extend(await self._scrape_query(page, query))
            await browser.close()
        return jobs

    async def _scrape_query(self, page, query: str) -> list[Job]:
        url = INDEED_URL.format(
            query=query.replace(" ", "+"),
            location=self.location.replace(" ", "+"),
        )
        try:
            await page.goto(url, timeout=20000)
            await page.wait_for_selector(".job_seen_beacon", timeout=10000)
        except Exception:
            return []

        cards = await page.query_selector_all(".job_seen_beacon")
        jobs = []
        for card in cards[:25]:
            try:
                title_el    = await card.query_selector("h2.jobTitle a span")
                link_el     = await card.query_selector("h2.jobTitle a[data-jk]")
                company_el  = await card.query_selector("[data-testid='company-name']")
                location_el = await card.query_selector("[data-testid='text-location']")
                salary_el   = await card.query_selector(".salary-snippet-container span")

                title    = (await title_el.inner_text()).strip()    if title_el    else ""
                jk       = await link_el.get_attribute("data-jk")  if link_el     else ""
                company  = (await company_el.inner_text()).strip()  if company_el  else ""
                location = (await location_el.inner_text()).strip() if location_el else ""
                salary   = (await salary_el.inner_text()).strip()   if salary_el   else ""
                job_url  = f"https://www.indeed.com/viewjob?jk={jk}" if jk else ""

                if title and job_url:
                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=location,
                        url=job_url,
                        source="indeed",
                        salary=salary,
                    ))
            except Exception:
                continue
        return jobs
