"""Temporal activity: scrape all configured job sources."""

import yaml
from temporalio import activity
from scrapers.greenhouse import GreenhouseScraper
from scrapers.lever import LeverScraper
from scrapers.hn_hiring import HNHiringScraper
from scrapers.linkedin import LinkedInScraper
from sheets.client import SheetsClient


@activity.defn(name="scrape_all_sources")
async def scrape_all_sources(sources_path: str) -> list[dict]:
    with open(sources_path) as f:
        config = yaml.safe_load(f)

    all_jobs: list[dict] = []
    for source in config.get("sources", []):
        source_type = source.get("type")
        enabled = source.get("enabled", True)
        if not enabled:
            continue

        try:
            if source_type == "greenhouse":
                scraper = GreenhouseScraper(source.get("companies", []))
            elif source_type == "lever":
                scraper = LeverScraper(source.get("companies", []))
            elif source_type == "hn_hiring":
                scraper = HNHiringScraper()
            elif source_type == "linkedin":
                scraper = LinkedInScraper(
                    keywords=source.get("keywords", []),
                    location=source.get("location", "Remote"),
                )
            else:
                activity.logger.warning(f"Unknown source type: {source_type}")
                continue

            jobs = await scraper.fetch()
            all_jobs.extend(job.to_dict() for job in jobs)
            activity.logger.info(f"Scraped {len(jobs)} jobs from {source_type}")
        except Exception as e:
            activity.logger.error(f"Scraper {source_type} failed: {e}")

    return all_jobs


@activity.defn(name="deduplicate_jobs")
async def deduplicate_jobs(raw_jobs: list[dict]) -> list[dict]:
    """Remove jobs already in the sheet by URL."""
    sheets = SheetsClient()
    existing_urls = sheets.get_existing_urls()

    seen_urls: set[str] = set()
    new_jobs = []
    for job in raw_jobs:
        url = job.get("url", "")
        if url and url not in existing_urls and url not in seen_urls:
            seen_urls.add(url)
            new_jobs.append(job)

    activity.logger.info(f"Deduplication: {len(raw_jobs)} raw → {len(new_jobs)} new")
    return new_jobs
