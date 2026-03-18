import re
from typing import List, Set

import requests
from bs4 import BeautifulSoup


def _fetch_xml(url: str, timeout: int = 12) -> str:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "ADE-Crawler/1.0"})
    response.raise_for_status()
    return response.text


def parse_sitemap(url: str, max_urls: int = 500) -> List[str]:
    seen: Set[str] = set()
    to_visit = [url]
    urls: List[str] = []

    while to_visit and len(urls) < max_urls:
        current = to_visit.pop(0)
        if current in seen:
            continue
        seen.add(current)
        xml = _fetch_xml(current)
        soup = BeautifulSoup(xml, "xml")
        if soup.find("sitemapindex"):
            for loc in soup.find_all("loc"):
                loc_text = loc.get_text(strip=True)
                if loc_text and loc_text not in seen:
                    to_visit.append(loc_text)
            continue
        for loc in soup.find_all("loc"):
            loc_text = loc.get_text(strip=True)
            if loc_text and loc_text not in seen:
                urls.append(loc_text)
                seen.add(loc_text)
            if len(urls) >= max_urls:
                break
    return urls


def filter_product_urls(urls: List[str], rules: List[str]) -> List[str]:
    if not rules:
        return urls
    patterns = [re.compile(rule, re.IGNORECASE) for rule in rules]
    return [url for url in urls if any(pattern.search(url) for pattern in patterns)]
