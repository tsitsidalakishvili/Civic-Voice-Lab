import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from .audience_discovery_sitemap import filter_product_urls, parse_sitemap


DEFAULT_PRODUCT_RULES = [
    r"/product",
    r"/products",
    r"/service",
    r"/services",
    r"/program",
    r"/programs",
    r"/solution",
    r"/solutions",
    r"/concert",
]


def _looks_like_product_page(url: str, html: str, product_rules: List[str]) -> bool:
    if product_rules:
        for rule in product_rules:
            if re.search(rule, url, flags=re.IGNORECASE):
                return True
    lower_url = url.lower()
    if any(keyword in lower_url for keyword in ["product", "service", "program", "solution"]):
        return True
    soup = BeautifulSoup(html, "html.parser")
    headings = " ".join(
        [
            heading.get_text(strip=True).lower()
            for heading in soup.find_all(["h1", "h2"])
        ]
    )
    cta_text = " ".join(
        [
            button.get_text(strip=True).lower()
            for button in soup.find_all(["button", "a"])
        ]
    )
    heuristics = [
        "apply",
        "join",
        "get started",
        "book",
        "request demo",
        "donate",
        "sign up",
    ]
    if any(keyword in headings for keyword in ["program", "service", "solution", "offer"]):
        return True
    if any(keyword in cta_text for keyword in heuristics):
        return True
    feature_blocks = soup.find_all(attrs={"class": re.compile(r"(feature|card|benefit)", re.IGNORECASE)})
    return len(feature_blocks) >= 2


@dataclass
class CrawlPage:
    url: str
    status: str
    html: str = ""
    content_type: str = ""
    raw_bytes: bytes = b""
    error: str = ""


@dataclass
class CrawlResult:
    pages: List[CrawlPage] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)


def _allowed_domain(url: str, allowed_domains: List[str]) -> bool:
    if not allowed_domains:
        return True
    host = urlparse(url).netloc.lower()
    return any(host.endswith(domain.lower()) for domain in allowed_domains)


def _is_pdf(url: str, content_type: str) -> bool:
    path = urlparse(url).path.lower()
    if path.endswith(".pdf"):
        return True
    return "application/pdf" in (content_type or "").lower()


def _fetch(
    url: str, timeout: int, user_agent: str, retries: int = 2
) -> Tuple[str, int, str, bytes]:
    headers = {"User-Agent": user_agent}
    last_error = ""
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            content_type = response.headers.get("Content-Type", "")
            if _is_pdf(url, content_type):
                return "", response.status_code, content_type, response.content
            return response.text, response.status_code, content_type, response.content
        except requests.RequestException as exc:
            last_error = str(exc)
            time.sleep(0.5 * (attempt + 1))
    raise requests.RequestException(last_error)


def _get_robots_parser(url: str, user_agent: str) -> Optional[RobotFileParser]:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    try:
        parser.set_url(robots_url)
        parser.read()
        return parser
    except Exception:
        return None


def _extract_links(base_url: str, html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: List[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        absolute = urljoin(base_url, href)
        links.append(absolute.split("#")[0])
    return links


def crawl_site(
    sitemap_url: Optional[str],
    seed_urls: List[str],
    depth: int = 1,
    allowed_domains: Optional[List[str]] = None,
    product_rules: Optional[List[str]] = None,
    timeout: int = 12,
    max_pages: int = 200,
    user_agent: str = "ADE-Crawler/1.0",
    respect_robots: bool = True,
) -> CrawlResult:
    allowed_domains = allowed_domains or []
    product_rules = product_rules or DEFAULT_PRODUCT_RULES
    result = CrawlResult()
    seen: Set[str] = set()

    if sitemap_url:
        try:
            urls = parse_sitemap(sitemap_url, max_urls=max_pages)
            urls = filter_product_urls(urls, product_rules)
            seed_urls = seed_urls + urls
        except requests.RequestException as exc:
            result.logs.append(f"Sitemap fetch failed: {exc}")

    frontier: List[Tuple[str, int]] = [(url, 0) for url in seed_urls]
    robots = _get_robots_parser(seed_urls[0], user_agent) if seed_urls else None

    while frontier and len(result.pages) < max_pages:
        url, level = frontier.pop(0)
        if url in seen:
            continue
        seen.add(url)
        if not _allowed_domain(url, allowed_domains):
            result.pages.append(CrawlPage(url=url, status="skipped", error="Domain not allowed"))
            result.logs.append(f"Skipped {url}: domain not allowed")
            continue
        if respect_robots and robots and not robots.can_fetch(user_agent, url):
            result.pages.append(CrawlPage(url=url, status="skipped", error="robots.txt"))
            result.logs.append(f"Skipped {url}: blocked by robots.txt")
            continue
        try:
            html, status_code, content_type, raw_bytes = _fetch(url, timeout, user_agent)
        except requests.RequestException as exc:
            result.pages.append(CrawlPage(url=url, status="failed", error=str(exc)))
            result.logs.append(f"Failed {url}: {exc}")
            continue
        if status_code >= 400:
            result.pages.append(
                CrawlPage(url=url, status="failed", error=f"HTTP {status_code}")
            )
            result.logs.append(f"Failed {url}: HTTP {status_code}")
            continue
        if _is_pdf(url, content_type):
            result.pages.append(
                CrawlPage(
                    url=url,
                    status="success",
                    html="",
                    content_type=content_type,
                    raw_bytes=raw_bytes,
                )
            )
            result.logs.append(f"Captured PDF content from {url}")
            continue
        if not _looks_like_product_page(url, html, product_rules):
            result.pages.append(
                CrawlPage(url=url, status="skipped", error="Non-product page")
            )
            result.logs.append(f"Skipped {url}: non-product heuristics")
            continue
        result.pages.append(
            CrawlPage(
                url=url,
                status="success",
                html=html,
                content_type=content_type,
                raw_bytes=raw_bytes,
            )
        )
        if level < depth:
            for link in _extract_links(url, html):
                if link not in seen:
                    frontier.append((link, level + 1))
    return result
