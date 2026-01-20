from typing import Dict, Optional
from urllib.parse import urlparse

from .generic import scrape_generic
from .linkedin import scrape_linkedin


def _site_from_url(url: str) -> Optional[str]:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return None
    if host.startswith("www."):
        host = host[4:]
    if host.endswith("linkedin.com"):
        return "linkedin"
    return None


_SCRAPERS = {
    "linkedin": scrape_linkedin,
}


def scrape_job(url: str) -> Dict[str, Optional[str]]:
    site = _site_from_url(url)
    scraper = _SCRAPERS.get(site, scrape_generic)
    return scraper(url)
