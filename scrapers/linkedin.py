from typing import Dict, Optional

from .generic import scrape_generic


def scrape_linkedin(url: str) -> Dict[str, Optional[str]]:
    return scrape_generic(url)
