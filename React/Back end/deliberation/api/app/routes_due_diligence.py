import html as html_lib
import io
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode

import requests

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .db import get_active_database, get_driver

router = APIRouter()


class CompetitorCreate(BaseModel):
    name: str = Field(min_length=1)
    competitor_type: str = Field(alias="competitorType")
    notes: Optional[str] = ""


class CompetitorOut(BaseModel):
    competitor_id: str = Field(alias="competitorId")
    name: str
    competitor_type: str = Field(alias="competitorType")
    notes: str = ""
    updated_at: Optional[str] = Field(alias="updatedAt", default=None)


class DueDiligenceSummaryOut(BaseModel):
    competitors: int


class DueDiligenceCaseCreate(BaseModel):
    subject: Optional[str] = None
    subject_georgian: Optional[str] = Field(default=None, alias="subjectGeorgian")
    subject_english: Optional[str] = Field(default=None, alias="subjectEnglish")
    subject_type: str = Field(default="Person", alias="subjectType")
    status: Optional[str] = "Draft"
    owner: Optional[str] = ""


class DueDiligenceCaseUpdate(BaseModel):
    subject: Optional[str] = None
    subject_georgian: Optional[str] = Field(default=None, alias="subjectGeorgian")
    subject_english: Optional[str] = Field(default=None, alias="subjectEnglish")
    subject_type: Optional[str] = Field(default=None, alias="subjectType")
    status: Optional[str] = None
    owner: Optional[str] = None


class DueDiligenceCaseOut(BaseModel):
    case_id: str = Field(alias="caseId")
    subject: str
    subject_georgian: Optional[str] = Field(alias="subjectGeorgian", default="")
    subject_english: Optional[str] = Field(alias="subjectEnglish", default="")
    subject_type: str = Field(alias="subjectType")
    status: str
    owner: Optional[str] = ""
    created_at: Optional[str] = Field(alias="createdAt", default=None)
    updated_at: Optional[str] = Field(alias="updatedAt", default=None)
    last_report_id: Optional[str] = Field(alias="lastReportId", default=None)
    last_risk_level: Optional[str] = Field(alias="lastRiskLevel", default=None)
    last_total_hits: Optional[int] = Field(alias="lastTotalHits", default=None)
    last_report_at: Optional[str] = Field(alias="lastReportAt", default=None)
    task_count: Optional[int] = Field(alias="taskCount", default=None)


class DueDiligenceTaskCreate(BaseModel):
    label: str = Field(min_length=1)
    status: Optional[str] = "Open"
    assignee: Optional[str] = ""
    due_date: Optional[str] = Field(default=None, alias="dueDate")


class DueDiligenceTaskUpdate(BaseModel):
    label: Optional[str] = None
    status: Optional[str] = None
    assignee: Optional[str] = None
    due_date: Optional[str] = Field(default=None, alias="dueDate")


class DueDiligenceTaskOut(BaseModel):
    task_id: str = Field(alias="taskId")
    label: str
    status: str
    assignee: Optional[str] = ""
    due_date: Optional[str] = Field(default=None, alias="dueDate")
    created_at: Optional[str] = Field(alias="createdAt", default=None)
    updated_at: Optional[str] = Field(alias="updatedAt", default=None)


class DueDiligenceDecisionCreate(BaseModel):
    outcome: str = Field(min_length=1)
    rationale: Optional[str] = ""
    decided_by: Optional[str] = Field(default="", alias="decidedBy")


class DueDiligenceDecisionOut(BaseModel):
    decision_id: str = Field(alias="decisionId")
    outcome: str
    rationale: Optional[str] = ""
    decided_at: Optional[str] = Field(alias="decidedAt", default=None)
    decided_by: Optional[str] = Field(alias="decidedBy", default=None)


class DueDiligenceAnalysisRequest(BaseModel):
    subject: str = Field(min_length=1)
    subject_type: str = Field(default="Person", alias="subjectType")
    case_id: Optional[str] = Field(default=None, alias="caseId")
    use_wikidata: bool = Field(default=False, alias="useWikidata")
    use_wikipedia: bool = Field(default=True, alias="useWikipedia")
    use_opensanctions: bool = Field(default=True, alias="useOpenSanctions")
    use_news: bool = Field(default=True, alias="useNews")
    use_declarations: bool = Field(default=True, alias="useDeclarations")
    max_news: int = Field(default=8, alias="maxNews", ge=1, le=20)
    use_local_media: bool = Field(default=True, alias="useLocalMedia")
    media_source_ids: List[str] = Field(default_factory=lambda: ["netgazeti", "publika", "interpressnews"], alias="mediaSourceIds")
    media_topics: List[str] = Field(default_factory=list, alias="mediaTopics")
    media_max_results: int = Field(default=12, alias="mediaMaxResults", ge=1, le=50)
    demo: bool = Field(default=True)


class WikidataResult(BaseModel):
    id: str
    label: str
    description: Optional[str] = ""
    url: Optional[str] = ""


class OpenSanctionsResult(BaseModel):
    id: str
    name: str
    schema: Optional[str] = ""
    datasets: List[str] = []
    topics: List[str] = []
    score: Optional[float] = None
    url: Optional[str] = ""


class NewsResult(BaseModel):
    title: str
    url: str
    source: Optional[str] = ""
    published_at: Optional[str] = Field(default=None, alias="publishedAt")
    tone: Optional[float] = None


class AssetDeclarationResult(BaseModel):
    id: str
    name: str
    organization: Optional[str] = ""
    position: Optional[str] = ""
    birth_date: Optional[str] = Field(default="", alias="birthDate")
    declaration_submit_date: Optional[str] = Field(default="", alias="declarationSubmitDate")
    date_edited: Optional[str] = Field(default="", alias="dateEdited")
    source_url: Optional[str] = Field(default="", alias="sourceUrl")
    summary: Dict[str, Any] = {}
    raw: Dict[str, Any] = {}


class WikipediaResult(BaseModel):
    title: str
    summary: Optional[str] = ""
    url: Optional[str] = ""


class DebatePrepRequest(BaseModel):
    opponent: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    years_back: int = Field(default=2, alias="yearsBack", ge=1, le=10)
    max_results: int = Field(default=25, alias="maxResults", ge=5, le=100)
    use_wikipedia: bool = Field(default=True, alias="useWikipedia")
    use_google: bool = Field(default=True, alias="useGoogle")
    use_local_media: bool = Field(default=True, alias="useLocalMedia")
    demo: bool = Field(default=True)


class DebatePrepMention(BaseModel):
    title: str
    url: str
    source: Optional[str] = ""
    published_at: Optional[str] = Field(default=None, alias="publishedAt")
    tone: Optional[float] = None
    snippet: Optional[str] = ""


class DebatePrepTheme(BaseModel):
    name: str
    count: int
    examples: List[str] = []
    keywords: List[str] = []


class DebatePrepOut(BaseModel):
    opponent: str
    topic: str
    years_back: int = Field(alias="yearsBack")
    start_date: str = Field(alias="startDate")
    end_date: str = Field(alias="endDate")
    query: str
    keywords: List[str]
    wikipedia: List[WikipediaResult]
    mentions: List[DebatePrepMention]
    themes: List[DebatePrepTheme]
    warnings: List[str]


class DueDiligenceAnalysisOut(BaseModel):
    subject: str
    subject_type: str = Field(alias="subjectType")
    case_id: Optional[str] = Field(default=None, alias="caseId")
    wikidata: List[WikidataResult]
    wikipedia: List[WikipediaResult] = []
    opensanctions: List[OpenSanctionsResult]
    news: List[NewsResult]
    declarations: List[AssetDeclarationResult] = []
    media: Optional[Dict[str, object]] = None
    ai_report: Optional[Dict[str, object]] = Field(default=None, alias="aiReport")
    sources: List[str] = []
    summary: Dict[str, object]
    warnings: List[str]
    report_id: Optional[str] = Field(default=None, alias="reportId")
    stored_at: Optional[str] = Field(default=None, alias="storedAt")


class DueDiligenceReportListOut(BaseModel):
    report_id: str = Field(alias="reportId")
    case_id: Optional[str] = Field(alias="caseId", default=None)
    subject: str
    subject_type: str = Field(alias="subjectType")
    risk_level: Optional[str] = Field(default=None, alias="riskLevel")
    total_hits: Optional[int] = Field(default=None, alias="totalHits")
    created_at: Optional[str] = Field(default=None, alias="createdAt")
    sources: List[str] = []


class DueDiligenceReportOut(BaseModel):
    report_id: str = Field(alias="reportId")
    case_id: Optional[str] = Field(alias="caseId", default=None)
    subject: str
    subject_type: str = Field(alias="subjectType")
    created_at: Optional[str] = Field(default=None, alias="createdAt")
    payload: Dict[str, object]


class MediaSourceOut(BaseModel):
    source_id: str = Field(alias="sourceId")
    name: str
    source_type: str = Field(alias="sourceType")
    status: str
    url: str
    notes: str = ""
    access_model: str = Field(alias="accessModel")


class MediaMonitorRequest(BaseModel):
    subject: str = Field(min_length=1)
    subject_type: str = Field(default="Person", alias="subjectType")
    case_id: Optional[str] = Field(default=None, alias="caseId")
    topics: List[str] = []
    source_ids: List[str] = Field(default_factory=lambda: ["netgazeti", "publika", "interpressnews"], alias="sourceIds")
    max_results: int = Field(default=12, alias="maxResults", ge=1, le=50)
    persist: bool = True


class MediaQuoteOut(BaseModel):
    text: str
    speaker: Optional[str] = ""
    topic: Optional[str] = ""


class MediaMentionOut(BaseModel):
    title: str
    url: str
    source: str
    source_id: str = Field(alias="sourceId")
    published_at: Optional[str] = Field(default=None, alias="publishedAt")
    snippet: str = ""
    matched_topics: List[str] = Field(default_factory=list, alias="matchedTopics")
    quotes: List[MediaQuoteOut] = []
    stored: bool = False


class MediaMonitorOut(BaseModel):
    subject: str
    subject_type: str = Field(alias="subjectType")
    sources: List[MediaSourceOut]
    mentions: List[MediaMentionOut]
    warnings: List[str]
    stored_count: int = Field(alias="storedCount")


class DueDiligenceAiReportRequest(BaseModel):
    subject: str = Field(min_length=1)
    subject_type: str = Field(default="Person", alias="subjectType")
    topic: str = Field(default="General")
    case_id: Optional[str] = Field(default=None, alias="caseId")
    analysis: Optional[Dict[str, object]] = None
    media: Optional[Dict[str, object]] = None


class DueDiligenceAiReportOut(BaseModel):
    subject: str
    subject_type: str = Field(alias="subjectType")
    topic: str
    generated_at: str = Field(alias="generatedAt")
    mode: str
    report_title: Optional[str] = Field(default=None, alias="reportTitle")
    classification: Optional[str] = None
    report_metadata: Dict[str, object] = Field(default_factory=dict, alias="reportMetadata")
    sections: List[Dict[str, object]] = Field(default_factory=list)
    evidence_table: List[Dict[str, object]] = Field(default_factory=list, alias="evidenceTable")
    limitations: List[str] = []
    executive_summary: str = Field(alias="executiveSummary")
    key_findings: List[str] = Field(alias="keyFindings")
    topic_assessment: str = Field(alias="topicAssessment")
    risk_assessment: str = Field(alias="riskAssessment")
    evidence: List[Dict[str, str]]
    recommended_actions: List[str] = Field(alias="recommendedActions")
    caveats: List[str]
    warnings: List[str]


class MetaContentLibraryInfoOut(BaseModel):
    status: str
    fit_for_due_diligence: str = Field(alias="fitForDueDiligence")
    access_steps: List[str] = Field(alias="accessSteps")
    eligible_users: str = Field(alias="eligibleUsers")
    integration_plan: List[str] = Field(alias="integrationPlan")
    limitations: List[str]
    source_url: str = Field(alias="sourceUrl")


def _execute_read(session, query: str, params: Optional[dict] = None):
    if hasattr(session, "execute_read"):
        return session.execute_read(lambda tx: list(tx.run(query, params or {})))
    return session.read_transaction(lambda tx: list(tx.run(query, params or {})))


def _execute_write(session, query: str, params: Optional[dict] = None):
    def _run(tx):
        result = tx.run(query, params or {})
        return list(result)

    if hasattr(session, "execute_write"):
        return session.execute_write(_run)
    return session.write_transaction(_run)


def _db_session(driver):
    return driver.session(database=get_active_database())


def _safe_float(value) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _strip_html(value: str) -> str:
    cleaned = re.sub(r"<[^>]+>", "", str(value or ""))
    return html_lib.unescape(cleaned).strip()


def _normalize_text(value: str) -> str:
    return str(value or "").lower().strip()


CASE_STATUSES = {"Draft", "Active", "Review", "Decided", "Closed", "Archived"}
TASK_STATUSES = {"Open", "In Progress", "Blocked", "Done"}


def _normalize_subject_type(value: Optional[str]) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return "Person"
    if cleaned.lower() == "company":
        return "Organization"
    if cleaned.lower().startswith("org"):
        return "Organization"
    return "Person" if cleaned.lower().startswith("person") else cleaned.title()


def _normalize_case_status(value: Optional[str], default: str = "Draft") -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return default
    normalized = cleaned.title()
    if normalized not in CASE_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid case status")
    return normalized


def _normalize_task_status(value: Optional[str], default: str = "Open") -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return default
    normalized = cleaned.title()
    if normalized not in TASK_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid task status")
    return normalized


def _default_local_media_feeds() -> List[str]:
    env = str(os.getenv("LOCAL_MEDIA_RSS") or "").strip()
    if env:
        return [item.strip() for item in env.split(",") if item.strip()]
    return [
        "https://publika.ge/feed/",
        "https://netgazeti.ge/feed/",
    ]


def _media_sources() -> Dict[str, Dict[str, str]]:
    return {
        "netgazeti": {
            "sourceId": "netgazeti",
            "name": "Netgazeti",
            "sourceType": "online_media",
            "status": "active",
            "url": "https://netgazeti.ge/",
            "accessModel": "public_web_rss_search",
            "notes": "Uses Netgazeti public RSS and WordPress REST search; stores article metadata, excerpts, detected mentions, and quote snippets with source links.",
        },
        "publika": {
            "sourceId": "publika",
            "name": "Publika",
            "sourceType": "online_media",
            "status": "active",
            "url": "https://publika.ge/",
            "accessModel": "public_rss",
            "notes": "Uses Publika public RSS feed for recent article metadata, excerpts, detected mentions, and quote snippets.",
        },
        "interpressnews": {
            "sourceId": "interpressnews",
            "name": "Interpressnews",
            "sourceType": "online_media",
            "status": "active",
            "url": "https://www.interpressnews.ge/ka/",
            "accessModel": "public_web_search",
            "notes": "Uses public search pages when extractable; site markup may limit automated result extraction.",
        },
        "meta_content_library": {
            "sourceId": "meta_content_library",
            "name": "Meta Content Library/API",
            "sourceType": "social_platform_research_tool",
            "status": "access_required",
            "url": "https://transparency.meta.com/researchtools/meta-content-library/",
            "accessModel": "controlled_research_access",
            "notes": "Useful for Facebook/Instagram/Threads public-content analysis after approved researcher access; not enabled as an open commercial API connector.",
        },
    }


def _media_source_models(source_ids: Optional[List[str]] = None) -> List[MediaSourceOut]:
    sources = _media_sources()
    selected = source_ids or list(sources.keys())
    return [MediaSourceOut(**sources[source_id]) for source_id in selected if source_id in sources]


def _parse_rss_date(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return parsedate_to_datetime(text).isoformat()
    except (TypeError, ValueError):
        return text


def _match_topics(text: str, topics: List[str]) -> List[str]:
    haystack = _normalize_text(text)
    matches: List[str] = []
    for topic in topics or []:
        cleaned = str(topic or "").strip()
        if cleaned and _normalize_text(cleaned) in haystack:
            matches.append(cleaned)
    return matches


def _extract_media_quotes(text: str, topics: List[str], limit: int = 6) -> List[MediaQuoteOut]:
    cleaned = re.sub(r"\s+", " ", _strip_html(text or ""))
    quote_patterns = [r'ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¾([^ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â]{12,500})[ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â]', r'ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ([^ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â]{12,500})ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â', r'"([^"]{12,500})"']
    quotes: List[MediaQuoteOut] = []
    seen = set()
    for pattern in quote_patterns:
        for match in re.finditer(pattern, cleaned):
            quote = match.group(1).strip()
            key = quote.lower()
            if not quote or key in seen:
                continue
            seen.add(key)
            quote_topics = _match_topics(quote, topics)
            quotes.append(
                MediaQuoteOut(
                    text=quote,
                    speaker="",
                    topic=quote_topics[0] if quote_topics else "",
                )
            )
            if len(quotes) >= limit:
                return quotes
    return quotes


def _fetch_rss_media_mentions(
    *,
    source_id: str,
    source_name: str,
    feed_url: str,
    subject: str,
    topics: List[str],
    limit: int,
) -> Tuple[List[MediaMentionOut], Optional[str]]:
    headers = {"User-Agent": "FS-DueDiligence/1.0"}
    try:
        response = requests.get(feed_url, headers=headers, timeout=20)
        response.raise_for_status()
        response.encoding = "utf-8"
        root = ET.fromstring(response.text)
    except requests.RequestException as exc:
        return [], f"{source_name} RSS request failed: {exc}"
    except ET.ParseError as exc:
        return [], f"{source_name} RSS parse failed: {exc}"

    subject_key = _normalize_text(subject)
    mentions: List[MediaMentionOut] = []
    for item in root.findall(".//item"):
        title = str(item.findtext("title") or "").strip()
        link = str(item.findtext("link") or "").strip()
        description = _strip_html(item.findtext("description") or "")
        haystack = " ".join([title, description])
        if subject_key and subject_key not in _normalize_text(haystack):
            continue
        if not title or not link:
            continue
        mentions.append(
            MediaMentionOut(
                title=title,
                url=link,
                source=source_name,
                sourceId=source_id,
                publishedAt=_parse_rss_date(item.findtext("pubDate")),
                snippet=description[:600],
                matchedTopics=_match_topics(haystack, topics),
                quotes=_extract_media_quotes(haystack, topics),
            )
        )
        if len(mentions) >= limit:
            break
    return mentions, None


def _fetch_netgazeti_rss(subject: str, topics: List[str], limit: int) -> Tuple[List[MediaMentionOut], Optional[str]]:
    return _fetch_rss_media_mentions(
        source_id="netgazeti",
        source_name="Netgazeti",
        feed_url="https://netgazeti.ge/feed/",
        subject=subject,
        topics=topics,
        limit=limit,
    )


def _fetch_publika_media_mentions(subject: str, topics: List[str], limit: int) -> Tuple[List[MediaMentionOut], List[str]]:
    mentions, error = _fetch_rss_media_mentions(
        source_id="publika",
        source_name="Publika",
        feed_url="https://publika.ge/feed/",
        subject=subject,
        topics=topics,
        limit=limit,
    )
    return mentions, [error] if error else []


def _fetch_interpressnews_media_mentions(subject: str, topics: List[str], limit: int) -> Tuple[List[MediaMentionOut], List[str]]:
    warnings: List[str] = []
    query = quote(subject)
    urls = [
        f"https://www.interpressnews.ge/ka/search?search={query}",
        f"https://www.interpressnews.ge/ka/search?query={query}",
    ]
    headers = {"User-Agent": "FS-DueDiligence/1.0"}
    mentions: List[MediaMentionOut] = []
    seen = set()
    for url in urls:
        try:
            response = requests.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            response.encoding = "utf-8"
            html = response.text
        except requests.RequestException as exc:
            warnings.append(f"Interpressnews search request failed: {exc}")
            continue
        for match in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, flags=re.I | re.S):
            href = html_lib.unescape(match.group(1)).strip()
            raw_title = _strip_html(match.group(2))
            title = re.sub(r"\s+", " ", raw_title).strip()
            if not href or not title or len(title) < 8:
                continue
            if "/ka/" not in href and "interpressnews.ge" not in href:
                continue
            haystack = title
            if _normalize_text(subject) not in _normalize_text(haystack):
                continue
            if href.startswith("/"):
                href = f"https://www.interpressnews.ge{href}"
            key = href or title
            if key in seen:
                continue
            seen.add(key)
            mentions.append(
                MediaMentionOut(
                    title=title,
                    url=href,
                    source="Interpressnews",
                    sourceId="interpressnews",
                    publishedAt=None,
                    snippet="",
                    matchedTopics=_match_topics(haystack, topics),
                    quotes=[],
                )
            )
            if len(mentions) >= limit:
                return mentions, warnings
    if not mentions:
        warnings.append("Interpressnews search returned no extractable matches for the subject.")
    return mentions, warnings


def _fetch_netgazeti_search(subject: str, topics: List[str], limit: int) -> Tuple[List[MediaMentionOut], Optional[str]]:
    url = "https://netgazeti.ge/wp-json/wp/v2/posts"
    params = {
        "search": subject,
        "per_page": max(1, min(limit, 20)),
        "_fields": "date,link,title,excerpt",
    }
    headers = {"User-Agent": "FS-DueDiligence/1.0"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        return [], f"Netgazeti REST search failed: {exc}"
    except ValueError as exc:
        return [], f"Netgazeti REST search parse failed: {exc}"

    mentions: List[MediaMentionOut] = []
    for item in data if isinstance(data, list) else []:
        title = _strip_html((item.get("title") or {}).get("rendered") or "")
        link = str(item.get("link") or "").strip()
        excerpt = _strip_html((item.get("excerpt") or {}).get("rendered") or "")
        haystack = " ".join([title, excerpt])
        if not title or not link:
            continue
        mentions.append(
            MediaMentionOut(
                title=title,
                url=link,
                source="Netgazeti",
                sourceId="netgazeti",
                publishedAt=str(item.get("date") or "").strip() or None,
                snippet=excerpt[:600],
                matchedTopics=_match_topics(haystack, topics),
                quotes=_extract_media_quotes(haystack, topics),
            )
        )
        if len(mentions) >= limit:
            break
    return mentions, None


def _fetch_netgazeti_media_mentions(subject: str, topics: List[str], limit: int) -> Tuple[List[MediaMentionOut], List[str]]:
    warnings: List[str] = []
    rss_mentions, rss_error = _fetch_netgazeti_rss(subject, topics, limit)
    search_mentions, search_error = _fetch_netgazeti_search(subject, topics, max(0, limit - len(rss_mentions)))
    if rss_error and search_error and not (rss_mentions or search_mentions):
        warnings.extend([rss_error, search_error])
    seen = set()
    deduped: List[MediaMentionOut] = []
    for mention in [*rss_mentions, *search_mentions]:
        key = str(mention.url or mention.title).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(mention)
        if len(deduped) >= limit:
            break
    return deduped, warnings


def _store_media_mentions(
    *,
    subject: str,
    subject_type: str,
    case_id: Optional[str],
    topics: List[str],
    mentions: List[MediaMentionOut],
) -> int:
    if not mentions:
        return 0
    driver = get_driver()
    rows = [mention.dict(by_alias=True) for mention in mentions]
    query = """
    MERGE (p:DueDiligenceProfile {nameKey: toLower($subject), subjectType: $subjectType})
    ON CREATE SET p.profileId = randomUUID(), p.createdAt = datetime(), p.name = $subject
    SET p.name = $subject, p.updatedAt = datetime()
    WITH p
    UNWIND $mentions AS row
    WITH p, row,
         CASE
           WHEN size(coalesce(row.matchedTopics, [])) > 0 THEN row.matchedTopics
           WHEN size($topics) > 0 THEN $topics
           ELSE ['General']
         END AS topicNames
    MERGE (a:MediaArticle {url: row.url})
    ON CREATE SET a.articleId = randomUUID(), a.createdAt = datetime()
    SET a.title = row.title,
        a.source = row.source,
        a.sourceId = row.sourceId,
        a.publishedAt = row.publishedAt,
        a.snippet = row.snippet,
        a.updatedAt = datetime()
    MERGE (p)-[m:MENTIONED_IN]->(a)
    SET m.updatedAt = datetime(),
        m.topics = topicNames,
        m.caseId = $caseId
    WITH p, a, row, topicNames
    UNWIND topicNames AS topicName
    WITH p, a, row, trim(toString(topicName)) AS topicName
    WHERE topicName <> ''
    MERGE (t:Topic {nameKey: toLower(topicName)})
    ON CREATE SET t.topicId = randomUUID(), t.createdAt = datetime(), t.name = topicName
    SET t.name = topicName,
        t.domain = 'due_diligence',
        t.updatedAt = datetime()
    MERGE (p)-[pt:RELATED_TO_TOPIC]->(t)
    SET pt.subjectType = $subjectType,
        pt.caseId = $caseId,
        pt.updatedAt = datetime()
    MERGE (a)-[at:ABOUT_TOPIC]->(t)
    SET at.source = row.source,
        at.caseId = $caseId,
        at.updatedAt = datetime()
    MERGE (t)-[tm:HAS_MEDIA]->(a)
    SET tm.source = row.source,
        tm.caseId = $caseId,
        tm.updatedAt = datetime()
    WITH p, a, row, collect(DISTINCT t) AS articleTopics
    FOREACH (quoteRow IN coalesce(row.quotes, []) |
      MERGE (q:MediaQuote {textKey: toLower(quoteRow.text), articleUrl: row.url})
      ON CREATE SET q.quoteId = randomUUID(), q.createdAt = datetime()
      SET q.text = quoteRow.text,
          q.speaker = quoteRow.speaker,
          q.topic = quoteRow.topic,
          q.source = row.source,
          q.updatedAt = datetime()
      MERGE (a)-[:HAS_QUOTE]->(q)
      MERGE (p)-[:HAS_MEDIA_QUOTE]->(q)
      MERGE (q)-[:QUOTE_MENTIONS_PROFILE]->(p)
      FOREACH (topicNode IN articleTopics |
        MERGE (q)-[qt:QUOTE_ABOUT_TOPIC]->(topicNode)
        SET qt.updatedAt = datetime()
      )
    )
    WITH count(DISTINCT a) AS stored
    OPTIONAL MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
    FOREACH (_ IN CASE WHEN caseNode IS NULL THEN [] ELSE [1] END | SET caseNode.updatedAt = datetime())
    RETURN stored
    """
    params = {
        "subject": subject,
        "subjectType": subject_type,
        "caseId": case_id,
        "topics": topics,
        "mentions": rows,
    }
    with _db_session(driver) as session:
        records = _execute_write(session, query, params)
    row = records[0] if records else None
    return int(row.get("stored") or 0) if row else 0

def _wikidata_search(subject: str, limit: int = 5) -> Tuple[List[WikidataResult], Optional[str]]:
    url = "https://www.wikidata.org/w/api.php"
    params = {
        "action": "wbsearchentities",
        "search": subject,
        "language": "en",
        "format": "json",
        "limit": limit,
    }
    headers = {"User-Agent": "FS-DueDiligence/1.0"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        return [], f"Wikidata request failed: {exc}"
    results = []
    for item in data.get("search", []) or []:
        entity_id = str(item.get("id") or "").strip()
        results.append(
            WikidataResult(
                id=entity_id,
                label=str(item.get("label") or "").strip(),
                description=str(item.get("description") or "").strip(),
                url=str(item.get("concepturi") or item.get("url") or "").strip()
                or (f"https://www.wikidata.org/wiki/{entity_id}" if entity_id else ""),
            )
        )
    return results, None


def _wikipedia_search(query: str, limit: int = 4) -> Tuple[List[WikipediaResult], Optional[str]]:
    headers = {"User-Agent": "FS-DueDiligence/1.0"}
    results: List[WikipediaResult] = []
    errors: List[str] = []
    seen: set[str] = set()
    for lang, host in [("ka", "ka.wikipedia.org"), ("en", "en.wikipedia.org")]:
        url = f"https://{host}/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "format": "json",
        }
        try:
            response = requests.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            errors.append(f"{lang}: {exc}")
            continue
        for item in data.get("query", {}).get("search", []) or []:
            title = str(item.get("title") or "").strip()
            if not title or title.lower() in seen:
                continue
            seen.add(title.lower())
            snippet = _strip_html(item.get("snippet") or "")
            results.append(
                WikipediaResult(
                    title=title,
                    summary=snippet,
                    url=f"https://{host}/wiki/{quote(title.replace(' ', '_'))}",
                )
            )
            if len(results) >= limit:
                return results, None
    if errors and not results:
        return [], "Wikipedia request failed: " + "; ".join(errors)
    return results, None


def _opensanctions_search(
    subject: str, subject_type: str, limit: int = 5
) -> Tuple[List[OpenSanctionsResult], Optional[str]]:
    api_key = str(os.getenv("OPENSANCTIONS_API_KEY") or "").strip()
    if not api_key:
        return [], "OpenSanctions API key not configured."
    schema = "Person" if subject_type.lower().startswith("person") else "Organization"
    url = "https://api.opensanctions.org/search/default"
    params = {"q": subject, "schema": schema, "limit": limit}
    headers = {"Authorization": f"ApiKey {api_key}", "User-Agent": "FS-DueDiligence/1.0"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        return [], f"OpenSanctions request failed: {exc}"
    results = []
    for item in data.get("results", []) or []:
        entity = item.get("entity") or item
        entity_id = str(entity.get("id") or item.get("id") or "").strip()
        results.append(
            OpenSanctionsResult(
                id=entity_id or str(entity.get("entity_id") or ""),
                name=str(entity.get("caption") or entity.get("name") or item.get("caption") or "").strip(),
                schema=str(entity.get("schema") or item.get("schema") or "").strip(),
                datasets=list(entity.get("datasets") or item.get("datasets") or []),
                topics=list(entity.get("topics") or item.get("topics") or []),
                score=_safe_float(item.get("score")),
                url=f"https://www.opensanctions.org/entities/{entity_id}/" if entity_id else "",
            )
        )
    return results, None


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _pick_records(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("items", "results", "data", "declarations", "Declarations"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return [payload]


def _money_totals(rows: List[Dict[str, Any]], amount_keys: Tuple[str, ...] = ("Amount",)) -> Dict[str, float]:
    totals: Dict[str, float] = {}
    for row in rows:
        currency = str(row.get("Currency") or row.get("AmountCurrency") or row.get("IncomeCurrency") or "Unknown").strip() or "Unknown"
        amount = None
        for key in amount_keys:
            if row.get(key) is not None:
                amount = row.get(key)
                break
        try:
            numeric = float(amount)
        except (TypeError, ValueError):
            continue
        totals[currency] = round(totals.get(currency, 0.0) + numeric, 2)
    return totals


def _clean_decl_text(value: Any) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return " ".join(text.split())


def _decl_pick(row: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and _clean_decl_text(value):
            return _clean_decl_text(value)
    return ""


def _decl_person_name(row: Dict[str, Any], first_key: str = "OwnerFirstName", last_key: str = "OwnerLatsName") -> str:
    first = _decl_pick(row, first_key, "FirstName", "firstName")
    last = _decl_pick(row, last_key, "OwnerLastName", "LastName", "lastName")
    return " ".join(part for part in [first, last] if part).strip() or _decl_pick(row, "Name", "FullName")


def _decl_money(row: Dict[str, Any], *amount_keys: str) -> str:
    amount = None
    for key in amount_keys or ("Amount", "Price", "Income", "Share"):
        if row.get(key) is not None:
            amount = row.get(key)
            break
    if amount is None or str(amount).strip() == "":
        return ""
    currency = _decl_pick(row, "Currency", "CurrencyName", "AmountCurrency", "IncomeCurrency", "IncomeCurrencyName")
    return f"{amount} {currency}".strip()


def _decl_sample(rows: List[Dict[str, Any]], fields: Tuple[Tuple[str, Tuple[str, ...]], ...], limit: int = 6) -> List[Dict[str, str]]:
    output: List[Dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item: Dict[str, str] = {}
        for label, keys in fields:
            if label == "owner":
                value = _decl_person_name(row)
            elif label == "amount":
                value = _decl_money(row, *keys)
            else:
                value = _decl_pick(row, *keys)
            if value:
                item[label] = value
        if item:
            output.append(item)
        if len(output) >= limit:
            break
    return output


def _declaration_dossier(row: Dict[str, Any]) -> Dict[str, Any]:
    family = _as_list(row.get("FamilyMembers"))
    properties = _as_list(row.get("Properties"))
    movable = _as_list(row.get("MovableProperties"))
    securities = _as_list(row.get("Securities"))
    bank_accounts = _as_list(row.get("BankAccounts"))
    cashes = _as_list(row.get("Cashes"))
    jobs = _as_list(row.get("Jobs"))
    contracts = _as_list(row.get("Contracts"))
    gifts = _as_list(row.get("Gifts"))
    inouts = _as_list(row.get("InOuts"))
    enterprises = _as_list(row.get("Enterprice")) + _as_list(row.get("Enterprise"))
    linked_enterprises = _as_list(row.get("LinkedEnterprice")) + _as_list(row.get("LinkedEnterprise"))
    education = _as_list(row.get("Education")) + _as_list(row.get("Educations"))
    return {
        "declarant": {
            "name": _declaration_name(row),
            "birthDate": _decl_pick(row, "BirthDate"),
            "birthPlace": _decl_pick(row, "BirthPlace"),
            "organization": _decl_pick(row, "Organisation", "Organization"),
            "position": _decl_pick(row, "Position"),
            "submitted": _decl_pick(row, "DeclarationSubmitDate"),
            "edited": _decl_pick(row, "DateEdited"),
        },
        "familyMembers": _decl_sample(family, (("name", ("Name", "FullName")), ("relation", ("Relationship", "RelationName", "Relation")), ("birthDate", ("BirthDate",)), ("position", ("Position",)))) or [
            {k: v for k, v in {"name": _decl_person_name(item, "FirstName", "LastName"), "relation": _decl_pick(item, "Relationship", "RelationName", "Relation"), "birthDate": _decl_pick(item, "BirthDate")}.items() if v}
            for item in family[:6]
            if isinstance(item, dict)
        ],
        "properties": _decl_sample(properties, (("owner", ()), ("type", ("PropertyType", "Type", "Kind")), ("address", ("Address", "Location", "City", "District")), ("area", ("Area", "Square", "LandArea")), ("share", ("Share", "Part")), ("acquired", ("PurchaseDate", "RegisterDate", "Date")), ("amount", ("Price", "Amount")))) ,
        "vehiclesAndMovable": _decl_sample(movable, (("owner", ()), ("type", ("PropertyType", "Type", "Kind")), ("details", ("Details", "Description", "Name", "Model")), ("acquired", ("PurchaseDate", "PurchaseYear", "RegisterDate")), ("amount", ("Price", "Amount")))) ,
        "businesses": _decl_sample(enterprises, (("name", ("Name", "EnterpriseName")), ("role", ("PartnershipFormName", "Role", "Position")), ("share", ("Share", "SharePct")), ("registered", ("RegisterDate",)), ("amount", ("Income", "Amount")))) ,
        "linkedBusinesses": _decl_sample(linked_enterprises, (("name", ("Name", "EnterpriseName")), ("relation", ("RelationName", "Relationship")), ("role", ("PartnershipFormName", "Role", "Position")), ("share", ("Share", "SharePct")), ("amount", ("Income", "Amount")))) ,
        "careerAndIncome": _decl_sample(jobs, (("owner", ()), ("organization", ("Organisation", "Organization")), ("position", ("Position",)), ("period", ("StartDate",)), ("endDate", ("EndDate",)), ("amount", ("Amount",)))) ,
        "contracts": _decl_sample(contracts, (("owner", ()), ("type", ("ContractType",)), ("subject", ("Subject",)), ("agency", ("Agency",)), ("period", ("StartDate",)), ("endDate", ("EndDate", "EndDateName")), ("amount", ("Amount",)), ("income", ("Income",)))) ,
        "bankAndCash": {
            "accounts": _decl_sample(bank_accounts, (("owner", ()), ("bank", ("BankName",)), ("type", ("AccountType",)), ("amount", ("Amount",))), 8),
            "cash": _decl_sample(cashes, (("owner", ()), ("amount", ("Amount",))), 6),
        },
        "gifts": _decl_sample(gifts, (("owner", ()), ("source", ("Source", "Giver", "From")), ("description", ("Description", "Comment", "GiftType")), ("amount", ("Amount",)))) ,
        "inOuts": _decl_sample(inouts, (("owner", ()), ("kind", ("InOutKind", "Kind")), ("amount", ("Amount",)))) ,
        "securities": _decl_sample(securities, (("owner", ()), ("issuer", ("Issuer", "Name")), ("type", ("SecurityType", "Type")), ("amount", ("Amount", "NominalValue")))) ,
        "education": _decl_sample(education, (("institution", ("Institution", "University", "School")), ("degree", ("Degree", "Qualification")), ("period", ("StartDate",)), ("endDate", ("EndDate",)))) ,
    }


def _declaration_name(row: Dict[str, Any]) -> str:
    first = str(row.get("FirstName") or "").strip()
    last = str(row.get("LastName") or "").strip()
    full = " ".join(part for part in [first, last] if part).strip()
    return full or str(row.get("Name") or row.get("FullName") or "").strip()


def _summarize_declaration(row: Dict[str, Any]) -> Dict[str, Any]:
    bank_accounts = _as_list(row.get("BankAccounts"))
    cashes = _as_list(row.get("Cashes"))
    jobs = _as_list(row.get("Jobs"))
    contracts = _as_list(row.get("Contracts"))
    properties = _as_list(row.get("Properties"))
    movable = _as_list(row.get("MovableProperties"))
    securities = _as_list(row.get("Securities"))
    gifts = _as_list(row.get("Gifts"))
    inouts = _as_list(row.get("InOuts"))
    family = _as_list(row.get("FamilyMembers"))
    enterprises = _as_list(row.get("Enterprice")) + _as_list(row.get("Enterprise"))
    linked_enterprises = _as_list(row.get("LinkedEnterprice")) + _as_list(row.get("LinkedEnterprise"))
    income_rows = []
    for contract in contracts:
        if isinstance(contract, dict) and contract.get("Income") is not None:
            income_rows.append({"Amount": contract.get("Income"), "Currency": contract.get("IncomeCurrency") or contract.get("Currency")})
    return {
        "counts": {
            "familyMembers": len(family),
            "properties": len(properties),
            "movableProperties": len(movable),
            "securities": len(securities),
            "bankAccounts": len(bank_accounts),
            "cashEntries": len(cashes),
            "jobs": len(jobs),
            "contracts": len(contracts),
            "gifts": len(gifts),
            "inOuts": len(inouts),
            "enterprises": len(enterprises),
            "linkedEnterprises": len(linked_enterprises),
        },
        "bankAccountTotals": _money_totals([row for row in bank_accounts if isinstance(row, dict)]),
        "cashTotals": _money_totals([row for row in cashes if isinstance(row, dict)]),
        "jobIncomeTotals": _money_totals([row for row in jobs if isinstance(row, dict)]),
        "contractAmountTotals": _money_totals([row for row in contracts if isinstance(row, dict)]),
        "contractIncomeTotals": _money_totals(income_rows),
        "inOutTotals": _money_totals([row for row in inouts if isinstance(row, dict)]),
        "giftTotals": _money_totals([row for row in gifts if isinstance(row, dict)]),
        "dossier": _declaration_dossier(row),
    }


def _declaration_source_url(row: Dict[str, Any]) -> str:
    for key in ("Url", "URL", "SourceUrl", "sourceUrl"):
        if row.get(key):
            return str(row.get(key))
    base = os.getenv("DECLARACIA_PUBLIC_URL", "https://declaration.gov.ge/").rstrip("/")
    declaration_id = row.get("Id") or row.get("id")
    return f"{base}/{declaration_id}" if declaration_id else base


def _normalize_declaration(row: Dict[str, Any]) -> AssetDeclarationResult:
    declaration_id = str(row.get("Id") or row.get("id") or row.get("DeclarationId") or _declaration_name(row) or "declaration")
    return AssetDeclarationResult(
        id=declaration_id,
        name=_declaration_name(row) or "Unknown declarant",
        organization=str(row.get("Organisation") or row.get("Organization") or "").strip(),
        position=str(row.get("Position") or "").strip(),
        birthDate=str(row.get("BirthDate") or "").strip(),
        declarationSubmitDate=str(row.get("DeclarationSubmitDate") or "").strip(),
        dateEdited=str(row.get("DateEdited") or "").strip(),
        sourceUrl=_declaration_source_url(row),
        summary=_summarize_declaration(row),
        raw=row,
    )


def _declaration_query_params(subject: str) -> Dict[str, Any]:
    parts = [part for part in subject.split() if part]
    first_name = parts[0] if parts else ""
    last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
    return {
        "Key": subject,
        "Firstname": first_name,
        "Lastname": last_name,
        "OrganizationIds": [],
        "PositionIds": [],
        "YearSelectedValues": [],
    }


def _asset_declaration_search(subject: str) -> Tuple[List[AssetDeclarationResult], Optional[str]]:
    endpoint = (
        os.getenv("DECLARACIA_API_URL")
        or os.getenv("DECLARATION_API_URL")
        or "https://declaration.acb.gov.ge/Api/Declarations"
    )
    headers = {"User-Agent": "FS-DueDiligence/1.0", "Accept": "application/json"}
    params = _declaration_query_params(subject)
    try:
        if "{query}" in endpoint:
            url = endpoint.replace("{query}", quote(subject))
            response = requests.get(url, headers=headers, timeout=20)
        else:
            response = requests.get(endpoint, params=params, headers=headers, timeout=20)
        response.raise_for_status()
        records = _pick_records(response.json())
        return [_normalize_declaration(row) for row in records[:5]], None
    except Exception as exc:
        return [], f"Declaration request failed: {exc}"


def _gdelt_news_search(
    subject: str, limit: int = 8
) -> Tuple[List[NewsResult], Optional[str]]:
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {"query": f'"{subject}"', "mode": "ArtList", "maxrecords": limit, "format": "json"}
    headers = {"User-Agent": "FS-DueDiligence/1.0"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        response = getattr(exc, "response", None)
        if getattr(response, "status_code", None) == 429:
            return [], "GDELT is temporarily rate-limiting requests (429). Local media fallback was attempted."
        return [], f"GDELT news request failed: {exc}"
    articles = data.get("articles") or data.get("results") or []
    results = []
    for item in articles:
        results.append(
            NewsResult(
                title=str(item.get("title") or "").strip(),
                url=str(item.get("url") or "").strip(),
                source=str(
                    item.get("sourceCountry")
                    or item.get("domain")
                    or item.get("source")
                    or ""
                ).strip(),
                publishedAt=str(item.get("seendate") or item.get("date") or "").strip() or None,
                tone=_safe_float(item.get("tone")),
            )
        )
    return results, None


def _local_media_subject_terms(subject: str) -> List[str]:
    cleaned = str(subject or "").strip()
    terms = [cleaned] if cleaned else []
    lower = cleaned.lower()
    aliases = []
    if "kobakhidze" in lower or "ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¾ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¹ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â®ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â«ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â" in cleaned:
        aliases.extend(["ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¾ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¾ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¹ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â®ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â«ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â", "ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¾ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¹ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â®ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â«ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â"])
    if "ivanishvili" in lower or "ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¨ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“" in cleaned:
        aliases.extend(["ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¹ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â«ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¨ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“", "ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¨ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“"])
    if "kaladze" in lower or "ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¾ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â«ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â" in cleaned:
        aliases.extend(["ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¾ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â®ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¾ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â«ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â", "ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¾ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â«ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â"])
    for alias in aliases:
        if alias and alias not in terms:
            terms.append(alias)
    return terms


def _local_media_news_search(subject: str, limit: int = 8) -> Tuple[List[NewsResult], List[str]]:
    warnings: List[str] = []
    results: List[NewsResult] = []
    seen = set()
    for term in _local_media_subject_terms(subject):
        if len(results) >= limit:
            break
        mentions: List[MediaMentionOut] = []
        for fetcher in (
            _fetch_netgazeti_media_mentions,
            _fetch_publika_media_mentions,
            _fetch_interpressnews_media_mentions,
        ):
            if len(results) + len(mentions) >= limit:
                break
            source_mentions, term_warnings = fetcher(term, [], max(1, limit - len(results) - len(mentions)))
            mentions.extend(source_mentions)
            warnings.extend(term_warnings)
        for mention in mentions:
            if not mention.title or not mention.url or mention.url in seen:
                continue
            seen.add(mention.url)
            results.append(
                NewsResult(
                    title=mention.title,
                    url=mention.url,
                    source=mention.source or "Netgazeti",
                    publishedAt=mention.published_at,
                    tone=None,
                )
            )
            if len(results) >= limit:
                break
    if results:
        warnings.append("Local media fallback used configured Georgian media sources for subject aliases/transliterations.")
    else:
        warnings.append("Local media fallback found no matches in configured Georgian media sources for the subject or known aliases.")
    return results, warnings


def _format_gdelt_datetime(value: datetime) -> str:
    return value.strftime("%Y%m%d%H%M%S")


def _topic_keywords(topic: str) -> List[str]:
    cleaned = str(topic or "").strip()
    lower = cleaned.lower()
    keywords: List[str] = []
    if any(term in lower for term in ["education", "school", "university", "teacher", "student"]):
        keywords = [
            "education",
            "school",
            "schools",
            "teacher",
            "teachers",
            "student",
            "students",
            "university",
            "higher education",
            "curriculum",
            "exam",
            "vocational",
            "scholarship",
        ]
    else:
        keywords = [cleaned]
    if cleaned and cleaned not in keywords:
        keywords.insert(0, cleaned)
    seen = set()
    deduped: List[str] = []
    for item in keywords:
        key = item.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped or [cleaned]


def _build_debate_query(opponent: str, topic: str) -> Tuple[str, List[str]]:
    keywords = _topic_keywords(topic)
    clauses = []
    for keyword in keywords:
        text = keyword.strip()
        if not text:
            continue
        if " " in text:
            clauses.append(f'"{text}"')
        else:
            clauses.append(text)
    topic_clause = " OR ".join(clauses) or topic
    query = f'"{opponent}" AND ({topic_clause})'
    return query, keywords


def _google_debate_search(
    opponent: str, topic: str, years_back: int, limit: int
) -> Tuple[List[DebatePrepMention], Dict[str, str], Optional[str]]:
    api_key = str(os.getenv("GOOGLE_SEARCH_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    cse_id = str(os.getenv("GOOGLE_CSE_ID") or os.getenv("GOOGLE_CX") or "").strip()
    if not api_key or not cse_id:
        return [], {}, "Google search API not configured (GOOGLE_SEARCH_API_KEY + GOOGLE_CSE_ID)."
    query = f'"{opponent}" "{topic}"'.strip()
    url = "https://www.googleapis.com/customsearch/v1"
    headers = {"User-Agent": "FS-DueDiligence/1.0"}
    results: List[DebatePrepMention] = []
    start = 1
    remaining = max(0, limit)
    date_restrict = f"y{years_back}" if years_back else None
    while remaining > 0 and start <= 91:
        batch = min(10, remaining)
        params = {"key": api_key, "cx": cse_id, "q": query, "num": batch, "start": start}
        if date_restrict:
            params["dateRestrict"] = date_restrict
        try:
            response = requests.get(url, params=params, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            return results, {}, f"Google search request failed: {exc}"
        error_info = data.get("error") if isinstance(data, dict) else None
        if error_info:
            message = error_info.get("message") if isinstance(error_info, dict) else None
            return results, {}, f"Google search request failed: {message or error_info}"
        items = data.get("items") or []
        if not items:
            break
        for item in items:
            link = str(item.get("link") or "").strip()
            title = str(item.get("title") or "").strip()
            if not link or not title:
                continue
            results.append(
                DebatePrepMention(
                    title=title,
                    url=link,
                    source=str(item.get("displayLink") or "").strip(),
                    publishedAt=None,
                    tone=None,
                    snippet=str(item.get("snippet") or "").strip(),
                )
            )
        remaining = limit - len(results)
        start += len(items)
        if len(items) < batch:
            break
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=365 * years_back)
    meta = {
        "query": query,
        "startDate": start_dt.date().isoformat(),
        "endDate": end_dt.date().isoformat(),
    }
    return results, meta, None


def _fetch_rss_mentions(
    feed_url: str, opponent: str, topic: str
) -> Tuple[List[DebatePrepMention], Optional[str]]:
    headers = {"User-Agent": "FS-DueDiligence/1.0"}
    try:
        response = requests.get(feed_url, headers=headers, timeout=20)
        response.raise_for_status()
        xml_text = response.text
        root = ET.fromstring(xml_text)
    except requests.RequestException as exc:
        return [], f"Local media RSS failed ({feed_url}): {exc}"
    except ET.ParseError as exc:
        return [], f"Local media RSS parse failed ({feed_url}): {exc}"

    channel = root.find("channel")
    channel_title = ""
    if channel is not None:
        channel_title = str(channel.findtext("title") or "").strip()

    opponent_key = _normalize_text(opponent)
    keywords = [_normalize_text(item) for item in _topic_keywords(topic)]
    mentions: List[DebatePrepMention] = []
    topic_mentions: List[DebatePrepMention] = []

    for item in root.findall(".//item"):
        title = str(item.findtext("title") or "").strip()
        link = str(item.findtext("link") or "").strip()
        pub_date = str(item.findtext("pubDate") or "").strip() or None
        description = _strip_html(item.findtext("description") or "")
        haystack = _normalize_text(" ".join([title, description]))
        if opponent_key and opponent_key not in haystack:
            continue
        if not title or not link:
            continue
        mention = DebatePrepMention(
            title=title,
            url=link,
            source=channel_title or feed_url,
            publishedAt=pub_date,
            tone=None,
            snippet=description,
        )
        mentions.append(mention)
        if keywords and any(keyword in haystack for keyword in keywords if keyword):
            topic_mentions.append(mention)
    if topic_mentions:
        return topic_mentions, None
    return mentions, None


def _gdelt_debate_search(
    opponent: str, topic: str, years_back: int, limit: int
) -> Tuple[List[DebatePrepMention], Dict[str, str], Optional[str]]:
    query, keywords = _build_debate_query(opponent, topic)
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=365 * years_back)
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {
        "query": query,
        "mode": "ArtList",
        "maxrecords": limit,
        "format": "json",
        "startdatetime": _format_gdelt_datetime(start_dt),
        "enddatetime": _format_gdelt_datetime(end_dt),
    }
    headers = {"User-Agent": "FS-DueDiligence/1.0"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        return [], {}, f"GDELT debate prep request failed: {exc}"
    articles = data.get("articles") or data.get("results") or []
    results = []
    for item in articles:
        results.append(
            DebatePrepMention(
                title=str(item.get("title") or "").strip(),
                url=str(item.get("url") or "").strip(),
                source=str(
                    item.get("sourceCountry")
                    or item.get("domain")
                    or item.get("source")
                    or ""
                ).strip(),
                publishedAt=str(item.get("seendate") or item.get("date") or "").strip() or None,
                tone=_safe_float(item.get("tone")),
            )
        )
    meta = {
        "query": query,
        "startDate": start_dt.date().isoformat(),
        "endDate": end_dt.date().isoformat(),
        "keywords": ", ".join(keywords),
    }
    return results, meta, None


def _topic_theme_definitions(topic: str) -> List[Tuple[str, List[str]]]:
    lower = str(topic or "").lower()
    base = [
        ("Policy & reform", ["policy", "reform", "law", "bill", "strategy", "plan"]),
        ("Funding & budgets", ["budget", "funding", "finance", "spending", "investment", "grant"]),
        ("Governance & accountability", ["ministry", "agency", "oversight", "audit", "regulation"]),
        ("Public response", ["protest", "strike", "union", "parents", "students"]),
    ]
    if any(term in lower for term in ["education", "school", "university", "teacher", "student"]):
        base.extend(
            [
                ("Teachers & workforce", ["teacher", "educator", "salary", "wage", "staff"]),
                ("Schools & infrastructure", ["school", "classroom", "facility", "building"]),
                ("Higher education", ["university", "college", "higher education", "research"]),
                ("Curriculum & standards", ["curriculum", "exam", "testing", "standards"]),
                ("Digital learning", ["digital", "online", "remote", "platform", "technology"]),
            ]
        )
    return base


def _build_debate_themes(
    mentions: List[DebatePrepMention], topic: str
) -> List[DebatePrepTheme]:
    themes = _topic_theme_definitions(topic)
    buckets: Dict[str, Dict[str, object]] = {}
    for name, keywords in themes:
        buckets[name] = {"count": 0, "examples": [], "keywords": keywords}

    other = {"count": 0, "examples": [], "keywords": []}
    for mention in mentions:
        title = str(mention.title or "").lower()
        matched = False
        for name, keywords in themes:
            if any(keyword in title for keyword in keywords):
                bucket = buckets[name]
                bucket["count"] += 1
                if len(bucket["examples"]) < 3 and mention.title:
                    bucket["examples"].append(mention.title)
                matched = True
                break
        if not matched:
            other["count"] += 1
            if len(other["examples"]) < 3 and mention.title:
                other["examples"].append(mention.title)

    output: List[DebatePrepTheme] = []
    for name, data in buckets.items():
        if data["count"]:
            output.append(
                DebatePrepTheme(
                    name=name,
                    count=int(data["count"]),
                    examples=list(data["examples"]),
                    keywords=list(data["keywords"]),
                )
            )
    if other["count"]:
        output.append(
            DebatePrepTheme(
                name="Other",
                count=int(other["count"]),
                examples=list(other["examples"]),
                keywords=[],
            )
        )
    output.sort(key=lambda item: item.count, reverse=True)
    return output


def _demo_debate_results(opponent: str, topic: str) -> List[DebatePrepMention]:
    topic_label = topic or "the topic"
    return [
        DebatePrepMention(
            title=f"{opponent} outlines {topic_label} reforms in parliamentary address",
            url="https://example.com/debate-prep/statement-1",
            source="Demo Wire",
            publishedAt="2025-12-01",
            tone=0.1,
        ),
        DebatePrepMention(
            title=f"Interview: {opponent} on funding priorities for {topic_label}",
            url="https://example.com/debate-prep/statement-2",
            source="Demo Journal",
            publishedAt="2025-08-14",
            tone=-0.05,
        ),
    ]


def _demo_results(subject: str) -> Dict[str, List[Dict[str, object]]]:
    subject_label = subject or "Subject"
    return {
        "wikidata": [
            {
                "id": "Q123456",
                "label": subject_label,
                "description": "Demo profile generated for due diligence walkthrough.",
                "url": "https://www.wikidata.org/wiki/Q123456",
            }
        ],
        "opensanctions": [
            {
                "id": "demo-entity-001",
                "name": subject_label,
                "schema": "Person",
                "datasets": ["sanctions", "peps"],
                "topics": ["sanction", "role.pep"],
                "score": 0.82,
                "url": "https://www.opensanctions.org/entities/demo-entity-001/",
            }
        ],
        "news": [
            {
                "title": f"{subject_label} mentioned in procurement review",
                "url": "https://example.com/news/procurement-review",
                "source": "Demo Briefing",
                "publishedAt": "2026-03-02",
                "tone": -0.3,
            },
            {
                "title": f"Civic groups call for transparency on {subject_label} contracts",
                "url": "https://example.com/news/transparency-call",
                "source": "Demo Wire",
                "publishedAt": "2026-03-01",
                "tone": 0.1,
            },
        ],
    }


def _build_summary(
    wikidata: List[WikidataResult],
    wikipedia: List[WikipediaResult],
    opensanctions: List[OpenSanctionsResult],
    news: List[NewsResult],
    declarations: List[AssetDeclarationResult],
    warnings: List[str],
    media_mentions: int = 0,
) -> Dict[str, object]:
    wikidata_hits = len(wikidata)
    wikipedia_hits = len(wikipedia)
    opensanctions_hits = len(opensanctions)
    news_hits = len(news)
    declaration_hits = len(declarations)
    media_hits = media_mentions
    total_hits = wikidata_hits + wikipedia_hits + opensanctions_hits + news_hits + declaration_hits + media_hits
    topics = {
        topic
        for row in opensanctions
        for topic in (row.topics or [])
        if isinstance(topic, str)
    }
    has_sanction = any(topic.startswith("sanction") for topic in topics)
    has_pep = any("pep" in topic for topic in topics)
    has_crime = any(topic.startswith("crime") for topic in topics)

    risk_score = 0
    rationale = []
    if wikipedia_hits:
        risk_score += 8
        rationale.append("Found Wikipedia profile/context matches.")
    if wikidata_hits:
        risk_score += 6
        rationale.append("Found Wikidata entity matches.")
    if news_hits:
        news_boost = min(35, 20 + news_hits * 2)
        risk_score += news_boost
        rationale.append("Recent news mentions detected.")
    if media_hits:
        media_boost = min(25, 10 + media_hits * 2)
        risk_score += media_boost
        rationale.append("Georgian media mentions detected across configured sources.")
    if declaration_hits:
        rationale.append("Public asset declaration profile found; review assets, income, contracts, and related parties.")
    if opensanctions_hits:
        risk_score += 50
        rationale.append("OpenSanctions matches found.")
    if has_sanction:
        risk_score += 20
        rationale.append("Sanctions-related topics present.")
    if has_pep:
        risk_score += 10
        rationale.append("Politically exposed person indicators.")
    if has_crime:
        risk_score += 10
        rationale.append("Crime-related topics present.")

    if opensanctions_hits and (news_hits or media_hits):
        risk_score += 5
        rationale.append("Cross-source signal overlap (media/news + sanctions).")

    risk_score = min(100, risk_score)
    if total_hits == 0:
        risk_level = "Unknown"
    elif risk_score >= 70:
        risk_level = "High"
    elif risk_score >= 40:
        risk_level = "Medium"
    else:
        risk_level = "Low"
    return {
        "wikidata_hits": wikidata_hits,
        "wikipedia_hits": wikipedia_hits,
        "opensanctions_hits": opensanctions_hits,
        "news_hits": news_hits,
        "media_hits": media_hits,
        "declaration_hits": declaration_hits,
        "total_hits": total_hits,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "risk_rationale": rationale,
        "warnings": warnings,
        "news_source": "GDELT",
        "opensanctions_available": bool(os.getenv("OPENSANCTIONS_API_KEY")),
    }


def _store_dd_report(
    *,
    subject: str,
    subject_type: str,
    summary: Dict[str, object],
    payload: Dict[str, object],
    sources: List[str],
    case_id: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    driver = get_driver()
    query = """
    CREATE (r:DueDiligenceReport)
    SET r.reportId = randomUUID(),
        r.subject = $subject,
        r.subjectType = $subjectType,
        r.createdAt = datetime(),
        r.riskLevel = $riskLevel,
        r.totalHits = $totalHits,
        r.wikidataHits = $wikidataHits,
        r.wikipediaHits = $wikipediaHits,
        r.opensanctionsHits = $opensanctionsHits,
        r.newsHits = $newsHits,
        r.declarationHits = $declarationHits,
        r.sources = $sources,
        r.summaryJson = $summaryJson,
        r.payloadJson = $payloadJson
    WITH r
    OPTIONAL MATCH (c:Competitor {nameKey: toLower($subject), competitorType: $subjectType})
    FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END | MERGE (c)-[:HAS_DD_REPORT]->(r))
    WITH r
    OPTIONAL MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
    FOREACH (
      _ IN CASE WHEN caseNode IS NULL THEN [] ELSE [1] END |
      MERGE (caseNode)-[:HAS_DD_REPORT]->(r)
      SET caseNode.updatedAt = datetime()
    )
    SET r.caseId = CASE WHEN $caseId IS NULL THEN r.caseId ELSE $caseId END
    RETURN r.reportId AS reportId, toString(r.createdAt) AS createdAt
    """
    params = {
        "subject": subject,
        "subjectType": subject_type,
        "riskLevel": summary.get("risk_level"),
        "totalHits": summary.get("total_hits"),
        "wikidataHits": summary.get("wikidata_hits"),
        "wikipediaHits": summary.get("wikipedia_hits"),
        "opensanctionsHits": summary.get("opensanctions_hits"),
        "newsHits": summary.get("news_hits"),
        "declarationHits": summary.get("declaration_hits"),
        "sources": sources,
        "summaryJson": json.dumps(summary),
        "payloadJson": json.dumps(payload),
        "caseId": case_id,
    }
    with _db_session(driver) as session:
        records = _execute_write(session, query, params)
    row = records[0] if records else None
    if not row:
        return None, None
    return row.get("reportId"), row.get("createdAt")


def _get_pdf_font_name() -> str:
    candidates = [
        (os.environ.get("DD_PDF_FONT_NAME") or "DDReportFont", os.environ.get("DD_PDF_FONT_PATH") or ""),
        ("FSGeorgianSylfaen", r"C:\Windows\Fonts\sylfaen.ttf"),
        ("FSUnicodeArial", r"C:\Windows\Fonts\arial.ttf"),
        ("FSUnicodeSegoe", r"C:\Windows\Fonts\SegUIVar.ttf"),
        ("FSDejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ("FSDejaVuSansCondensed", "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf"),
        ("FSNotoSansGeorgian", "/usr/share/fonts/truetype/noto/NotoSansGeorgian-Regular.ttf"),
        ("FSNotoSans", "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
        ("FSNotoSansGeorgianOpenType", "/usr/share/fonts/opentype/noto/NotoSansGeorgian-Regular.ttf"),
        ("FSFreeSans", "/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
        ("FSLocalNotoSansGeorgian", "/usr/local/share/fonts/NotoSansGeorgian-Regular.ttf"),
    ]
    for font_name, font_path in candidates:
        if not font_path or not os.path.exists(font_path):
            continue
        try:
            if font_name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(font_name, font_path))
            return font_name
        except Exception:
            continue
    return "Helvetica"

def _pdf_escape(value: object) -> str:
    return html_lib.escape("" if value is None else str(value)).replace("\n", "<br/>")


def _pdf_paragraph(value: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_pdf_escape(value), style)


_RAW_AI_SECTION_HEADINGS = {
    "raw sources",
    "raw source",
    "raw data",
    "raw evidence",
    "source payload",
    "json payload",
}


def _looks_like_raw_report_payload(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if "raw sources" in lowered:
        return True
    if not (text.startswith("{") or text.startswith("[")):
        return False
    markers = [
        '"subject"',
        '"subjecttype"',
        '"caseid"',
        '"wikidata"',
        '"wikipedia"',
        '"opensanctions"',
        '"declarations"',
        '"media"',
        '"news"',
    ]
    return any(marker in lowered for marker in markers)


def _sanitize_dd_ai_list(items: object) -> List[str]:
    if not isinstance(items, list):
        return []
    return [
        str(item)
        for item in items
        if str(item).strip() and not _looks_like_raw_report_payload(item)
    ]


def _sanitize_dd_ai_sections(sections: object) -> List[Dict[str, object]]:
    cleaned: List[Dict[str, object]] = []
    if not isinstance(sections, list):
        return cleaned
    for section in sections:
        if not isinstance(section, dict):
            continue
        heading = str(section.get("heading") or "Report Section").strip() or "Report Section"
        heading_key = heading.lower()
        if heading_key in _RAW_AI_SECTION_HEADINGS or "raw source" in heading_key:
            continue
        paragraphs = [
            str(item)
            for item in (section.get("paragraphs") or [])
            if str(item).strip() and not _looks_like_raw_report_payload(item)
        ]
        bullets = [
            str(item)
            for item in (section.get("bullets") or [])
            if str(item).strip() and not _looks_like_raw_report_payload(item)
        ]
        if not paragraphs and not bullets and heading_key == "report section":
            continue
        cleaned_section: Dict[str, object] = {"heading": heading}
        if paragraphs:
            cleaned_section["paragraphs"] = paragraphs
        if bullets:
            cleaned_section["bullets"] = bullets
        cleaned.append(cleaned_section)
    return cleaned


def _build_report_pdf(report: Dict[str, object]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER, title="Due Diligence Report")
    styles = getSampleStyleSheet()
    pdf_font = _get_pdf_font_name()
    title_style = ParagraphStyle("TitleUnicode", parent=styles["Title"], fontName=pdf_font)
    header_style = ParagraphStyle("Header", parent=styles["Heading2"], fontName=pdf_font, spaceAfter=6)
    body_style = ParagraphStyle("BodyUnicode", parent=styles["BodyText"], fontName=pdf_font)
    mono_style = ParagraphStyle(
        "Mono", parent=styles["BodyText"], fontName=pdf_font, fontSize=9, leading=11
    )

    summary = report.get("summary") or {}
    rationale = summary.get("risk_rationale") or []
    warnings = report.get("warnings") or []
    ai_report = report.get("aiReport") or report.get("ai_report") or {}
    if isinstance(ai_report, dict):
        ai_sections = ai_report.get("sections") or []
        ai_key_findings = _sanitize_dd_ai_list(ai_report.get("keyFindings") or [])
        ai_actions = _sanitize_dd_ai_list(ai_report.get("recommendedActions") or [])
        ai_limitations = _sanitize_dd_ai_list(ai_report.get("limitations") or ai_report.get("caveats") or [])
    else:
        ai_sections = []
        ai_key_findings = []
        ai_actions = []
        ai_limitations = []

    ai_sections = _sanitize_dd_ai_sections(ai_sections)

    if not ai_sections:
        fallback_compact = _compact_dd_evidence(
            report,
            report.get("media") if isinstance(report.get("media"), dict) else None,
        )
        fallback_report = _fallback_dd_ai_report(
            str(report.get("subject") or "Subject"),
            str(report.get("subjectType") or report.get("subject_type") or "Person"),
            "General",
            fallback_compact,
            [str(w) for w in warnings if str(w).strip()],
        )
        ai_sections = _sanitize_dd_ai_sections(fallback_report.get("sections") or [])
        ai_key_findings = _sanitize_dd_ai_list(fallback_report.get("keyFindings") or [])
        ai_actions = _sanitize_dd_ai_list(fallback_report.get("recommendedActions") or [])
        ai_limitations = _sanitize_dd_ai_list(fallback_report.get("limitations") or fallback_report.get("caveats") or [])

    rendered_section_headings = {
        str(section.get("heading") or "").strip().lower()
        for section in ai_sections
        if isinstance(section, dict)
    }

    story = [
        Paragraph(_pdf_escape((ai_report if isinstance(ai_report, dict) else {}).get("reportTitle") or f"Due Diligence Brief: {report.get('subject') or 'Subject'}"), title_style),
        Paragraph(f"Subject: <b>{_pdf_escape(report.get('subject'))}</b>", body_style),
        Paragraph(f"Type: {_pdf_escape(report.get('subjectType'))}", body_style),
        Paragraph(f"Generated: {_pdf_escape(report.get('createdAt'))}", body_style),
        Spacer(1, 10),
    ]

    summary_table = Table(
        [
            ["Risk level", _pdf_paragraph(summary.get("risk_level", "Unknown"), body_style)],
            ["Risk score", _pdf_paragraph(summary.get("risk_score", "-"), body_style)],
            ["Total signals reviewed", _pdf_paragraph(summary.get("total_hits", 0), body_style)],
        ],
        colWidths=[140, 360],
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 0), (-1, -1), pdf_font),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.extend([Paragraph("Summary", header_style), summary_table, Spacer(1, 12)])

    if rationale:
        story.append(Paragraph("Risk rationale", header_style))
        rationale_text = "<br/>".join([_pdf_escape(item) for item in rationale])
        story.append(Paragraph(rationale_text, body_style))
        story.append(Spacer(1, 12))

    if warnings:
        story.append(Paragraph("Warnings", header_style))
        warning_text = "<br/>".join([_pdf_escape(w) for w in warnings])
        story.append(Paragraph(warning_text, body_style))
        story.append(Spacer(1, 12))

    story.append(Paragraph("Analyst Brief", header_style))
    if ai_sections:
        for section in ai_sections:
            if not isinstance(section, dict):
                continue
            heading = section.get("heading") or "Report Section"
            story.append(Paragraph(_pdf_escape(heading), header_style))
            for paragraph in section.get("paragraphs") or []:
                if str(paragraph).strip():
                    story.append(_pdf_paragraph(paragraph, body_style))
                    story.append(Spacer(1, 6))
            bullets = [str(item) for item in (section.get("bullets") or []) if str(item).strip()]
            if bullets:
                bullet_text = "<br/>".join([f"- {_pdf_escape(item)}" for item in bullets])
                story.append(Paragraph(bullet_text, body_style))
                story.append(Spacer(1, 8))
    else:
        story.append(Paragraph("The scan did not produce enough structured findings for a narrative report.", body_style))
        story.append(Spacer(1, 8))

    if ai_key_findings and "key findings" not in rendered_section_headings:
        story.append(Paragraph("Key Findings", header_style))
        findings_text = "<br/>".join([f"- {_pdf_escape(item)}" for item in ai_key_findings if str(item).strip()])
        story.append(Paragraph(findings_text, body_style))
        story.append(Spacer(1, 10))

    if ai_actions and "recommended actions" not in rendered_section_headings:
        story.append(Paragraph("Recommended Actions", header_style))
        actions_text = "<br/>".join([f"- {_pdf_escape(item)}" for item in ai_actions if str(item).strip()])
        story.append(Paragraph(actions_text, body_style))
        story.append(Spacer(1, 10))

    if ai_limitations and "limitations" not in rendered_section_headings:
        story.append(Paragraph("Limitations", header_style))
        limitations_text = "<br/>".join([f"- {_pdf_escape(item)}" for item in ai_limitations if str(item).strip()])
        story.append(Paragraph(limitations_text, body_style))
        story.append(Spacer(1, 10))

    story.append(Paragraph("Reviewer Note", header_style))
    story.append(
        Paragraph(
            "This report is an analyst-facing summary generated from the DD scan. "
            "Use it for review and decision support, and validate important claims before action.",
            body_style,
        )
    )

    doc.build(story)
    return buffer.getvalue()


@router.get("/summary", response_model=DueDiligenceSummaryOut)
def due_diligence_summary():
    driver = get_driver()
    query = "MATCH (c:Competitor) RETURN count(c) AS competitors"
    with _db_session(driver) as session:
        records = _execute_read(session, query)
    row = records[0] if records else {}
    return {"competitors": int(row.get("competitors") or 0)}


@router.get("/competitors", response_model=List[CompetitorOut])
def list_competitors(limit: int = Query(50, ge=1, le=200)):
    driver = get_driver()
    query = """
    MATCH (c:Competitor)
    RETURN
      c.competitorId AS competitorId,
      c.name AS name,
      c.competitorType AS competitorType,
      coalesce(c.notes, '') AS notes,
      toString(c.updatedAt) AS updatedAt
    ORDER BY c.updatedAt DESC
    LIMIT $limit
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query, {"limit": int(limit)})
    return [record.data() for record in records]


@router.post("/competitors", response_model=CompetitorOut)
def upsert_competitor(payload: CompetitorCreate):
    competitor_type = (payload.competitor_type or "").strip()
    if competitor_type not in {"Person", "Company"}:
        raise HTTPException(status_code=400, detail="competitorType must be Person or Company")
    name = payload.name.strip()
    notes = (payload.notes or "").strip()
    driver = get_driver()
    query = """
    MERGE (c:Competitor {nameKey: toLower($name), competitorType: $competitorType})
    ON CREATE SET c.competitorId = randomUUID(), c.createdAt = datetime()
    SET c.name = $name,
        c.notes = $notes,
        c.updatedAt = datetime()
    RETURN
      c.competitorId AS competitorId,
      c.name AS name,
      c.competitorType AS competitorType,
      coalesce(c.notes, '') AS notes,
      toString(c.updatedAt) AS updatedAt
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {"name": name, "competitorType": competitor_type, "notes": notes},
        )
    if not records:
        raise HTTPException(status_code=500, detail="Competitor upsert failed")
    return records[0].data()


@router.delete("/competitors/{competitor_id}")
def delete_competitor(competitor_id: str):
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            "MATCH (c:Competitor {competitorId: $id}) DETACH DELETE c",
            {"id": competitor_id},
        )
    return {"deleted": True, "competitor_id": competitor_id}


def _watchlist_match_score(query: str, name: str) -> float:
    """Higher is better: exact, substring, token overlap, partial token match."""
    q = _normalize_text(query)
    n = _normalize_text(name)
    if not q or not n:
        return 0.0
    if q == n:
        return 100.0
    if q in n or n in q:
        return 85.0
    q_tokens = {t for t in q.split() if len(t) >= 2}
    n_tokens = {t for t in n.split() if len(t) >= 2}
    if not q_tokens:
        return 0.0
    overlap = len(q_tokens & n_tokens)
    if overlap:
        return 45.0 + min(45.0, overlap * 12.0)
    for qt in q_tokens:
        if len(qt) < 3:
            continue
        for nt in n_tokens:
            if qt in nt or nt in qt:
                return 28.0
    return 0.0


@router.get("/watchlist-matches", response_model=List[CompetitorOut])
def watchlist_matches(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
):
    """Rank watchlist (Competitor) rows by relevance to the query (server-side)."""
    driver = get_driver()
    query = """
    MATCH (c:Competitor)
    RETURN
      c.competitorId AS competitorId,
      c.name AS name,
      c.competitorType AS competitorType,
      coalesce(c.notes, '') AS notes,
      toString(c.updatedAt) AS updatedAt
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query)
    rows = [record.data() for record in records]
    scored = []
    for row in rows:
        score = _watchlist_match_score(q, str(row.get("name") or ""))
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda item: (-item[0], str(item[1].get("name") or "")))
    return [item[1] for item in scored[: int(limit)]]


@router.get("/media-sources", response_model=List[MediaSourceOut])
def list_media_sources():
    return _media_source_models()


@router.get("/meta-content-library", response_model=MetaContentLibraryInfoOut)
def meta_content_library_info():
    return {
        "status": "research_access_required",
        "fitForDueDiligence": (
            "Strong fit for public narrative, misinformation, amplification, and relationship evidence "
            "once approved access is available. It should be treated as a controlled source, not a default public feed."
        ),
        "eligibleUsers": (
            "Meta says applicants need affiliation with an academic institution or a non-profit/public-interest "
            "research organization; applications are independently reviewed by CASD."
        ),
        "accessSteps": [
            "Confirm the research program and organization eligibility.",
            "Apply through Meta Research Tools Manager from a desktop/laptop.",
            "If approved, use Meta Content Library for manual review and Content Library API for Python/R analysis in the approved secure environment.",
            "Export only allowed evidence/aggregate findings and attach source links or approved references to due diligence profiles.",
        ],
        "integrationPlan": [
            "Keep this app connector-gated until credentials/access are approved.",
            "Model Meta results with the same Profile, MediaArticle, MediaMention, and Quote objects used for Netgazeti.",
            "Add a visibility limitation warning whenever Meta access is unavailable or incomplete.",
        ],
        "limitations": [
            "Not a simple open API for general commercial scraping.",
            "API use happens inside approved secure computing environments.",
            "Public content coverage varies by platform, account type, follower threshold, geography, and available fields.",
        ],
        "sourceUrl": "https://transparency.meta.com/researchtools/meta-content-library/",
    }


def _run_media_monitor(
    *,
    subject: str,
    subject_type: str,
    case_id: Optional[str],
    topics: List[str],
    source_ids: Optional[List[str]],
    max_results: int,
    persist: bool,
) -> Dict[str, object]:
    source_ids = source_ids or ["netgazeti", "publika", "interpressnews"]
    warnings: List[str] = []
    mentions: List[MediaMentionOut] = []
    enabled_sources = _media_source_models(source_ids)
    unknown_sources = [source_id for source_id in source_ids if source_id not in _media_sources()]
    if unknown_sources:
        warnings.append(f"Unknown media source ids ignored: {', '.join(unknown_sources)}")

    media_fetchers = {
        "netgazeti": _fetch_netgazeti_media_mentions,
        "publika": _fetch_publika_media_mentions,
        "interpressnews": _fetch_interpressnews_media_mentions,
    }
    selected_fetchers = [(source_id, fetcher) for source_id, fetcher in media_fetchers.items() if source_id in source_ids]
    per_source_limit = max(1, min(max_results, (max_results + max(1, len(selected_fetchers)) - 1) // max(1, len(selected_fetchers))))
    for source_id, fetcher in selected_fetchers:
        source_mentions, source_warnings = fetcher(subject, topics, per_source_limit)
        mentions.extend(source_mentions)
        warnings.extend(source_warnings)

    if "meta_content_library" in source_ids:
        warnings.append(
            "Meta Content Library/API requires approved research access; no live Meta query was run."
        )

    seen = set()
    deduped: List[MediaMentionOut] = []
    for mention in mentions:
        key = str(mention.url or mention.title or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(mention)
        if len(deduped) >= max_results:
            break
    mentions = deduped

    stored_count = 0
    if persist and mentions:
        try:
            stored_count = _store_media_mentions(
                subject=subject,
                subject_type=subject_type,
                case_id=case_id.strip() if case_id else None,
                topics=topics,
                mentions=mentions,
            )
            for mention in mentions:
                mention.stored = True
        except Exception as exc:
            warnings.append(f"Media evidence was fetched but could not be stored: {exc}")

    if not mentions:
        warnings.append("No mentions found in the currently available Georgian media sources.")
    return {
        "subject": subject,
        "subjectType": subject_type,
        "sources": [source.dict(by_alias=True) for source in enabled_sources],
        "mentions": [mention.dict(by_alias=True) for mention in mentions],
        "warnings": warnings,
        "storedCount": stored_count,
    }


@router.post("/media-monitor", response_model=MediaMonitorOut)
def media_monitor(payload: MediaMonitorRequest):
    subject = payload.subject.strip()
    if not subject:
        raise HTTPException(status_code=400, detail="Subject is required")
    subject_type = _normalize_subject_type(payload.subject_type)
    topics = [str(item or "").strip() for item in payload.topics if str(item or "").strip()]
    return _run_media_monitor(
        subject=subject,
        subject_type=subject_type,
        case_id=payload.case_id,
        topics=topics,
        source_ids=payload.source_ids,
        max_results=payload.max_results,
        persist=payload.persist,
    )


def _extract_json_payload(text: str) -> Dict[str, object]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except ValueError:
            return {}
    return {}


def _compact_dd_evidence(analysis: Optional[Dict[str, object]], media: Optional[Dict[str, object]]) -> Dict[str, object]:
    analysis = analysis or {}
    media = media or {}
    wikidata = list(analysis.get("wikidata") or [])[:5]
    wikipedia = list(analysis.get("wikipedia") or [])[:5]
    opensanctions = list(analysis.get("opensanctions") or [])[:5]
    news = list(analysis.get("news") or [])[:10]
    declarations = []
    for row in list(analysis.get("declarations") or [])[:5]:
        if not isinstance(row, dict):
            continue
        summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
        declarations.append({
            "id": row.get("id"),
            "name": row.get("name"),
            "organization": row.get("organization"),
            "position": row.get("position"),
            "birthDate": row.get("birthDate"),
            "declarationSubmitDate": row.get("declarationSubmitDate"),
            "dateEdited": row.get("dateEdited"),
            "sourceUrl": row.get("sourceUrl"),
            "summary": {
                "counts": summary.get("counts") or {},
                "bankAccountTotals": summary.get("bankAccountTotals") or {},
                "cashTotals": summary.get("cashTotals") or {},
                "jobIncomeTotals": summary.get("jobIncomeTotals") or {},
                "contractAmountTotals": summary.get("contractAmountTotals") or {},
                "contractIncomeTotals": summary.get("contractIncomeTotals") or {},
                "inOutTotals": summary.get("inOutTotals") or {},
                "giftTotals": summary.get("giftTotals") or {},
                "dossier": summary.get("dossier") or {},
            },
        })
    mentions = list(media.get("mentions") or [])[:12]
    evidence: List[Dict[str, str]] = []
    for row in news:
        evidence.append({
            "source": str(row.get("source") or "News/Web"),
            "title": str(row.get("title") or "Untitled"),
            "url": str(row.get("url") or ""),
            "date": str(row.get("publishedAt") or row.get("published_at") or ""),
            "snippet": "",
        })
    for row in mentions:
        evidence.append({
            "source": str(row.get("source") or "Media"),
            "title": str(row.get("title") or "Untitled"),
            "url": str(row.get("url") or ""),
            "date": str(row.get("publishedAt") or row.get("published_at") or ""),
            "snippet": str(row.get("snippet") or "")[:500],
        })
    return {
        "summary": analysis.get("summary") or {},
        "warnings": list(analysis.get("warnings") or []) + list(media.get("warnings") or []),
        "wikidata": wikidata,
        "wikipedia": wikipedia,
        "opensanctions": opensanctions,
        "declarations": declarations,
        "news": news,
        "media_mentions": mentions,
        "evidence": evidence[:18],
    }


def _fallback_dd_ai_report(subject: str, subject_type: str, topic: str, compact: Dict[str, object], warnings: List[str]) -> Dict[str, object]:
    summary = compact.get("summary") or {}
    wikidata = compact.get("wikidata") or []
    wikipedia = compact.get("wikipedia") or []
    opensanctions = compact.get("opensanctions") or []
    declarations = compact.get("declarations") or []
    evidence = compact.get("evidence") or []
    risk_level = str(summary.get("risk_level") or "Unknown")
    risk_score = summary.get("risk_score")
    total_hits = int(summary.get("total_hits") or len(evidence) or 0)
    topic_label = (topic or "General").strip() or "General"
    topic_l = topic_label.lower()
    topic_hits = []
    for row in evidence:
        haystack = " ".join([str(row.get("title") or ""), str(row.get("snippet") or "")]).lower()
        if topic_l and topic_l != "general" and topic_l in haystack:
            topic_hits.append(row)
    if not topic_hits:
        topic_hits = evidence[:5]

    coverage_notes = []
    if wikipedia or wikidata:
        coverage_notes.append("Profile and identity context was available from encyclopedic sources.")
    if opensanctions:
        coverage_notes.append("Watchlist-style screening returned possible matches that require identity verification.")
    if declarations:
        coverage_notes.append("Public asset declaration records were available for review.")
    if topic_hits:
        coverage_notes.append("Media or news material was available for the selected review scope.")
    if not coverage_notes:
        coverage_notes.append("The configured sources returned limited material for this subject at scan time.")

    key_findings = [
        f"The scan found {total_hits} signal(s) that may require analyst review.",
        f"The automated risk level is {risk_level}; treat this as triage guidance, not a final decision.",
    ]
    if wikipedia:
        key_findings.append("Wikipedia returned profile context that should be checked against the subject's Georgian and English names.")
    if wikidata:
        key_findings.append("Wikidata returned identity context that can help with alias and entity disambiguation.")
    if opensanctions:
        key_findings.append("OpenSanctions returned possible match(es); confirm identity before using them in a conclusion.")
    if declarations:
        key_findings.append("Asset declaration records should be reviewed for roles, ownership, income, and related-party patterns.")
    if topic_hits:
        key_findings.append(f"Relevant source material was available for the review scope: {topic_label}.")

    executive = (
        f"This brief summarizes the due diligence scan for {subject} ({subject_type}). "
        f"The current automated risk level is {risk_level}"
        + (f" with a score of {risk_score}" if risk_score is not None else "")
        + ". The purpose of the report is to help an analyst identify what should be verified before a case decision."
    )
    coverage = " ".join(coverage_notes)
    topic_assessment = (
        f"For the review scope '{topic_label}', the scan identified {len(topic_hits)} item(s) that may support further assessment. "
        "Where material is indirect, ambiguous, or based on similar names, it should be treated as context rather than a finding."
    )
    risk_assessment = (
        f"Risk is currently assessed as {risk_level}. Escalation should depend on confirmed identity, source relevance, recency, "
        "and whether the same concern appears across more than one independent signal."
    )
    declaration_bullets: List[str] = []
    for declaration in declarations[:3]:
        if not isinstance(declaration, dict):
            continue
        dossier = ((declaration.get("summary") or {}).get("dossier") or {}) if isinstance(declaration.get("summary"), dict) else {}
        counts = ((declaration.get("summary") or {}).get("counts") or {}) if isinstance(declaration.get("summary"), dict) else {}
        declarant = dossier.get("declarant") or {}
        submitted = declarant.get("submitted") or declaration.get("declarationSubmitDate") or declaration.get("dateEdited") or "unknown date"
        declaration_bullets.append(
            f"Declaration {submitted}: {counts.get('properties', 0)} properties, {counts.get('movableProperties', 0)} vehicles/movable assets, "
            f"{counts.get('enterprises', 0) + counts.get('linkedEnterprises', 0)} business links, {counts.get('familyMembers', 0)} family members, "
            f"{counts.get('jobs', 0)} job/income records, and {counts.get('contracts', 0)} contracts."
        )
        for job in (dossier.get("careerAndIncome") or [])[:3]:
            declaration_bullets.append(
                "Career/income: " + "; ".join(str(part) for part in [job.get("owner"), job.get("organization"), job.get("position"), job.get("amount")] if part)
            )
        for item in (dossier.get("properties") or [])[:3]:
            declaration_bullets.append(
                "Property: " + "; ".join(str(part) for part in [item.get("owner"), item.get("type"), item.get("address"), item.get("area"), item.get("share"), item.get("amount")] if part)
            )
        for item in (dossier.get("vehiclesAndMovable") or [])[:3]:
            declaration_bullets.append(
                "Vehicle/movable asset: " + "; ".join(str(part) for part in [item.get("owner"), item.get("type"), item.get("details"), item.get("amount")] if part)
            )
        for item in (dossier.get("businesses") or [])[:3]:
            declaration_bullets.append(
                "Business interest: " + "; ".join(str(part) for part in [item.get("name"), item.get("role"), item.get("share"), item.get("amount")] if part)
            )
        for item in (dossier.get("familyMembers") or [])[:3]:
            declaration_bullets.append(
                "Family member: " + "; ".join(str(part) for part in [item.get("name"), item.get("relation"), item.get("birthDate"), item.get("position")] if part)
            )
    actions = [
        "Confirm the subject identity against Georgian and English names before relying on any match.",
        "Review the highest-risk signals first and separate verified facts from contextual mentions.",
        "Record a short analyst conclusion explaining whether the signals support approval, escalation, or rejection.",
    ]
    caveats = [
        "Automated screening can miss relevant material because of rate limits, language variation, transliteration, and source availability.",
        "Similar names and organization aliases can create false positives.",
        "This report supports human review and should not be treated as a final legal or factual determination by itself.",
    ]
    sections = [
        {"heading": "Executive Summary", "paragraphs": [executive]},
        {"heading": "Source Coverage", "paragraphs": [coverage]},
        *([{"heading": "Asset Declaration Dossier", "bullets": declaration_bullets[:12]}] if declaration_bullets else []),
        {"heading": f"Assessment Scope: {topic_label}", "paragraphs": [topic_assessment]},
        {"heading": "Risk Assessment", "paragraphs": [risk_assessment]},
        {"heading": "Key Findings", "bullets": key_findings},
        {"heading": "Recommended Actions", "bullets": actions},
        {"heading": "Limitations", "bullets": caveats},
    ]
    return {
        "subject": subject,
        "subjectType": subject_type,
        "topic": topic_label,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": "fallback-structured",
        "reportTitle": f"Due Diligence Brief: {subject}",
        "classification": "Internal review",
        "reportMetadata": {
            "subject": subject,
            "subjectType": subject_type,
            "topic": topic_label,
            "riskLevel": risk_level,
            "riskScore": risk_score,
            "totalHits": total_hits,
        },
        "sections": sections,
        "evidenceTable": [],
        "limitations": caveats,
        "executiveSummary": executive,
        "keyFindings": key_findings,
        "topicAssessment": topic_assessment,
        "riskAssessment": risk_assessment,
        "evidence": [],
        "recommendedActions": actions,
        "caveats": caveats,
        "warnings": warnings,
    }


def _call_dd_ai_report(subject: str, subject_type: str, topic: str, compact: Dict[str, object]) -> Tuple[Optional[Dict[str, object]], Optional[str]]:
    api_key = (
        os.getenv("DD_LLM_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
        or os.getenv("LLM_API_KEY", "").strip()
    )
    api_url = (
        os.getenv("DD_LLM_API_URL", "").strip()
        or os.getenv("OPENAI_CHAT_COMPLETIONS_URL", "").strip()
        or os.getenv("LLM_API_URL", "").strip()
        or ("https://api.openai.com/v1/chat/completions" if api_key else "")
    )
    model = (
        os.getenv("DD_LLM_MODEL", "").strip()
        or os.getenv("OPENAI_MODEL", "").strip()
        or os.getenv("LLM_MODEL", "").strip()
        or "gpt-4.1-mini"
    )
    if not api_key or not api_url:
        return None, "LLM is not configured; generated a structured non-LLM report."
    prompt = {
        "task": "Draft a decision-ready due diligence report from the supplied evidence only.",
        "outputContract": {
            "format": "Return one valid JSON object only so the app can render it. The JSON values must contain finished, reader-facing report text; do not include markdown, code fences, raw payloads, or prose outside JSON.",
            "schema": {
                "reportTitle": "Due Diligence Report: <subject>",
                "classification": "Internal review",
                "reportMetadata": {"subject": "string", "subjectType": "string", "topic": "string", "riskLevel": "string", "generatedFor": "string"},
                "sections": [
                    {"heading": "Executive Summary", "paragraphs": ["ready-to-render report paragraphs"], "bullets": []},
                    {"heading": "Profile and Source Coverage", "paragraphs": ["what sources returned and what did not"], "bullets": []},
                    {"heading": "Assessment Scope: <topic>", "paragraphs": ["topic-specific assessment"], "bullets": []},
                    {"heading": "Risk Assessment", "paragraphs": ["risk interpretation with confidence limits"], "bullets": []}
                ],
                "evidenceTable": [],
                "limitations": ["coverage gaps, ambiguity, rate limits, language/transliteration issues, or false-positive risks"],
                "recommendedActions": ["specific verification or follow-up actions"],
                "executiveSummary": "same content as Executive Summary, retained for compatibility",
                "keyFindings": ["4-8 source-backed findings; retained for compatibility"],
                "topicAssessment": "same content as topic section, retained for compatibility",
                "riskAssessment": "same content as risk section, retained for compatibility",
                "evidence": [],
                "caveats": ["same content as limitations, retained for compatibility"],
            },
        },
        "subject": subject,
        "subjectType": subject_type,
        "topic": topic,
        "configuredSources": [
            "Wikipedia for profile/background context",
            "OpenSanctions for sanctions/PEP/watchlist signals",
            "Georgian asset declarations from declaration.acb.gov.ge",
            "Georgian media: Netgazeti, Publika, Interpressnews",
        ],
        "rawEvidence": compact,
        "analysisRules": [
            "Use only facts present in rawEvidence. Do not invent facts, quotes, dates, sanctions, assets, relationships, or allegations.",
            "Treat OpenSanctions results as possible matches until identity is verified; never state a sanctions/PEP match as confirmed unless the supplied evidence clearly supports it.",
            "Treat asset declarations as self-declared public records. Build a clear dossier section from declaration summaries: properties owned, vehicles/movable property, business interests, linked businesses, career/positions, yearly job income, contracts/loans/rent, bank/cash totals, gifts, family members, and family-member assets when present. Do not dump raw declaration JSON.",
            "Keep Georgian titles, organization names, and quotes in Georgian when present. You may explain their relevance in English.",
            "Separate evidence from interpretation: every key finding should be traceable to Wikipedia, OpenSanctions, declarations, or a named media source.",
            "If the selected topic is not directly supported by the evidence, say so clearly instead of stretching unrelated material.",
            "Prefer cautious analyst language: possible, reported, declared, appears, requires verification. Avoid legal conclusions or defamatory phrasing.",
            "Prioritize the most recent declaration, but mention meaningful older declaration records when they show career, income, property, business, or family-asset changes.",
            "If evidence is thin or sources returned zero results, make that a caveat and propose next verification steps.",
        ],
        "styleGuide": [
            "Concise, professional, readable for a non-technical decision maker.",
            "No generic filler. Each sentence should add a finding, limitation, or action.",
            "Do not create a raw sources section, article dump, JSON-looking prose, or evidence table in the report text.",
            "For asset declarations, write like a professional dossier: grouped headings, short conclusions, amounts with currencies, and clear caveats where ownership or family relationship needs verification.",
            "Do not overstate automated risk scores; explain what drove the signal.",
        ],
    }
    try:
        response = requests.post(
            api_url,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a careful due diligence analyst preparing neutral, source-grounded reports. You must return valid JSON only and must not invent unsupported facts."},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=float(os.getenv("DD_LLM_TIMEOUT", "8")),
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = _extract_json_payload(content)
        if not parsed:
            return None, "LLM returned an empty or invalid JSON report; generated fallback report."
        parsed["mode"] = f"ai:{model}"
        return parsed, None
    except Exception as exc:
        return None, f"LLM report failed ({type(exc).__name__}); generated fallback report."


def _prepare_dd_ai_report(subject: str, subject_type: str, topic: str, compact: Dict[str, object]) -> Dict[str, object]:
    warnings = [str(w) for w in (compact.get("warnings") or []) if str(w).strip()]
    ai_report, ai_warning = _call_dd_ai_report(subject, subject_type, topic, compact)
    if ai_warning:
        warnings.append(ai_warning)
    fallback = _fallback_dd_ai_report(subject, subject_type, topic, compact, warnings)
    if not ai_report:
        return fallback
    return {
        "subject": subject,
        "subjectType": subject_type,
        "topic": topic,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": str(ai_report.get("mode") or "ai"),
        "reportTitle": str(ai_report.get("reportTitle") or fallback.get("reportTitle") or f"Due Diligence Brief: {subject}"),
        "classification": str(ai_report.get("classification") or fallback.get("classification") or "Internal review"),
        "reportMetadata": dict(ai_report.get("reportMetadata") or fallback.get("reportMetadata") or {}),
        "sections": (_sanitize_dd_ai_sections(ai_report.get("sections") or fallback.get("sections") or []) or fallback.get("sections") or [])[:8],
        "evidenceTable": [],
        "limitations": _sanitize_dd_ai_list(ai_report.get("limitations") or ai_report.get("caveats") or fallback.get("limitations") or fallback["caveats"])[:8],
        "executiveSummary": str(ai_report.get("executiveSummary") or fallback["executiveSummary"]),
        "keyFindings": _sanitize_dd_ai_list(ai_report.get("keyFindings") or fallback["keyFindings"])[:8],
        "topicAssessment": str(ai_report.get("topicAssessment") or fallback["topicAssessment"]),
        "riskAssessment": str(ai_report.get("riskAssessment") or fallback["riskAssessment"]),
        "evidence": [],
        "recommendedActions": _sanitize_dd_ai_list(ai_report.get("recommendedActions") or fallback["recommendedActions"])[:8],
        "caveats": _sanitize_dd_ai_list(ai_report.get("caveats") or fallback["caveats"])[:8],
        "warnings": warnings,
    }

@router.post("/ai-report", response_model=DueDiligenceAiReportOut)
def generate_due_diligence_ai_report(payload: DueDiligenceAiReportRequest):
    subject = payload.subject.strip()
    if not subject:
        raise HTTPException(status_code=400, detail="Subject is required")
    subject_type = _normalize_subject_type(payload.subject_type)
    topic = payload.topic.strip() or "General"
    compact = _compact_dd_evidence(payload.analysis, payload.media)
    return _prepare_dd_ai_report(subject, subject_type, topic, compact)


@router.post("/analyze", response_model=DueDiligenceAnalysisOut)
def analyze_due_diligence(payload: DueDiligenceAnalysisRequest):
    subject = payload.subject.strip()
    if not subject:
        raise HTTPException(status_code=400, detail="Subject is required")
    case_id = payload.case_id.strip() if payload.case_id else None
    subject_type = _normalize_subject_type(payload.subject_type)
    warnings: List[str] = []
    source_notes: List[str] = []
    wikidata_results: List[WikidataResult] = []
    wikipedia_results: List[WikipediaResult] = []
    opensanctions_results: List[OpenSanctionsResult] = []
    news_results: List[NewsResult] = []
    declaration_results: List[AssetDeclarationResult] = []
    media_result: Optional[Dict[str, object]] = None
    local_media_used = False

    if payload.use_wikidata:
        wikidata_results, error = _wikidata_search(subject)
        if error:
            warnings.append(error)

    if payload.use_wikipedia:
        wikipedia_results, error = _wikipedia_search(subject)
        if error:
            warnings.append(error)

    if payload.use_opensanctions:
        opensanctions_results, error = _opensanctions_search(subject, subject_type)
        if error:
            warnings.append(error)

    if payload.use_news:
        news_results, error = _gdelt_news_search(subject, payload.max_news)
        if error:
            warnings.append(error)
        if not news_results:
            local_news, local_warnings = _local_media_news_search(subject, payload.max_news)
            if local_news:
                news_results = local_news
                local_media_used = True
            warnings.extend(local_warnings)

    if payload.use_declarations:
        declaration_results, error = _asset_declaration_search(subject)
        if error:
            warnings.append(error)

    if payload.use_local_media:
        media_topics = [str(item or "").strip() for item in payload.media_topics if str(item or "").strip()]
        media_result = _run_media_monitor(
            subject=subject,
            subject_type=subject_type,
            case_id=case_id,
            topics=media_topics,
            source_ids=payload.media_source_ids,
            max_results=payload.media_max_results,
            persist=True,
        )
        warnings.extend(str(item) for item in media_result.get("warnings") or [])

    if payload.demo and (payload.use_wikidata or payload.use_wikipedia or payload.use_opensanctions or payload.use_news) and not (
        wikidata_results or wikipedia_results or opensanctions_results or news_results or declaration_results
    ):
        demo = _demo_results(subject)
        if payload.use_wikidata:
            wikidata_results = [WikidataResult(**row) for row in demo["wikidata"]]
        if payload.use_opensanctions:
            opensanctions_results = [OpenSanctionsResult(**row) for row in demo["opensanctions"]]
        if payload.use_news:
            news_results = [NewsResult(**row) for row in demo["news"]]
        warnings.append("Demo data used for selected external sources.")

    if local_media_used:
        kept_warnings: List[str] = []
        for warning in warnings:
            if warning.startswith("GDELT is temporarily rate-limiting"):
                source_notes.append("GDELT is temporarily rate-limited; Netgazeti was used instead.")
            elif warning.startswith("Local media fallback used configured Georgian media sources"):
                source_notes.append("Configured Georgian media sources matched the subject using local aliases/transliterations.")
            else:
                kept_warnings.append(warning)
        warnings = kept_warnings

    media_mentions = len((media_result or {}).get("mentions") or [])
    summary = _build_summary(
        wikidata_results,
        wikipedia_results,
        opensanctions_results,
        news_results,
        declaration_results,
        warnings,
        media_mentions=media_mentions,
    )
    if media_result:
        summary["media_source"] = "Configured Georgian media"
        summary["media_sources"] = [source.get("name") for source in media_result.get("sources") or [] if isinstance(source, dict)]
    if payload.use_news:
        summary["news_source"] = "GDELT + Georgian media" if local_media_used else "GDELT"
    if source_notes:
        summary["source_notes"] = source_notes
    sources = []
    if payload.use_wikidata:
        sources.append("Wikidata")
    if payload.use_wikipedia:
        sources.append("Wikipedia")
    if payload.use_opensanctions:
        sources.append("OpenSanctions")
    if payload.use_news:
        sources.append("GDELT")
        if local_media_used:
            sources.extend(["Netgazeti", "Publika", "Interpressnews"])
    if payload.use_declarations:
        sources.append("Asset Declarations")
    if payload.use_local_media:
        for source in (media_result.get("sources", []) if media_result else []):
            if isinstance(source, dict) and source.get("name") and source.get("name") not in sources:
                sources.append(str(source.get("name")))

    ai_topic = "General"
    analysis_for_ai = {
        "subject": subject,
        "subjectType": subject_type,
        "caseId": case_id,
        "wikidata": [row.dict(by_alias=True) for row in wikidata_results],
        "wikipedia": [row.dict(by_alias=True) for row in wikipedia_results],
        "opensanctions": [row.dict(by_alias=True) for row in opensanctions_results],
        "news": [row.dict(by_alias=True) for row in news_results],
        "declarations": [row.dict(by_alias=True) for row in declaration_results],
        "media": media_result,
        "sources": sources,
        "summary": summary,
        "warnings": warnings,
    }
    ai_report = _prepare_dd_ai_report(
        subject,
        subject_type,
        ai_topic,
        _compact_dd_evidence(analysis_for_ai, media_result),
    )

    payload_blob = {
        "subject": subject,
        "subjectType": subject_type,
        "caseId": case_id,
        "wikidata": [row.dict(by_alias=True) for row in wikidata_results],
        "wikipedia": [row.dict(by_alias=True) for row in wikipedia_results],
        "opensanctions": [row.dict(by_alias=True) for row in opensanctions_results],
        "news": [row.dict(by_alias=True) for row in news_results],
        "declarations": [row.dict(by_alias=True) for row in declaration_results],
        "media": media_result,
        "aiReport": ai_report,
        "sources": sources,
        "summary": summary,
        "warnings": warnings,
    }
    report_id, stored_at = _store_dd_report(
        subject=subject,
        subject_type=subject_type,
        summary=summary,
        payload=payload_blob,
        sources=sources,
        case_id=case_id,
    )

    return {
        "subject": subject,
        "subjectType": subject_type,
        "caseId": case_id,
        "wikidata": wikidata_results,
        "wikipedia": wikipedia_results,
        "opensanctions": opensanctions_results,
        "news": news_results,
        "declarations": declaration_results,
        "media": media_result,
        "aiReport": ai_report,
        "sources": sources,
        "summary": summary,
        "warnings": warnings,
        "reportId": report_id,
        "storedAt": stored_at,
    }


@router.post("/debate-prep", response_model=DebatePrepOut)
def debate_prep(payload: DebatePrepRequest):
    opponent = payload.opponent.strip()
    topic = payload.topic.strip()
    if not opponent or not topic:
        raise HTTPException(status_code=400, detail="Opponent and topic are required")
    warnings: List[str] = [
        "Results are public sources. Open sources to verify direct quotes."
    ]
    mentions: List[DebatePrepMention] = []
    meta: Dict[str, str] = {}
    wikipedia_results: List[WikipediaResult] = []
    if payload.use_google:
        mentions, meta, error = _google_debate_search(
            opponent, topic, payload.years_back, payload.max_results
        )
        if error:
            warnings.append(error)
    else:
        mentions, meta, error = _gdelt_debate_search(
            opponent, topic, payload.years_back, payload.max_results
        )
        if error:
            warnings.append(error)
    if payload.use_wikipedia:
        wikipedia_results, error = _wikipedia_search(opponent, limit=4)
        if error:
            warnings.append(error)
    if payload.use_local_media:
        local_mentions: List[DebatePrepMention] = []
        for feed_url in _default_local_media_feeds():
            rss_mentions, error = _fetch_rss_mentions(feed_url, opponent, topic)
            if error:
                warnings.append(error)
            if rss_mentions:
                local_mentions.extend(rss_mentions)
        if local_mentions:
            mentions.extend(local_mentions)
    if payload.demo and not mentions:
        mentions = _demo_debate_results(opponent, topic)
        warnings.append("Demo data used for debate prep.")
        meta = {
            "query": f'"{opponent}" AND "{topic}"',
            "startDate": (datetime.now(timezone.utc) - timedelta(days=365 * payload.years_back))
            .date()
            .isoformat(),
            "endDate": datetime.now(timezone.utc).date().isoformat(),
            "keywords": topic,
        }
    query, keywords = _build_debate_query(opponent, topic)
    if mentions:
        seen = set()
        deduped: List[DebatePrepMention] = []
        for item in mentions:
            key = str(item.url or item.title or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        mentions = deduped
    themes = _build_debate_themes(mentions, topic)
    return {
        "opponent": opponent,
        "topic": topic,
        "yearsBack": payload.years_back,
        "startDate": meta.get("startDate")
        or (datetime.now(timezone.utc) - timedelta(days=365 * payload.years_back)).date().isoformat(),
        "endDate": meta.get("endDate") or datetime.now(timezone.utc).date().isoformat(),
        "query": meta.get("query") or query,
        "keywords": [keyword.strip() for keyword in (meta.get("keywords") or "").split(",") if keyword.strip()]
        or keywords,
        "wikipedia": wikipedia_results,
        "mentions": mentions,
        "themes": themes,
        "warnings": warnings,
    }



def _case_display_subject(subject: Optional[str], subject_georgian: Optional[str], subject_english: Optional[str]) -> str:
    current = str(subject or "").strip()
    ka = str(subject_georgian or "").strip()
    en = str(subject_english or "").strip()
    return current or ka or en


@router.get("/cases", response_model=List[DueDiligenceCaseOut])
def list_due_diligence_cases(
    status: Optional[str] = Query(None),
    subject: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    driver = get_driver()
    normalized_status = _normalize_case_status(status) if status else None
    subject_filter = subject.strip() if subject else None
    if subject_filter == "":
        subject_filter = None
    query = """
    MATCH (c:DueDiligenceCase)
    WHERE ($status IS NULL OR c.status = $status)
      AND (
        $subject IS NULL
        OR toLower(coalesce(c.subject, '')) CONTAINS toLower($subject)
        OR toLower(coalesce(c.subjectGeorgian, '')) CONTAINS toLower($subject)
        OR toLower(coalesce(c.subjectEnglish, '')) CONTAINS toLower($subject)
      )
    OPTIONAL MATCH (c)-[:HAS_DD_REPORT]->(r:DueDiligenceReport)
    WITH c, r ORDER BY r.createdAt DESC
    WITH c, collect(r)[0] AS latest
    OPTIONAL MATCH (c)-[:HAS_TASK]->(t:DueDiligenceTask)
    WITH c, latest, count(t) AS taskCount
    ORDER BY c.updatedAt DESC
    RETURN
      c.caseId AS caseId,
      c.subject AS subject,
      coalesce(c.subjectGeorgian, '') AS subjectGeorgian,
      coalesce(c.subjectEnglish, '') AS subjectEnglish,
      c.subjectType AS subjectType,
      c.status AS status,
      coalesce(c.owner, '') AS owner,
      toString(c.createdAt) AS createdAt,
      toString(c.updatedAt) AS updatedAt,
      latest.reportId AS lastReportId,
      latest.riskLevel AS lastRiskLevel,
      latest.totalHits AS lastTotalHits,
      toString(latest.createdAt) AS lastReportAt,
      taskCount AS taskCount
    LIMIT $limit
    """
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            query,
            {
                "status": normalized_status,
                "subject": subject_filter,
                "limit": int(limit),
            },
        )
    return [record.data() for record in records]


@router.post("/cases", response_model=DueDiligenceCaseOut)
def create_due_diligence_case(payload: DueDiligenceCaseCreate):
    subject_georgian = str(payload.subject_georgian or "").strip()
    subject_english = str(payload.subject_english or "").strip()
    subject = _case_display_subject(payload.subject, subject_georgian, subject_english)
    if not subject:
        raise HTTPException(status_code=400, detail="At least one subject name is required")
    subject_type = _normalize_subject_type(payload.subject_type)
    status = _normalize_case_status(payload.status)
    owner = str(payload.owner or "").strip()
    driver = get_driver()
    query = """
    CREATE (c:DueDiligenceCase)
    SET c.caseId = randomUUID(),
        c.subject = $subject,
        c.subjectGeorgian = $subjectGeorgian,
        c.subjectEnglish = $subjectEnglish,
        c.subjectType = $subjectType,
        c.status = $status,
        c.owner = $owner,
        c.createdAt = datetime(),
        c.updatedAt = datetime()
    RETURN
      c.caseId AS caseId,
      c.subject AS subject,
      coalesce(c.subjectGeorgian, '') AS subjectGeorgian,
      coalesce(c.subjectEnglish, '') AS subjectEnglish,
      c.subjectType AS subjectType,
      c.status AS status,
      coalesce(c.owner, '') AS owner,
      toString(c.createdAt) AS createdAt,
      toString(c.updatedAt) AS updatedAt,
      null AS lastReportId,
      null AS lastRiskLevel,
      null AS lastTotalHits,
      null AS lastReportAt,
      0 AS taskCount
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "subject": subject,
                "subjectGeorgian": subject_georgian,
                "subjectEnglish": subject_english,
                "subjectType": subject_type,
                "status": status,
                "owner": owner,
            },
        )
    if not records:
        raise HTTPException(status_code=500, detail="Case creation failed")
    return records[0].data()


@router.get("/cases/{case_id}", response_model=DueDiligenceCaseOut)
def get_due_diligence_case(case_id: str):
    driver = get_driver()
    query = """
    MATCH (c:DueDiligenceCase {caseId: $caseId})
    OPTIONAL MATCH (c)-[:HAS_DD_REPORT]->(r:DueDiligenceReport)
    WITH c, r ORDER BY r.createdAt DESC
    WITH c, collect(r)[0] AS latest
    OPTIONAL MATCH (c)-[:HAS_TASK]->(t:DueDiligenceTask)
    RETURN
      c.caseId AS caseId,
      c.subject AS subject,
      coalesce(c.subjectGeorgian, '') AS subjectGeorgian,
      coalesce(c.subjectEnglish, '') AS subjectEnglish,
      c.subjectType AS subjectType,
      c.status AS status,
      coalesce(c.owner, '') AS owner,
      toString(c.createdAt) AS createdAt,
      toString(c.updatedAt) AS updatedAt,
      latest.reportId AS lastReportId,
      latest.riskLevel AS lastRiskLevel,
      latest.totalHits AS lastTotalHits,
      toString(latest.createdAt) AS lastReportAt,
      count(t) AS taskCount
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query, {"caseId": case_id})
    if not records:
        raise HTTPException(status_code=404, detail="Case not found")
    return records[0].data()


@router.patch("/cases/{case_id}", response_model=DueDiligenceCaseOut)
def update_due_diligence_case(case_id: str, payload: DueDiligenceCaseUpdate):
    subject_georgian = str(payload.subject_georgian).strip() if payload.subject_georgian is not None else None
    subject_english = str(payload.subject_english).strip() if payload.subject_english is not None else None
    subject = payload.subject.strip() if payload.subject else None
    if subject is None and (subject_georgian is not None or subject_english is not None):
        subject = _case_display_subject(None, subject_georgian, subject_english)
    subject_type = (
        _normalize_subject_type(payload.subject_type) if payload.subject_type else None
    )
    status = _normalize_case_status(payload.status) if payload.status else None
    owner = str(payload.owner).strip() if payload.owner is not None else None
    driver = get_driver()
    query = """
    MATCH (c:DueDiligenceCase {caseId: $caseId})
    SET c.subject = coalesce($subject, c.subject),
        c.subjectGeorgian = coalesce($subjectGeorgian, c.subjectGeorgian),
        c.subjectEnglish = coalesce($subjectEnglish, c.subjectEnglish),
        c.subjectType = coalesce($subjectType, c.subjectType),
        c.status = coalesce($status, c.status),
        c.owner = coalesce($owner, c.owner),
        c.updatedAt = datetime()
    WITH c
    OPTIONAL MATCH (c)-[:HAS_DD_REPORT]->(r:DueDiligenceReport)
    WITH c, r ORDER BY r.createdAt DESC
    WITH c, collect(r)[0] AS latest
    OPTIONAL MATCH (c)-[:HAS_TASK]->(t:DueDiligenceTask)
    RETURN
      c.caseId AS caseId,
      c.subject AS subject,
      coalesce(c.subjectGeorgian, '') AS subjectGeorgian,
      coalesce(c.subjectEnglish, '') AS subjectEnglish,
      c.subjectType AS subjectType,
      c.status AS status,
      coalesce(c.owner, '') AS owner,
      toString(c.createdAt) AS createdAt,
      toString(c.updatedAt) AS updatedAt,
      latest.reportId AS lastReportId,
      latest.riskLevel AS lastRiskLevel,
      latest.totalHits AS lastTotalHits,
      toString(latest.createdAt) AS lastReportAt,
      count(t) AS taskCount
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "caseId": case_id,
                "subject": subject,
                "subjectGeorgian": subject_georgian,
                "subjectEnglish": subject_english,
                "subjectType": subject_type,
                "status": status,
                "owner": owner,
            },
        )
    if not records:
        raise HTTPException(status_code=404, detail="Case not found")
    return records[0].data()


@router.post("/cases/{case_id}/archive", response_model=DueDiligenceCaseOut)
def archive_due_diligence_case(case_id: str):
    return update_due_diligence_case(
        case_id,
        DueDiligenceCaseUpdate(status="Archived"),
    )


@router.delete("/cases/{case_id}")
def delete_due_diligence_case(case_id: str):
    driver = get_driver()
    query = """
    MATCH (c:DueDiligenceCase {caseId: $caseId})
    DETACH DELETE c
    RETURN count(c) AS deleted
    """
    with _db_session(driver) as session:
        records = _execute_write(session, query, {"caseId": case_id})
    deleted = int(records[0].get("deleted") or 0) if records else 0
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"deleted": True, "caseId": case_id}


@router.get("/cases/{case_id}/tasks", response_model=List[DueDiligenceTaskOut])
def list_due_diligence_case_tasks(case_id: str):
    driver = get_driver()
    query = """
    MATCH (c:DueDiligenceCase {caseId: $caseId})-[:HAS_TASK]->(t:DueDiligenceTask)
    RETURN
      t.taskId AS taskId,
      t.label AS label,
      t.status AS status,
      coalesce(t.assignee, '') AS assignee,
      toString(t.dueDate) AS dueDate,
      toString(t.createdAt) AS createdAt,
      toString(t.updatedAt) AS updatedAt
    ORDER BY t.createdAt DESC
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query, {"caseId": case_id})
        if records:
            return [record.data() for record in records]
        case_check = _execute_read(
            session,
            "MATCH (c:DueDiligenceCase {caseId: $caseId}) RETURN c.caseId AS caseId",
            {"caseId": case_id},
        )
    if not case_check:
        raise HTTPException(status_code=404, detail="Case not found")
    return []


@router.post("/cases/{case_id}/tasks", response_model=DueDiligenceTaskOut)
def create_due_diligence_case_task(case_id: str, payload: DueDiligenceTaskCreate):
    label = payload.label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="Task label is required")
    status = _normalize_task_status(payload.status)
    assignee = str(payload.assignee or "").strip()
    due_date = str(payload.due_date or "").strip() or None
    driver = get_driver()
    query = """
    MATCH (c:DueDiligenceCase {caseId: $caseId})
    CREATE (t:DueDiligenceTask)
    SET t.taskId = randomUUID(),
        t.label = $label,
        t.status = $status,
        t.assignee = $assignee,
        t.dueDate = $dueDate,
        t.createdAt = datetime(),
        t.updatedAt = datetime()
    MERGE (c)-[:HAS_TASK]->(t)
    SET c.updatedAt = datetime()
    RETURN
      t.taskId AS taskId,
      t.label AS label,
      t.status AS status,
      coalesce(t.assignee, '') AS assignee,
      toString(t.dueDate) AS dueDate,
      toString(t.createdAt) AS createdAt,
      toString(t.updatedAt) AS updatedAt
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "caseId": case_id,
                "label": label,
                "status": status,
                "assignee": assignee,
                "dueDate": due_date,
            },
        )
    if not records:
        raise HTTPException(status_code=404, detail="Case not found")
    return records[0].data()


@router.patch("/cases/{case_id}/tasks/{task_id}", response_model=DueDiligenceTaskOut)
def update_due_diligence_case_task(case_id: str, task_id: str, payload: DueDiligenceTaskUpdate):
    fields_set = getattr(payload, "model_fields_set", None) or getattr(
        payload, "__fields_set__", set()
    )
    label_set = "label" in fields_set
    status_set = "status" in fields_set
    assignee_set = "assignee" in fields_set
    due_date_set = "due_date" in fields_set
    label = payload.label.strip() if label_set and payload.label is not None else None
    if label_set and not label:
        raise HTTPException(status_code=400, detail="Task label cannot be empty")
    if status_set and not payload.status:
        raise HTTPException(status_code=400, detail="Task status cannot be empty")
    status = _normalize_task_status(payload.status) if status_set and payload.status else None
    assignee = (
        None
        if not assignee_set
        else (str(payload.assignee).strip() if payload.assignee is not None else None)
    )
    if assignee_set and assignee == "":
        assignee = None
    due_date = (
        None
        if not due_date_set
        else (str(payload.due_date).strip() if payload.due_date is not None else None)
    )
    if due_date_set and due_date == "":
        due_date = None
    driver = get_driver()
    query = """
    MATCH (c:DueDiligenceCase {caseId: $caseId})-[:HAS_TASK]->(t:DueDiligenceTask {taskId: $taskId})
    SET t.label = CASE WHEN $labelSet THEN $label ELSE t.label END,
        t.status = CASE WHEN $statusSet THEN $status ELSE t.status END,
        t.assignee = CASE WHEN $assigneeSet THEN $assignee ELSE t.assignee END,
        t.dueDate = CASE WHEN $dueDateSet THEN $dueDate ELSE t.dueDate END,
        t.updatedAt = datetime(),
        c.updatedAt = datetime()
    RETURN
      t.taskId AS taskId,
      t.label AS label,
      t.status AS status,
      coalesce(t.assignee, '') AS assignee,
      toString(t.dueDate) AS dueDate,
      toString(t.createdAt) AS createdAt,
      toString(t.updatedAt) AS updatedAt
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "caseId": case_id,
                "taskId": task_id,
                "label": label,
                "status": status,
                "assignee": assignee,
                "dueDate": due_date,
                "labelSet": bool(label_set),
                "statusSet": bool(status_set),
                "assigneeSet": bool(assignee_set),
                "dueDateSet": bool(due_date_set),
            },
        )
    if not records:
        raise HTTPException(status_code=404, detail="Task not found")
    return records[0].data()


@router.post("/cases/{case_id}/decision", response_model=DueDiligenceDecisionOut)
def create_due_diligence_decision(case_id: str, payload: DueDiligenceDecisionCreate):
    outcome = payload.outcome.strip()
    if not outcome:
        raise HTTPException(status_code=400, detail="Decision outcome is required")
    rationale = str(payload.rationale or "").strip()
    decided_by = str(payload.decided_by or "").strip()
    driver = get_driver()
    query = """
    MATCH (c:DueDiligenceCase {caseId: $caseId})
    CREATE (d:DueDiligenceDecision)
    SET d.decisionId = randomUUID(),
        d.outcome = $outcome,
        d.rationale = $rationale,
        d.decidedAt = datetime(),
        d.decidedBy = $decidedBy
    MERGE (c)-[:HAS_DECISION]->(d)
    SET c.status = 'Decided',
        c.updatedAt = datetime()
    RETURN
      d.decisionId AS decisionId,
      d.outcome AS outcome,
      d.rationale AS rationale,
      toString(d.decidedAt) AS decidedAt,
      d.decidedBy AS decidedBy
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "caseId": case_id,
                "outcome": outcome,
                "rationale": rationale,
                "decidedBy": decided_by,
            },
        )
    if not records:
        raise HTTPException(status_code=404, detail="Case not found")
    return records[0].data()


@router.get("/reports", response_model=List[DueDiligenceReportListOut])
def list_due_diligence_reports(
    subject: Optional[str] = Query(None),
    case_id: Optional[str] = Query(None, alias="caseId"),
    limit: int = Query(50, ge=1, le=200),
):
    driver = get_driver()
    subject_filter = subject.strip() if subject else None
    if subject_filter == "":
        subject_filter = None
    case_filter = case_id.strip() if case_id else None
    if case_filter == "":
        case_filter = None
    query = """
    MATCH (r:DueDiligenceReport)
    OPTIONAL MATCH (c:DueDiligenceCase)-[:HAS_DD_REPORT]->(r)
    WHERE ($subject IS NULL OR toLower(r.subject) CONTAINS toLower($subject))
      AND ($caseId IS NULL OR c.caseId = $caseId OR r.caseId = $caseId)
    RETURN
      r.reportId AS reportId,
      coalesce(c.caseId, r.caseId) AS caseId,
      r.subject AS subject,
      r.subjectType AS subjectType,
      r.riskLevel AS riskLevel,
      r.totalHits AS totalHits,
      toString(r.createdAt) AS createdAt,
      coalesce(r.sources, []) AS sources
    ORDER BY r.createdAt DESC
    LIMIT $limit
    """
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            query,
            {
                "subject": subject_filter,
                "caseId": case_filter,
                "limit": int(limit),
            },
        )
    return [record.data() for record in records]


def _load_dd_report(report_id: str) -> Dict[str, object]:
    driver = get_driver()
    query = """
    MATCH (r:DueDiligenceReport {reportId: $rid})
    OPTIONAL MATCH (c:DueDiligenceCase)-[:HAS_DD_REPORT]->(r)
    RETURN
      r.reportId AS reportId,
      coalesce(c.caseId, r.caseId) AS caseId,
      r.subject AS subject,
      r.subjectType AS subjectType,
      toString(r.createdAt) AS createdAt,
      coalesce(r.payloadJson, '{}') AS payloadJson,
      coalesce(r.sources, []) AS sources
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query, {"rid": report_id})
    row = records[0] if records else None
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    payload_raw = row.get("payloadJson") or "{}"
    try:
        payload = json.loads(payload_raw)
    except (TypeError, ValueError):
        payload = {}
    payload["subject"] = row.get("subject")
    payload["subjectType"] = row.get("subjectType")
    payload["createdAt"] = row.get("createdAt")
    payload["sources"] = row.get("sources") or []
    payload["caseId"] = row.get("caseId")
    return {
        "reportId": row.get("reportId"),
        "caseId": row.get("caseId"),
        "subject": row.get("subject"),
        "subjectType": row.get("subjectType"),
        "createdAt": row.get("createdAt"),
        "payload": payload,
    }


@router.get("/reports/{report_id}", response_model=DueDiligenceReportOut)
def get_due_diligence_report(report_id: str):
    return _load_dd_report(report_id)


@router.get("/reports/{report_id}/pdf")
def download_due_diligence_report_pdf(report_id: str):
    report = _load_dd_report(report_id)
    payload = report.get("payload") or {}
    payload["subject"] = report.get("subject")
    payload["subjectType"] = report.get("subjectType")
    payload["createdAt"] = report.get("createdAt")
    pdf_bytes = _build_report_pdf(payload)
    filename = f"due-diligence-{report_id}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )







