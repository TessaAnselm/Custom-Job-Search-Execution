"""
Shared search configuration builder.
Used by both the Flask standalone path (app.py) and the Temporal activity
(temporal/activities/scrape_jobs.py) so both paths always produce identical
queries, tags, and location from the same profile.
"""

_GENERIC_TITLE_WORDS = {
    "engineer", "developer", "manager", "analyst", "designer", "lead",
    "senior", "junior", "staff", "principal", "associate", "specialist",
    "architect", "consultant", "director", "head", "vp", "chief",
    "intern", "contractor", "freelance", "remote", "full", "part", "time",
}


def get_local_region() -> dict:
    """Detect the server's local timezone and return matching location keywords."""
    import datetime
    offset_h = datetime.datetime.now().astimezone().utcoffset().total_seconds() / 3600
    if offset_h <= -7:
        return {"label": "West Coast US", "abbr": "PT",
                "keywords": ["remote (us)", "remote", "san francisco", "sf", "california",
                             "pacific", "seattle", "los angeles", "west coast", "us"]}
    if offset_h <= -5:
        return {"label": "Central / Mountain US", "abbr": "CT/MT",
                "keywords": ["remote (us)", "remote", "chicago", "denver", "mountain",
                             "central", "us"]}
    if offset_h <= -3:
        return {"label": "East Coast US", "abbr": "ET",
                "keywords": ["remote (us)", "remote", "new york", "nyc", "boston",
                             "east coast", "us"]}
    if offset_h <= 1:
        return {"label": "UK / West Europe", "abbr": "GMT",
                "keywords": ["remote (eu)", "remote", "uk", "london", "ireland",
                             "amsterdam", "paris", "europe", "eu"]}
    if offset_h <= 4:
        return {"label": "Central / East Europe", "abbr": "CET",
                "keywords": ["remote (eu)", "remote", "berlin", "amsterdam", "paris",
                             "europe", "eu", "warsaw", "prague"]}
    if offset_h <= 7:
        return {"label": "Middle East / South Asia", "abbr": "IST",
                "keywords": ["remote", "india", "dubai", "israel"]}
    if offset_h <= 10:
        return {"label": "East Asia", "abbr": "SGT",
                "keywords": ["remote", "singapore", "hong kong", "china", "japan",
                             "korea", "asia"]}
    return {"label": "Asia Pacific", "abbr": "AEST",
            "keywords": ["remote", "australia", "sydney", "melbourne", "auckland"]}


def build_search_config(profile: dict) -> dict:
    """
    Derive all search queries, RemoteOK tags, and scraper location from the
    profile. No hardcoded job titles or keywords anywhere.

    Returns:
        queries        — list of search strings for Remotive / Wellfound / LinkedIn
        tags           — list of single-word tags for RemoteOK API
        title_keywords — list of words used to filter RemoteOK results by title
        location       — city string for scrapers that accept a location param
    """
    target_titles = profile.get("target_titles") or []
    skills        = profile.get("skills") or []

    # Primary queries: target titles from profile
    queries: list[str] = []
    seen: set[str] = set()
    for t in target_titles:
        key = t.lower().strip()
        if key and key not in seen:
            seen.add(key)
            queries.append(t.strip())

    # Pad with key skills if fewer than 4 title queries
    if len(queries) < 4:
        for skill in skills:
            key = skill.lower().strip()
            if key and key not in seen:
                seen.add(key)
                queries.append(skill.strip())
            if len(queries) >= 6:
                break

    queries = queries[:8]

    # RemoteOK tags: distinctive single words from target titles
    tags: list[str] = []
    tag_seen: set[str] = set()
    for title in target_titles:
        for word in title.lower().split():
            w = word.strip("(),./")
            if w and w not in _GENERIC_TITLE_WORDS and w not in tag_seen and len(w) > 2:
                tag_seen.add(w)
                tags.append(w)
    if not tags:
        tags = [q.split()[0].lower() for q in queries if q.split()][:4]

    # Title keywords for RemoteOK result filtering
    title_kws: list[str] = []
    tkw_seen: set[str] = set()
    for title in target_titles:
        for word in title.lower().split():
            w = word.strip("(),./")
            if len(w) > 2 and w not in tkw_seen:
                tkw_seen.add(w)
                title_kws.append(w)

    # Location comes from the server's detected timezone, not from the resume
    region = get_local_region()
    region_location = {
        "PT":    "San Francisco Bay Area, CA",
        "CT/MT": "Chicago, IL",
        "ET":    "New York, NY",
        "GMT":   "London, UK",
        "CET":   "Berlin, Germany",
    }.get(region["abbr"], "Remote")

    return {
        "queries":        queries,
        "tags":           tags,
        "title_keywords": title_kws or None,
        "location":       region_location,
    }
