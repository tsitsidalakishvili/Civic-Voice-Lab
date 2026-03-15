import html as html_lib
import io
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
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


class DueDiligenceAnalysisRequest(BaseModel):
    subject: str = Field(min_length=1)
    subject_type: str = Field(default="Person", alias="subjectType")
    use_wikidata: bool = Field(default=True, alias="useWikidata")
    use_opensanctions: bool = Field(default=True, alias="useOpenSanctions")
    use_news: bool = Field(default=True, alias="useNews")
    max_news: int = Field(default=8, alias="maxNews", ge=1, le=20)
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
    wikidata: List[WikidataResult]
    opensanctions: List[OpenSanctionsResult]
    news: List[NewsResult]
    summary: Dict[str, object]
    warnings: List[str]
    report_id: Optional[str] = Field(default=None, alias="reportId")
    stored_at: Optional[str] = Field(default=None, alias="storedAt")


class DueDiligenceReportListOut(BaseModel):
    report_id: str = Field(alias="reportId")
    subject: str
    subject_type: str = Field(alias="subjectType")
    risk_level: Optional[str] = Field(default=None, alias="riskLevel")
    total_hits: Optional[int] = Field(default=None, alias="totalHits")
    created_at: Optional[str] = Field(default=None, alias="createdAt")
    sources: List[str] = []


class DueDiligenceReportOut(BaseModel):
    report_id: str = Field(alias="reportId")
    subject: str
    subject_type: str = Field(alias="subjectType")
    created_at: Optional[str] = Field(default=None, alias="createdAt")
    payload: Dict[str, object]


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


def _default_local_media_feeds() -> List[str]:
    env = str(os.getenv("LOCAL_MEDIA_RSS") or "").strip()
    if env:
        return [item.strip() for item in env.split(",") if item.strip()]
    return [
        "https://publika.ge/feed/",
        "https://netgazeti.ge/feed/",
    ]


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
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": limit,
        "format": "json",
    }
    headers = {"User-Agent": "FS-DueDiligence/1.0"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        return [], f"Wikipedia request failed: {exc}"
    results: List[WikipediaResult] = []
    for item in data.get("query", {}).get("search", []) or []:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        snippet = _strip_html(item.get("snippet") or "")
        results.append(
            WikipediaResult(
                title=title,
                summary=snippet,
                url=f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}",
            )
        )
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
    opensanctions: List[OpenSanctionsResult],
    news: List[NewsResult],
    warnings: List[str],
) -> Dict[str, object]:
    wikidata_hits = len(wikidata)
    opensanctions_hits = len(opensanctions)
    news_hits = len(news)
    total_hits = wikidata_hits + opensanctions_hits + news_hits
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
    if wikidata_hits:
        risk_score += 10
        rationale.append("Found Wikidata entity matches.")
    if news_hits:
        news_boost = min(35, 20 + news_hits * 2)
        risk_score += news_boost
        rationale.append("Recent news mentions detected.")
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

    if opensanctions_hits and news_hits:
        risk_score += 5
        rationale.append("Cross-source signal overlap (news + sanctions).")

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
        "opensanctions_hits": opensanctions_hits,
        "news_hits": news_hits,
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
        r.opensanctionsHits = $opensanctionsHits,
        r.newsHits = $newsHits,
        r.sources = $sources,
        r.summaryJson = $summaryJson,
        r.payloadJson = $payloadJson
    WITH r
    OPTIONAL MATCH (c:Competitor {nameKey: toLower($subject), competitorType: $subjectType})
    FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END | MERGE (c)-[:HAS_DD_REPORT]->(r))
    RETURN r.reportId AS reportId, toString(r.createdAt) AS createdAt
    """
    params = {
        "subject": subject,
        "subjectType": subject_type,
        "riskLevel": summary.get("risk_level"),
        "totalHits": summary.get("total_hits"),
        "wikidataHits": summary.get("wikidata_hits"),
        "opensanctionsHits": summary.get("opensanctions_hits"),
        "newsHits": summary.get("news_hits"),
        "sources": sources,
        "summaryJson": json.dumps(summary),
        "payloadJson": json.dumps(payload),
    }
    with _db_session(driver) as session:
        records = _execute_write(session, query, params)
    row = records[0] if records else None
    if not row:
        return None, None
    return row.get("reportId"), row.get("createdAt")


def _build_report_pdf(report: Dict[str, object]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER, title="Due Diligence Report")
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    header_style = ParagraphStyle("Header", parent=styles["Heading2"], spaceAfter=6)
    body_style = styles["BodyText"]
    mono_style = ParagraphStyle(
        "Mono", parent=styles["BodyText"], fontName="Courier", fontSize=9, leading=11
    )

    summary = report.get("summary") or {}
    rationale = summary.get("risk_rationale") or []
    warnings = report.get("warnings") or []
    wikidata = report.get("wikidata") or []
    opensanctions = report.get("opensanctions") or []
    news = report.get("news") or []
    sources = ", ".join(report.get("sources") or [])

    story = [
        Paragraph("Due Diligence Report", title_style),
        Paragraph(f"Subject: <b>{report.get('subject')}</b>", body_style),
        Paragraph(f"Type: {report.get('subjectType')}", body_style),
        Paragraph(f"Generated: {report.get('createdAt')}", body_style),
        Spacer(1, 10),
    ]

    summary_table = Table(
        [
            ["Risk level", summary.get("risk_level", "Unknown")],
            ["Total hits", summary.get("total_hits", 0)],
            ["Wikidata hits", summary.get("wikidata_hits", 0)],
            ["OpenSanctions hits", summary.get("opensanctions_hits", 0)],
            ["News hits", summary.get("news_hits", 0)],
            ["Sources", sources or "—"],
        ],
        colWidths=[140, 360],
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.extend([Paragraph("Summary", header_style), summary_table, Spacer(1, 12)])

    if rationale:
        story.append(Paragraph("Risk rationale", header_style))
        rationale_text = "<br/>".join([str(item) for item in rationale])
        story.append(Paragraph(rationale_text, body_style))
        story.append(Spacer(1, 12))

    if warnings:
        story.append(Paragraph("Warnings", header_style))
        warning_text = "<br/>".join([str(w) for w in warnings])
        story.append(Paragraph(warning_text, body_style))
        story.append(Spacer(1, 12))

    story.append(Paragraph("Wikidata Findings", header_style))
    if wikidata:
        rows = [["Label", "Description", "URL"]]
        for row in wikidata:
            rows.append(
                [row.get("label") or "", row.get("description") or "", row.get("url") or ""]
            )
        table = Table(rows, colWidths=[140, 250, 110])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(table)
    else:
        story.append(Paragraph("No Wikidata matches.", body_style))
    story.append(Spacer(1, 12))

    story.append(Paragraph("OpenSanctions Findings", header_style))
    if opensanctions:
        rows = [["Name", "Schema", "Datasets", "Topics", "Score"]]
        for row in opensanctions:
            rows.append(
                [
                    row.get("name") or "",
                    row.get("schema") or "",
                    ", ".join(row.get("datasets") or []),
                    ", ".join(row.get("topics") or []),
                    f"{row.get('score'):.2f}"
                    if isinstance(row.get("score"), (int, float))
                    else "",
                ]
            )
        table = Table(rows, colWidths=[140, 70, 120, 120, 50])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(table)
    else:
        story.append(Paragraph("No OpenSanctions matches.", body_style))
    story.append(Spacer(1, 12))

    story.append(Paragraph("News & Web Mentions (GDELT)", header_style))
    if news:
        rows = [["Headline", "Source", "Published", "Tone"]]
        for row in news:
            rows.append(
                [
                    row.get("title") or "",
                    row.get("source") or "",
                    row.get("publishedAt") or "",
                    f"{row.get('tone'):.2f}" if isinstance(row.get("tone"), (int, float)) else "",
                ]
            )
        table = Table(rows, colWidths=[260, 120, 80, 50])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(table)
    else:
        story.append(Paragraph("No recent news found.", body_style))

    story.append(Spacer(1, 12))
    story.append(Paragraph("Raw Sources", header_style))
    story.append(
        Paragraph(
            "This report summarizes public sources (Wikidata, OpenSanctions, GDELT). "
            "Always validate matches with human review before decisions.",
            body_style,
        )
    )
    story.append(Spacer(1, 10))
    story.append(Paragraph(json.dumps(report, indent=2), mono_style))

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


@router.post("/analyze", response_model=DueDiligenceAnalysisOut)
def analyze_due_diligence(payload: DueDiligenceAnalysisRequest):
    subject = payload.subject.strip()
    if not subject:
        raise HTTPException(status_code=400, detail="Subject is required")
    warnings: List[str] = []
    wikidata_results: List[WikidataResult] = []
    opensanctions_results: List[OpenSanctionsResult] = []
    news_results: List[NewsResult] = []

    if payload.use_wikidata:
        wikidata_results, error = _wikidata_search(subject)
        if error:
            warnings.append(error)

    if payload.use_opensanctions:
        opensanctions_results, error = _opensanctions_search(subject, payload.subject_type)
        if error:
            warnings.append(error)

    if payload.use_news:
        news_results, error = _gdelt_news_search(subject, payload.max_news)
        if error:
            warnings.append(error)

    if payload.demo and not (wikidata_results or opensanctions_results or news_results):
        demo = _demo_results(subject)
        wikidata_results = [WikidataResult(**row) for row in demo["wikidata"]]
        opensanctions_results = [OpenSanctionsResult(**row) for row in demo["opensanctions"]]
        news_results = [NewsResult(**row) for row in demo["news"]]
        warnings.append("Demo data used for external sources.")

    summary = _build_summary(wikidata_results, opensanctions_results, news_results, warnings)
    sources = []
    if payload.use_wikidata:
        sources.append("Wikidata")
    if payload.use_opensanctions:
        sources.append("OpenSanctions")
    if payload.use_news:
        sources.append("GDELT")

    payload_blob = {
        "subject": subject,
        "subjectType": payload.subject_type,
        "wikidata": [row.dict(by_alias=True) for row in wikidata_results],
        "opensanctions": [row.dict(by_alias=True) for row in opensanctions_results],
        "news": [row.dict(by_alias=True) for row in news_results],
        "summary": summary,
        "warnings": warnings,
        "sources": sources,
    }
    report_id, stored_at = _store_dd_report(
        subject=subject,
        subject_type=payload.subject_type,
        summary=summary,
        payload=payload_blob,
        sources=sources,
    )

    return {
        "subject": subject,
        "subjectType": payload.subject_type,
        "wikidata": wikidata_results,
        "opensanctions": opensanctions_results,
        "news": news_results,
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


@router.get("/reports", response_model=List[DueDiligenceReportListOut])
def list_due_diligence_reports(
    subject: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    driver = get_driver()
    query = """
    MATCH (r:DueDiligenceReport)
    WHERE $subject IS NULL OR toLower(r.subject) CONTAINS toLower($subject)
    RETURN
      r.reportId AS reportId,
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
            {"subject": subject.strip() if subject else None, "limit": int(limit)},
        )
    return [record.data() for record in records]


def _load_dd_report(report_id: str) -> Dict[str, object]:
    driver = get_driver()
    query = """
    MATCH (r:DueDiligenceReport {reportId: $rid})
    RETURN
      r.reportId AS reportId,
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
    return {
        "reportId": row.get("reportId"),
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
