"""Temporal activity: scrape all configured job sources."""

import os
import yaml
from temporalio import activity

from utils.search_config import build_search_config, get_local_region


@activity.defn(name="scrape_all_sources")
async def scrape_all_sources(sources_path: str, profile_path: str) -> list[dict]:
    """
    Scrape all enabled sources using queries derived from the user's profile.
    Returns a flat list of job dicts (url-deduplicated).
    """
    import yaml as _yaml
    with open(sources_path) as f:
        sources_cfg = _yaml.safe_load(f).get("sources", [])

    # Load profile and build queries — same logic as Flask standalone path
    profile: dict = {}
    if os.path.exists(profile_path):
        with open(profile_path) as f:
            profile = _yaml.safe_load(f) or {}

    sc             = build_search_config(profile)
    queries        = sc["queries"]
    tags           = sc["tags"]
    title_keywords = sc["title_keywords"]
    location       = sc["location"]

    activity.logger.info(f"queries={queries} | tags={tags} | location={location}")

    scrapers = []
    for src in sources_cfg:
        if not src.get("enabled", True):
            continue
        t = src.get("type")
        try:
            if t == "greenhouse":
                from scrapers.greenhouse import GreenhouseScraper
                scrapers.append(GreenhouseScraper(src.get("companies", [])))
            elif t == "lever":
                from scrapers.lever import LeverScraper
                scrapers.append(LeverScraper(src.get("companies", [])))
            elif t == "hn_hiring":
                from scrapers.hn_hiring import HNHiringScraper
                scrapers.append(HNHiringScraper())
            elif t == "remotive":
                from scrapers.remotive import RemotiveScraper
                scrapers.append(RemotiveScraper(queries))
            elif t == "remoteok":
                from scrapers.remoteok import RemoteOKScraper
                scrapers.append(RemoteOKScraper(tags=tags, title_keywords=title_keywords))
            elif t == "wellfound":
                try:
                    from scrapers.wellfound import WellfoundScraper
                    scrapers.append(WellfoundScraper(queries, location))
                except Exception as e_wf:
                    activity.logger.warning(f"wellfound init failed: {e_wf}")
            elif t == "linkedin":
                li_at = os.getenv("LINKEDIN_LI_AT", "")
                if li_at:
                    from scrapers.linkedin import LinkedInScraper
                    scrapers.append(LinkedInScraper(queries, location, li_at))
            elif t == "indeed":
                from scrapers.indeed import IndeedScraper
                scrapers.append(IndeedScraper(queries, location))
            elif t == "yc":
                from scrapers.yc import YCScraper
                scrapers.append(YCScraper(queries, remote=src.get("remote", True)))
            elif t == "builtin_sf":
                from scrapers.builtin_sf import BuiltInSFScraper
                scrapers.append(BuiltInSFScraper(queries, remote=src.get("remote", False)))
            else:
                activity.logger.warning(f"Unknown source type: {t}")
        except Exception as e:
            activity.logger.error(f"{t} failed to initialize: {type(e).__name__}: {e}")

    activity.logger.info(f"Running {len(scrapers)} scraper(s): {[s.source_name() for s in scrapers]}")

    import asyncio
    raw_results = await asyncio.gather(*[s.fetch() for s in scrapers], return_exceptions=True)

    seen_urls: set[str] = set()
    all_jobs: list[dict] = []
    for scraper_obj, result in zip(scrapers, raw_results):
        name = scraper_obj.source_name()
        if isinstance(result, Exception):
            activity.logger.error(f"{name}: FAILED — {type(result).__name__}: {result}")
        else:
            activity.logger.info(f"{name}: {len(result)} jobs")
            for job in result:
                if job.url not in seen_urls:
                    seen_urls.add(job.url)
                    all_jobs.append(job.to_dict())

    activity.logger.info(f"Total after URL dedup: {len(all_jobs)}")
    return all_jobs


@activity.defn(name="deduplicate_jobs")
async def deduplicate_jobs(raw_jobs: list[dict]) -> list[dict]:
    """Remove jobs already in the sheet by URL."""
    from sheets.client import SheetsClient
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
