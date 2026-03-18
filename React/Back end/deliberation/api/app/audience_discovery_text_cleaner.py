import re
from io import BytesIO
from typing import Dict, List

from bs4 import BeautifulSoup
from PyPDF2 import PdfReader


def _safe_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _normalize_text(raw_text: str) -> str:
    raw_text = re.sub(r"[ \t]+", " ", raw_text or "")
    raw_text = re.sub(r"\n{2,}", "\n\n", raw_text)
    return raw_text.strip()


def _find_breadcrumbs(soup: BeautifulSoup) -> List[str]:
    crumbs: List[str] = []
    candidates = soup.find_all(
        ["nav", "ol", "ul"],
        attrs={"class": re.compile(r"breadcrumb", re.IGNORECASE)},
    )
    for node in candidates:
        for item in node.find_all(["li", "a", "span"]):
            text = item.get_text(strip=True)
            if text and text not in crumbs:
                crumbs.append(text)
    return crumbs


def _extract_headings(soup: BeautifulSoup) -> List[str]:
    headings = []
    for tag in soup.find_all(["h1", "h2"]):
        text = tag.get_text(strip=True)
        if text:
            headings.append(text)
    return headings


def extract_pdf_content(pdf_bytes: bytes, url: str) -> Dict[str, object]:
    title = url.split("/")[-1] or "PDF document"
    if not pdf_bytes:
        return {
            "title": title,
            "meta_description": "",
            "canonical_url": url,
            "cleaned_text": "",
            "headings": [],
            "breadcrumbs": [],
        }
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        if reader.metadata and reader.metadata.title:
            title = _safe_text(str(reader.metadata.title)) or title
        pages_text = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages_text.append(page_text)
        cleaned_text = _normalize_text("\n\n".join(pages_text))
    except Exception:
        cleaned_text = ""
    return {
        "title": title,
        "meta_description": "",
        "canonical_url": url,
        "cleaned_text": cleaned_text,
        "headings": [],
        "breadcrumbs": [],
    }


def extract_page_content(
    html: str, url: str, content_type: str = "", raw_bytes: bytes = b""
) -> Dict[str, object]:
    if raw_bytes and (
        "application/pdf" in (content_type or "").lower() or url.lower().endswith(".pdf")
    ):
        return extract_pdf_content(raw_bytes, url)
    soup = BeautifulSoup(html or "", "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "img", "form"]):
        tag.decompose()

    for tag in soup.find_all(["nav", "footer", "header", "aside"]):
        tag.decompose()

    for tag in soup.find_all(attrs={"class": re.compile(r"(nav|menu|footer|header)", re.IGNORECASE)}):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = _safe_text(soup.title.string)
    if not title:
        h1 = soup.find("h1")
        title = _safe_text(h1.get_text()) if h1 else "Untitled page"

    meta_description = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        meta_description = _safe_text(meta.get("content"))

    canonical_url = url
    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        canonical_url = canonical.get("href").strip()

    raw_text = _normalize_text(soup.get_text(separator="\n"))

    return {
        "title": title,
        "meta_description": meta_description,
        "canonical_url": canonical_url,
        "cleaned_text": raw_text,
        "headings": _extract_headings(soup),
        "breadcrumbs": _find_breadcrumbs(soup),
    }
