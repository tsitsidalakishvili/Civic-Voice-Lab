import html as html_lib
import hashlib
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

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .db import get_active_database, get_driver
from .investigation_ftm import _relationship_schema, persist_investigation_projection
from .investigation_reuse import ftm_schema_metadata, infer_ftm_property_type, validate_ftm_entity
from .dd_workflow_v2 import (
    get_case_v2_for_legacy_route,
    legacy_mutation_disabled_response,
    list_cases_v2_for_legacy_route,
    workflow_v2_enabled,
)

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


class InvestigationGraphEnrichRequest(BaseModel):
    report_id: Optional[str] = Field(default=None, alias="reportId")


class InvestigationRelationshipCreate(BaseModel):
    from_entity_id: Optional[str] = Field(default=None, alias="fromEntityId")
    target_name: str = Field(min_length=1, alias="targetName")
    target_type: str = Field(default="Person", alias="targetType")
    relationship_type: str = Field(min_length=1, alias="relationshipType")
    source_name: str = Field(min_length=1, alias="sourceName")
    source_url: Optional[str] = Field(default="", alias="sourceUrl")
    evidence_note: str = Field(min_length=1, alias="evidenceNote")
    confidence: float = Field(default=0.8, ge=0, le=1)
    verification_status: str = Field(default="analyst-added", alias="verificationStatus")


class InvestigationImportSource(BaseModel):
    name: str = Field(min_length=1)
    url: Optional[str] = ""
    source_type: str = Field(default="Imported dataset", alias="sourceType")
    publisher: Optional[str] = ""
    license: Optional[str] = ""
    jurisdiction: Optional[str] = ""
    description: Optional[str] = ""
    ingestion_mode: str = Field(default="bulk-api", alias="ingestionMode")


class InvestigationImportEntity(BaseModel):
    external_id: str = Field(min_length=1, alias="externalId")
    name: str = Field(min_length=1)
    entity_type: str = Field(min_length=1, alias="entityType")
    entity_role: Optional[str] = Field(default="", alias="entityRole")
    description: Optional[str] = ""
    existing_entity_id: Optional[str] = Field(default=None, alias="existingEntityId")
    properties: Dict[str, Any] = Field(default_factory=dict)


class InvestigationImportEvidence(BaseModel):
    title: str = Field(min_length=1)
    source_url: Optional[str] = Field(default="", alias="sourceUrl")
    published_at: Optional[str] = Field(default="", alias="publishedAt")
    note: str = Field(min_length=1)


class InvestigationImportRelationship(BaseModel):
    from_external_id: str = Field(min_length=1, alias="fromExternalId")
    to_external_id: str = Field(min_length=1, alias="toExternalId")
    relationship_type: str = Field(min_length=1, alias="relationshipType")
    confidence: float = Field(default=0.8, ge=0, le=1)
    verification_status: str = Field(default="source-stated", alias="verificationStatus")
    details: Optional[str] = ""
    properties: Dict[str, Any] = Field(default_factory=dict)
    evidence: InvestigationImportEvidence


class InvestigationGraphImportRequest(BaseModel):
    source: InvestigationImportSource
    entities: List[InvestigationImportEntity] = Field(min_length=1, max_length=500)
    relationships: List[InvestigationImportRelationship] = Field(default_factory=list, max_length=1000)


class FollowTheMoneyImportDataset(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    url: Optional[str] = ""
    publisher: Optional[str] = ""
    license: Optional[str] = ""
    jurisdiction: Optional[str] = ""
    description: Optional[str] = ""


class FollowTheMoneyImportEntity(BaseModel):
    id: str = Field(min_length=1)
    schema_name: str = Field(min_length=1, alias="schema")
    properties: Dict[str, Any] = Field(default_factory=dict)
    datasets: List[str] = Field(default_factory=list)
    referents: List[str] = Field(default_factory=list)
    existing_entity_id: Optional[str] = Field(default=None, alias="existingEntityId")
    first_seen: Optional[str] = Field(default="", alias="firstSeen")
    last_seen: Optional[str] = Field(default="", alias="lastSeen")
    last_change: Optional[str] = Field(default="", alias="lastChange")


class FollowTheMoneyGraphImportRequest(BaseModel):
    dataset: FollowTheMoneyImportDataset
    entities: List[FollowTheMoneyImportEntity] = Field(min_length=1, max_length=2500)


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
    # Demo data fabricates sanctions/PEP hits carrying the real subject's name, so
    # it must never be the default for a screening request. Opt in explicitly.
    demo: bool = Field(default=False)


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
    demo: bool = Field(default=False)


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


class DueDiligenceFullCheckRequest(BaseModel):
    """Input for the one-click full check.

    There is deliberately no ``demo`` field: the full check must never fabricate
    entities carrying a real subject's name, so it always runs the underlying
    analysis with ``demo=False``.
    """

    subject: Optional[str] = None
    subject_type: Optional[str] = Field(default=None, alias="subjectType")
    max_news: int = Field(default=8, alias="maxNews", ge=1, le=20)
    use_local_media: bool = Field(default=True, alias="useLocalMedia")
    media_source_ids: List[str] = Field(
        default_factory=lambda: ["netgazeti", "publika", "interpressnews"],
        alias="mediaSourceIds",
    )
    media_topics: List[str] = Field(default_factory=list, alias="mediaTopics")
    media_max_results: int = Field(default=12, alias="mediaMaxResults", ge=1, le=50)
    identification_code: Optional[str] = Field(
        default=None, alias="identificationCode"
    )


class DueDiligenceSourceStatusOut(BaseModel):
    id: str
    label: str
    status: str
    hit_count: int = Field(default=0, alias="hitCount")
    detail: str = ""
    requires_configuration: bool = Field(
        default=False, alias="requiresConfiguration"
    )


class DueDiligenceFullCheckResultsOut(BaseModel):
    wikidata: List[WikidataResult] = []
    wikipedia: List[WikipediaResult] = []
    opensanctions: List[OpenSanctionsResult] = []
    news: List[NewsResult] = []
    declarations: List[AssetDeclarationResult] = []
    media: Optional[Dict[str, object]] = None
    company_registry: Optional[Dict[str, object]] = Field(
        default=None, alias="companyRegistry"
    )
    facebook: Optional[Dict[str, object]] = None


class DueDiligenceFullCheckOut(BaseModel):
    case_id: str = Field(alias="caseId")
    subject: str
    subject_type: str = Field(alias="subjectType")
    generated_at: str = Field(alias="generatedAt")
    demo: bool = False
    sources: List[DueDiligenceSourceStatusOut] = []
    summary: Dict[str, object]
    results: DueDiligenceFullCheckResultsOut
    ai_report: Optional[Dict[str, object]] = Field(default=None, alias="aiReport")
    warnings: List[str] = []
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
    is_demo: bool = False,
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
        r.payloadJson = $payloadJson,
        r.isDemo = $isDemo
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
        "isDemo": bool(is_demo),
    }
    with _db_session(driver) as session:
        records = _execute_write(session, query, params)
    row = records[0] if records else None
    if not row:
        return None, None
    return row.get("reportId"), row.get("createdAt")


def _investigation_id(prefix: str, *parts: object) -> str:
    material = "|".join(_clean_decl_text(part).casefold() for part in parts if part is not None)
    return f"{prefix}-{hashlib.sha256(material.encode('utf-8')).hexdigest()[:24]}"


def _birth_year(value: object) -> str:
    matches = re.findall(r"(?:19|20)\d{2}", str(value or ""))
    return matches[-1] if matches else ""


def _safe_investigation_properties(values: Dict[str, Any]) -> Dict[str, object]:
    reserved = {
        "entityId",
        "name",
        "entityType",
        "entityRole",
        "isRoot",
        "createdAt",
        "updatedAt",
    }
    output: Dict[str, object] = {}
    for raw_key, raw_value in (values or {}).items():
        key = str(raw_key or "").strip()
        if not key or key in reserved or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", key):
            continue
        if isinstance(raw_value, (str, int, float, bool)):
            output[key] = raw_value[:4000] if isinstance(raw_value, str) else raw_value
            continue
        if isinstance(raw_value, list):
            clean_list = [
                item[:1000] if isinstance(item, str) else item
                for item in raw_value[:100]
                if isinstance(item, (str, int, float, bool))
            ]
            if clean_list:
                output[key] = clean_list
    return output


def _graph_entity(
    entities: Dict[str, Dict[str, object]],
    *,
    name: object,
    entity_type: str,
    identity: Optional[object] = None,
    entity_id: Optional[str] = None,
    **properties: object,
) -> Optional[str]:
    clean_name = _clean_decl_text(name)
    if not clean_name:
        return None
    resolved_id = entity_id or _investigation_id(
        "entity", entity_type, identity if identity is not None else clean_name
    )
    row = entities.setdefault(
        resolved_id,
        {
            "entityId": resolved_id,
            "name": clean_name,
            "entityType": entity_type,
        },
    )
    row["name"] = clean_name
    row["entityType"] = entity_type
    for key, value in properties.items():
        if value is None or value == "":
            continue
        row[key] = value
    return resolved_id


def _graph_source(
    sources: Dict[str, Dict[str, object]],
    *,
    name: object,
    url: object = "",
    source_type: str = "Public source",
    **properties: object,
) -> str:
    clean_name = _clean_decl_text(name) or "Unspecified source"
    source_id = _investigation_id("source", clean_name)
    row = sources.setdefault(
        source_id,
        {
            "sourceId": source_id,
            "name": clean_name,
            "sourceType": source_type,
        },
    )
    clean_url = _clean_decl_text(url)
    if clean_url and not row.get("url"):
        row["url"] = clean_url
    for key, value in properties.items():
        if value not in (None, ""):
            row[key] = value
    return source_id


def _graph_evidence(
    evidence: Dict[str, Dict[str, object]],
    *,
    source_id: str,
    source_name: object,
    title: object,
    source_url: object = "",
    evidence_type: str = "Source record",
    published_at: object = "",
    note: object = "",
    identity: Optional[object] = None,
    report_id: Optional[str] = None,
) -> str:
    clean_title = _clean_decl_text(title) or "Evidence record"
    clean_url = _clean_decl_text(source_url)
    evidence_id = _investigation_id(
        "evidence", source_id, identity if identity is not None else clean_url or clean_title
    )
    row = evidence.setdefault(
        evidence_id,
        {
            "evidenceId": evidence_id,
            "sourceId": source_id,
            "sourceName": _clean_decl_text(source_name),
            "title": clean_title,
            "evidenceType": evidence_type,
        },
    )
    for key, value in {
        "sourceUrl": clean_url,
        "publishedAt": _clean_decl_text(published_at),
        "note": _clean_decl_text(note),
        "reportId": report_id,
    }.items():
        if value:
            row[key] = value
    return evidence_id


def _graph_link(
    links: Dict[str, Dict[str, object]],
    *,
    case_id: str,
    from_id: Optional[str],
    to_id: Optional[str],
    relationship_type: object,
    evidence_ids: Optional[List[str]] = None,
    confidence: float = 0.8,
    verification_status: str = "source-stated",
    details: object = "",
    relationship_id: Optional[str] = None,
    properties: Optional[Dict[str, Any]] = None,
    ftm_schema: Optional[str] = None,
) -> Optional[str]:
    if not from_id or not to_id or from_id == to_id:
        return None
    clean_type = _clean_decl_text(relationship_type) or "Connected to"
    resolved_relationship_id = relationship_id or _investigation_id(
        "link", case_id, from_id, to_id, clean_type
    )
    row = links.setdefault(
        resolved_relationship_id,
        {
            "relationshipId": resolved_relationship_id,
            "fromEntityId": from_id,
            "toEntityId": to_id,
            "relationshipType": clean_type,
            "schema": ftm_schema or _relationship_schema(clean_type),
            "confidence": max(0.0, min(float(confidence), 1.0)),
            "verificationStatus": verification_status,
            "details": _clean_decl_text(details),
            "evidenceIds": [],
            "properties": {},
        },
    )
    if ftm_schema:
        row["ftmSchema"] = ftm_schema
    if properties:
        row["properties"].update(_safe_investigation_properties(properties))
    for evidence_id in evidence_ids or []:
        if evidence_id and evidence_id not in row["evidenceIds"]:
            row["evidenceIds"].append(evidence_id)
    return resolved_relationship_id


def _case_and_report_for_graph(
    case_id: str, report_id: Optional[str] = None
) -> Tuple[Dict[str, object], Dict[str, object]]:
    driver = get_driver()
    query = """
    MATCH (c:DueDiligenceCase {caseId: $caseId})
    OPTIONAL MATCH (c)-[:HAS_DD_REPORT]->(candidate:DueDiligenceReport)
    WHERE $reportId IS NULL OR candidate.reportId = $reportId
    WITH c, candidate ORDER BY candidate.createdAt DESC
    WITH c, collect(candidate)[0] AS report
    RETURN
      c.caseId AS caseId,
      c.subject AS subject,
      c.subjectGeorgian AS subjectGeorgian,
      c.subjectEnglish AS subjectEnglish,
      c.subjectType AS subjectType,
      report.reportId AS reportId,
      coalesce(report.payloadJson, '{}') AS payloadJson
    """
    with _db_session(driver) as session:
        records = _execute_read(
            session, query, {"caseId": case_id, "reportId": report_id}
        )
    row = records[0].data() if records else None
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    if report_id and not row.get("reportId"):
        raise HTTPException(status_code=404, detail="Report not found for this case")
    try:
        payload = json.loads(row.get("payloadJson") or "{}")
    except (TypeError, ValueError):
        payload = {}
    case_row = {
        "caseId": row.get("caseId"),
        "subject": row.get("subject"),
        "subjectGeorgian": row.get("subjectGeorgian"),
        "subjectEnglish": row.get("subjectEnglish"),
        "subjectType": row.get("subjectType"),
    }
    return case_row, {"reportId": row.get("reportId"), "payload": payload}


def _build_investigation_graph_bundle(
    case_row: Dict[str, object], report: Dict[str, object]
) -> Dict[str, object]:
    case_id = str(case_row.get("caseId") or "")
    report_id = str(report.get("reportId") or "") or None
    payload = report.get("payload") if isinstance(report.get("payload"), dict) else {}
    entities: Dict[str, Dict[str, object]] = {}
    links: Dict[str, Dict[str, object]] = {}
    sources: Dict[str, Dict[str, object]] = {}
    evidence: Dict[str, Dict[str, object]] = {}

    subject_name = (
        case_row.get("subjectGeorgian")
        or case_row.get("subjectEnglish")
        or case_row.get("subject")
        or payload.get("subject")
        or "Case subject"
    )
    aliases = []
    for alias in [
        case_row.get("subject"),
        case_row.get("subjectGeorgian"),
        case_row.get("subjectEnglish"),
        payload.get("subject"),
    ]:
        clean_alias = _clean_decl_text(alias)
        if clean_alias and clean_alias not in aliases:
            aliases.append(clean_alias)
    root_id = _graph_entity(
        entities,
        name=subject_name,
        entity_type=str(case_row.get("subjectType") or "Person"),
        entity_id=_investigation_id("case-subject", case_id),
        isRoot=True,
        aliases=aliases,
        entityRole="Public official" if str(case_row.get("subjectType") or "Person") == "Person" else "Case subject",
        description="Primary subject of the due-diligence case",
    )

    person_ids: Dict[str, str] = {}
    if root_id:
        for alias in aliases:
            person_ids[alias.casefold()] = root_id

    def resolve_person(row: Dict[str, Any], fallback_to_root: bool = True) -> Optional[str]:
        name = _decl_person_name(row)
        if not name:
            return root_id if fallback_to_root else None
        known = person_ids.get(name.casefold())
        if known:
            return known
        person_id = _graph_entity(
            entities,
            name=name,
            entity_type="Person",
            identity=f"{name}|{_birth_year(row.get('BirthDate'))}",
            birthYear=_birth_year(row.get("BirthDate")),
            description="Person named in a public asset declaration",
            entityRole="Associated person",
        )
        if person_id:
            person_ids[name.casefold()] = person_id
        return person_id

    declaration_source_id = _graph_source(
        sources,
        name="Georgian Asset Declarations",
        url="https://declaration.acb.gov.ge/",
        source_type="Official registry",
    )
    declarations = payload.get("declarations") if isinstance(payload, dict) else []
    for declaration in declarations or []:
        if not isinstance(declaration, dict):
            continue
        raw = declaration.get("raw") if isinstance(declaration.get("raw"), dict) else {}
        declaration_id = str(declaration.get("id") or raw.get("Id") or "declaration")
        source_url = declaration.get("sourceUrl") or _declaration_source_url(raw)
        submitted = declaration.get("declarationSubmitDate") or raw.get("DeclarationSubmitDate")
        evidence_id = _graph_evidence(
            evidence,
            source_id=declaration_source_id,
            source_name="Georgian Asset Declarations",
            title=f"Asset declaration: {declaration.get('name') or subject_name}",
            source_url=source_url,
            evidence_type="Official declaration",
            published_at=submitted,
            note="Public declaration record; each relationship remains traceable to this filing.",
            identity=declaration_id,
            report_id=report_id,
        )

        for family_row in _as_list(raw.get("FamilyMembers")):
            if not isinstance(family_row, dict):
                continue
            family_name = _decl_person_name(family_row, "FirstName", "LastName")
            family_id = _graph_entity(
                entities,
                name=family_name,
                entity_type="Person",
                identity=f"{family_name}|{_birth_year(family_row.get('BirthDate'))}",
                birthYear=_birth_year(family_row.get("BirthDate")),
                entityRole="Relative",
                description="Relative named in a public asset declaration",
            )
            if family_id and family_name:
                person_ids[family_name.casefold()] = family_id
            relation = _decl_pick(
                family_row, "Relationship", "RelationName", "Relation"
            ) or "Relative"
            _graph_link(
                links,
                case_id=case_id,
                from_id=root_id,
                to_id=family_id,
                relationship_type=f"Family: {relation}",
                evidence_ids=[evidence_id],
                confidence=0.98,
                verification_status="source-stated",
                details="Relationship stated in an official asset declaration.",
            )

        for property_row in _as_list(raw.get("Properties")) + _as_list(raw.get("MovableProperties")):
            if not isinstance(property_row, dict):
                continue
            owner_id = resolve_person(property_row)
            asset_type = _decl_pick(property_row, "PropertyType", "Type", "Kind") or "Declared asset"
            address = _decl_pick(property_row, "Address", "Location", "Details", "Description")
            acquired = _decl_pick(property_row, "PurchaseDate", "RegisterDate", "PurchaseYear")
            asset_name = " · ".join(value for value in [asset_type, address] if value)[:180]
            asset_id = _graph_entity(
                entities,
                name=asset_name,
                entity_type="Asset",
                identity=f"{owner_id}|{asset_type}|{address}|{acquired}",
                description="Asset disclosed in an official declaration",
                entityRole="Declared asset",
                address=address,
                acquiredAt=acquired,
            )
            details = "; ".join(
                value
                for value in [
                    f"share {_decl_pick(property_row, 'Share', 'Part')}" if _decl_pick(property_row, "Share", "Part") else "",
                    f"area {_decl_pick(property_row, 'Area', 'Square', 'LandArea')}" if _decl_pick(property_row, "Area", "Square", "LandArea") else "",
                    _decl_money(property_row, "Price", "Amount"),
                ]
                if value
            )
            _graph_link(
                links,
                case_id=case_id,
                from_id=owner_id,
                to_id=asset_id,
                relationship_type="Declared ownership",
                evidence_ids=[evidence_id],
                confidence=0.98,
                verification_status="source-stated",
                details=details,
            )
            address_id = _graph_entity(
                entities,
                name=address,
                entity_type="Address",
                identity=address,
                entityRole="Declared address",
                description="Address stated in an official asset declaration",
            )
            _graph_link(
                links,
                case_id=case_id,
                from_id=asset_id,
                to_id=address_id,
                relationship_type="Located at",
                evidence_ids=[evidence_id],
                confidence=0.96,
                verification_status="source-stated",
            )

        for job_row in _as_list(raw.get("Jobs")):
            if not isinstance(job_row, dict):
                continue
            owner_id = resolve_person(job_row)
            organization = _decl_pick(job_row, "Organisation", "Organization")
            organization_id = _graph_entity(
                entities,
                name=organization,
                entity_type="Organization",
                identity=organization,
                entityRole="Institution or employer",
                description="Organization named in a declared employment record",
            )
            role = _decl_pick(job_row, "Position") or "Position"
            period = " – ".join(
                value for value in [_decl_pick(job_row, "StartDate"), _decl_pick(job_row, "EndDate")] if value
            )
            _graph_link(
                links,
                case_id=case_id,
                from_id=owner_id,
                to_id=organization_id,
                relationship_type=f"Held position: {role}",
                evidence_ids=[evidence_id],
                confidence=0.98,
                verification_status="source-stated",
                details="; ".join(value for value in [period, _decl_money(job_row, "Amount")] if value),
            )

        enterprise_rows = (
            _as_list(raw.get("Enterprice"))
            + _as_list(raw.get("Enterprise"))
            + _as_list(raw.get("LinkedEnterprice"))
            + _as_list(raw.get("LinkedEnterprise"))
        )
        for enterprise_row in enterprise_rows:
            if not isinstance(enterprise_row, dict):
                continue
            owner_id = resolve_person(enterprise_row)
            company_name = _decl_pick(enterprise_row, "Name", "EnterpriseName", "Organisation", "Organization")
            company_id = _graph_entity(
                entities,
                name=company_name,
                entity_type="Organization",
                identity=company_name,
                entityRole="Legal entity",
                description="Business interest named in an official declaration",
            )
            role = _decl_pick(enterprise_row, "PartnershipFormName", "Role", "Position")
            share = _decl_pick(enterprise_row, "Share", "SharePct")
            _graph_link(
                links,
                case_id=case_id,
                from_id=owner_id,
                to_id=company_id,
                relationship_type="Declared business interest",
                evidence_ids=[evidence_id],
                confidence=0.96,
                verification_status="source-stated",
                details="; ".join(value for value in [role, f"share {share}" if share else ""] if value),
            )

        for contract_row in _as_list(raw.get("Contracts")):
            if not isinstance(contract_row, dict):
                continue
            owner_id = resolve_person(contract_row)
            subject = _decl_pick(contract_row, "Subject", "ContractType") or "Declared contract"
            agency = _decl_pick(contract_row, "Agency", "Organisation", "Organization")
            start_date = _decl_pick(contract_row, "StartDate")
            contract_id = _graph_entity(
                entities,
                name=subject[:180],
                entity_type="Contract",
                identity=f"{owner_id}|{subject}|{agency}|{start_date}",
                entityRole="Declared agreement",
                description="Contract disclosed in an official declaration",
            )
            _graph_link(
                links,
                case_id=case_id,
                from_id=owner_id,
                to_id=contract_id,
                relationship_type="Party to declared contract",
                evidence_ids=[evidence_id],
                confidence=0.96,
                verification_status="source-stated",
                details=_decl_money(contract_row, "Amount", "Income"),
            )
            agency_id = _graph_entity(
                entities,
                name=agency,
                entity_type="Organization",
                identity=agency,
                entityRole="Contracting agency",
                description="Agency named in a declared contract",
            )
            _graph_link(
                links,
                case_id=case_id,
                from_id=contract_id,
                to_id=agency_id,
                relationship_type="Contract counterparty",
                evidence_ids=[evidence_id],
                confidence=0.9,
                verification_status="source-stated",
            )

    def add_article(item: Dict[str, Any], fallback_source: str) -> None:
        title = _clean_decl_text(item.get("title"))
        url = _clean_decl_text(item.get("url"))
        if not title and not url:
            return
        source_name = _clean_decl_text(item.get("source")) or fallback_source
        source_id = _graph_source(sources, name=source_name, url=url, source_type="Media")
        evidence_id = _graph_evidence(
            evidence,
            source_id=source_id,
            source_name=source_name,
            title=title or url,
            source_url=url,
            evidence_type="Media article",
            published_at=item.get("publishedAt") or item.get("published_at"),
            note=item.get("snippet") or "Article captured during subject monitoring.",
            identity=url or title,
            report_id=report_id,
        )
        article_id = _graph_entity(
            entities,
            name=title or url,
            entity_type="Article",
            identity=url or title,
            entityRole="Source document",
            description=source_name,
            sourceUrl=url,
        )
        _graph_link(
            links,
            case_id=case_id,
            from_id=root_id,
            to_id=article_id,
            relationship_type="Mentioned in article",
            evidence_ids=[evidence_id],
            confidence=0.72,
            verification_status="candidate-match",
            details="Open the source and verify that the mention refers to the case subject.",
        )

    for article in (payload.get("news") or []):
        if isinstance(article, dict):
            add_article(article, "News source")
    media_payload = payload.get("media") if isinstance(payload.get("media"), dict) else {}
    for article in (media_payload.get("mentions") or []):
        if isinstance(article, dict):
            add_article(article, "Georgian media")

    for screening in (payload.get("opensanctions") or []):
        if not isinstance(screening, dict):
            continue
        source_id = _graph_source(
            sources,
            name="OpenSanctions",
            url="https://www.opensanctions.org/",
            source_type="Screening database",
        )
        title = screening.get("name") or screening.get("id") or "Screening result"
        screening_url = screening.get("url") or ""
        evidence_id = _graph_evidence(
            evidence,
            source_id=source_id,
            source_name="OpenSanctions",
            title=f"Candidate screening match: {title}",
            source_url=screening_url,
            evidence_type="Screening result",
            note="Candidate match only; identity must be verified by an analyst.",
            identity=screening.get("id") or screening_url or title,
            report_id=report_id,
        )
        screening_id = _graph_entity(
            entities,
            name=title,
            entity_type="Screening record",
            identity=screening.get("id") or title,
            entityRole="Candidate identity record",
            description=", ".join(screening.get("topics") or screening.get("datasets") or []),
            sourceUrl=screening_url,
        )
        score = _safe_float(screening.get("score"))
        confidence = (score / 100.0 if score is not None and score > 1 else score) if score is not None else 0.5
        _graph_link(
            links,
            case_id=case_id,
            from_id=root_id,
            to_id=screening_id,
            relationship_type="Candidate screening match",
            evidence_ids=[evidence_id],
            confidence=confidence,
            verification_status="candidate-match",
            details="A screening hit is not a confirmed identity or finding of wrongdoing.",
        )

    for configured_source in payload.get("sources") or []:
        _graph_source(sources, name=configured_source)

    return {
        "caseId": case_id,
        "rootEntityId": root_id,
        "reportId": report_id,
        "entities": list(entities.values()),
        "relationships": list(links.values()),
        "sources": list(sources.values()),
        "evidence": list(evidence.values()),
    }


def _persist_investigation_graph_bundle(bundle: Dict[str, object]) -> None:
    driver = get_driver()
    case_id = bundle.get("caseId")
    entity_query = """
    MATCH (c:DueDiligenceCase {caseId: $caseId})
    UNWIND $entities AS entity
    MERGE (n:InvestigationEntity {entityId: entity.entityId})
    ON CREATE SET n.createdAt = datetime()
    SET n += entity, n.updatedAt = datetime()
    SET n.canonicalEntityId = coalesce(n.canonicalEntityId, n.entityId)
    MERGE (c)-[:HAS_INVESTIGATION_ENTITY]->(n)
    WITH DISTINCT c
    MATCH (root:InvestigationEntity {entityId: $rootEntityId})
    MERGE (c)-[:INVESTIGATES]->(root)
    """
    source_query = """
    MATCH (c:DueDiligenceCase {caseId: $caseId})
    UNWIND $sources AS source
    MERGE (s:InvestigationDataSource {sourceId: source.sourceId})
    ON CREATE SET s.createdAt = datetime()
    SET s += source, s.updatedAt = datetime()
    MERGE (c)-[:USES_INVESTIGATION_SOURCE]->(s)
    """
    evidence_query = """
    MATCH (c:DueDiligenceCase {caseId: $caseId})
    UNWIND $evidence AS item
    MATCH (s:InvestigationDataSource {sourceId: item.sourceId})
    MERGE (e:InvestigationEvidence {evidenceId: item.evidenceId})
    ON CREATE SET e.createdAt = datetime()
    SET e += item, e.updatedAt = datetime()
    MERGE (c)-[:USES_INVESTIGATION_EVIDENCE]->(e)
    MERGE (e)-[:FROM_SOURCE]->(s)
    """
    relationship_query = """
    UNWIND $relationships AS item
    MATCH (sourceNode:InvestigationEntity {entityId: item.fromEntityId})
    MATCH (targetNode:InvestigationEntity {entityId: item.toEntityId})
    MERGE (sourceNode)-[link:INVESTIGATION_LINK {caseId: $caseId, relationshipId: item.relationshipId}]->(targetNode)
    ON CREATE SET link.createdAt = datetime()
    SET link.relationshipType = item.relationshipType,
        link.schema = item.schema,
        link.ftmSchema = coalesce(item.ftmSchema, link.ftmSchema),
        link.confidence = item.confidence,
        link.verificationStatus = item.verificationStatus,
        link.details = item.details,
        link.lastSeenAt = datetime(),
        link.evidenceIds = reduce(
          collected = [], evidenceId IN coalesce(link.evidenceIds, []) + coalesce(item.evidenceIds, []) |
          CASE WHEN evidenceId IN collected THEN collected ELSE collected + [evidenceId] END
        )
    SET link += coalesce(item.properties, {})
    """
    params = {
        "caseId": case_id,
        "rootEntityId": bundle.get("rootEntityId"),
        "entities": bundle.get("entities") or [],
        "sources": bundle.get("sources") or [],
        "evidence": bundle.get("evidence") or [],
        "relationships": bundle.get("relationships") or [],
    }
    with _db_session(driver) as session:
        _execute_write(session, entity_query, params)
        if params["sources"]:
            _execute_write(session, source_query, params)
        if params["evidence"]:
            _execute_write(session, evidence_query, params)
        if params["relationships"]:
            _execute_write(session, relationship_query, params)
    persist_investigation_projection(bundle)


def _load_investigation_graph(case_id: str) -> Dict[str, object]:
    driver = get_driver()
    case_query = """
    MATCH (c:DueDiligenceCase {caseId: $caseId})
    RETURN c.caseId AS caseId, c.subject AS subject
    """
    entity_query = """
    MATCH (c:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_ENTITY]->(n:InvestigationEntity)
    RETURN n.entityId AS id, n.name AS label, n.entityType AS type,
           coalesce(n.description, '') AS description,
           coalesce(n.isRoot, false) AS isRoot,
           properties(n) AS properties
    ORDER BY n.isRoot DESC, n.entityType, n.name
    """
    relationship_query = """
    MATCH (sourceNode:InvestigationEntity)-[link:INVESTIGATION_LINK {caseId: $caseId}]->(targetNode:InvestigationEntity)
    RETURN link.relationshipId AS id,
           sourceNode.entityId AS source,
           targetNode.entityId AS target,
           link.relationshipType AS label,
           coalesce(link.schema, '') AS schema,
           coalesce(link.confidence, 0.0) AS confidence,
           coalesce(link.verificationStatus, 'unverified') AS verificationStatus,
           coalesce(link.details, '') AS details,
           coalesce(link.evidenceIds, []) AS evidenceIds,
           properties(link) AS properties
    ORDER BY link.relationshipType, sourceNode.name, targetNode.name
    """
    evidence_query = """
    MATCH (c:DueDiligenceCase {caseId: $caseId})-[:USES_INVESTIGATION_EVIDENCE]->(e:InvestigationEvidence)
    RETURN e.evidenceId AS evidenceId, e.sourceId AS sourceId, e.title AS title,
           coalesce(e.sourceName, '') AS sourceName,
           coalesce(e.sourceUrl, '') AS sourceUrl,
           coalesce(e.evidenceType, '') AS evidenceType,
           coalesce(e.publishedAt, '') AS publishedAt,
           coalesce(e.note, '') AS note,
           e.reportId AS reportId,
           properties(e) AS properties
    ORDER BY e.publishedAt DESC, e.title
    """
    source_query = """
    MATCH (c:DueDiligenceCase {caseId: $caseId})-[:USES_INVESTIGATION_SOURCE]->(s:InvestigationDataSource)
    RETURN s.sourceId AS sourceId, s.name AS name,
           coalesce(s.sourceType, '') AS sourceType,
           coalesce(s.url, '') AS url,
           properties(s) AS properties
    ORDER BY s.name
    """
    with _db_session(driver) as session:
        case_records = _execute_read(session, case_query, {"caseId": case_id})
        if not case_records:
            raise HTTPException(status_code=404, detail="Case not found")
        entity_records = _execute_read(session, entity_query, {"caseId": case_id})
        relationship_records = _execute_read(session, relationship_query, {"caseId": case_id})
        evidence_records = _execute_read(session, evidence_query, {"caseId": case_id})
        source_records = _execute_read(session, source_query, {"caseId": case_id})
    nodes = [record.data() for record in entity_records]
    relationships = [record.data() for record in relationship_records]
    evidence_rows = [record.data() for record in evidence_records]
    sources = [record.data() for record in source_records]
    return {
        "caseId": case_id,
        "subject": case_records[0].get("subject"),
        "nodes": nodes,
        "relationships": relationships,
        "evidence": evidence_rows,
        "sources": sources,
        "stats": {
            "entities": len(nodes),
            "relationships": len(relationships),
            "evidence": len(evidence_rows),
            "sources": len(sources),
            "candidateMatches": sum(
                1 for row in relationships if row.get("verificationStatus") == "candidate-match"
            ),
        },
    }


def _ordered_unique(values: List[object]) -> List[str]:
    output: List[str] = []
    for value in values:
        clean_value = str(value or "").strip()
        if clean_value and clean_value not in output:
            output.append(clean_value)
    return output


def _build_investigation_insights(graph: Dict[str, object]) -> Dict[str, object]:
    case_id = str(graph.get("caseId") or "")
    nodes = graph.get("nodes") or []
    relationships = graph.get("relationships") or []
    node_by_id = {str(row.get("id")): row for row in nodes}
    root = next((row for row in nodes if row.get("isRoot")), None)
    insights: List[Dict[str, object]] = []

    def add_insight(
        *,
        lead_type: str,
        title: str,
        summary: str,
        severity: str,
        confidence: float,
        node_ids: List[object],
        relationship_ids: List[object],
        evidence_ids: List[object],
        recommended_next_steps: List[str],
    ) -> None:
        resolved_nodes = _ordered_unique(node_ids)
        resolved_relationships = _ordered_unique(relationship_ids)
        resolved_evidence = _ordered_unique(evidence_ids)
        insight_id = _investigation_id(
            "insight",
            case_id,
            lead_type,
            ",".join(sorted(resolved_nodes)),
            ",".join(sorted(resolved_relationships)),
        )
        insights.append(
            {
                "insightId": insight_id,
                "leadType": lead_type,
                "title": title,
                "summary": summary,
                "severity": severity,
                "priority": {"high": 1, "medium": 2, "low": 3}.get(severity, 3),
                "confidence": round(max(0.0, min(float(confidence), 1.0)), 3),
                "status": "lead",
                "verificationStatus": "requires-review",
                "nodeIds": resolved_nodes,
                "relationshipIds": resolved_relationships,
                "evidenceIds": resolved_evidence,
                "recommendedNextSteps": recommended_next_steps,
            }
        )

    family_links = [
        row for row in relationships if str(row.get("label") or "").startswith("Family:")
    ]
    for family_link in family_links:
        relative_id = str(family_link.get("target") or "")
        relative = node_by_id.get(relative_id)
        if not relative:
            continue
        connected = [
            row
            for row in relationships
            if row.get("source") == relative_id
            and str(row.get("label") or "")
            in {
                "Declared ownership",
                "Declared business interest",
                "Party to declared contract",
            }
        ]
        for connection in connected:
            target = node_by_id.get(str(connection.get("target") or ""))
            if not target:
                continue
            is_contract = connection.get("label") == "Party to declared contract"
            lead_type = "relative_contract_path" if is_contract else "relative_asset_or_business"
            add_insight(
                lead_type=lead_type,
                title=(
                    f"Declared relative-to-contract path for {relative.get('label')}"
                    if is_contract
                    else f"Declared relative-to-{str(target.get('type') or 'entity').lower()} path"
                ),
                summary=(
                    f"{relative.get('label')} is identified as {family_link.get('label')} and is also linked to "
                    f"{target.get('label')} through {connection.get('label')}. This is a documented connection "
                    "that requires contextual review; it is not evidence of wrongdoing by itself."
                ),
                severity="medium" if is_contract or target.get("type") == "Organization" else "low",
                confidence=min(
                    float(family_link.get("confidence") or 0),
                    float(connection.get("confidence") or 0),
                ),
                node_ids=[
                    root.get("id") if root else None,
                    relative_id,
                    target.get("id"),
                ],
                relationship_ids=[family_link.get("id"), connection.get("id")],
                evidence_ids=(family_link.get("evidenceIds") or [])
                + (connection.get("evidenceIds") or []),
                recommended_next_steps=[
                    "Open each cited declaration and verify the relationship and ownership dates.",
                    "Compare the disclosed interest with procurement, company-registry, and beneficial-ownership records.",
                ],
            )

    for person in [row for row in nodes if row.get("type") == "Person"]:
        organization_links = [
            row
            for row in relationships
            if row.get("source") == person.get("id")
            and node_by_id.get(str(row.get("target") or ""), {}).get("type") == "Organization"
            and (
                str(row.get("label") or "").startswith("Held position:")
                or row.get("label") == "Declared business interest"
            )
        ]
        organization_ids = _ordered_unique([row.get("target") for row in organization_links])
        if len(organization_ids) < 3:
            continue
        add_insight(
            lead_type="multi_organization_role",
            title=f"Multiple declared organization roles for {person.get('label')}",
            summary=(
                f"{person.get('label')} is linked to {len(organization_ids)} organizations through declared "
                "positions or business interests. Review timing and role overlap before drawing conclusions."
            ),
            severity="medium",
            confidence=min(float(row.get("confidence") or 0) for row in organization_links),
            node_ids=[person.get("id")] + organization_ids,
            relationship_ids=[row.get("id") for row in organization_links],
            evidence_ids=[
                evidence_id
                for row in organization_links
                for evidence_id in (row.get("evidenceIds") or [])
            ],
            recommended_next_steps=[
                "Build a date-ordered role timeline and check for overlapping public and private interests.",
                "Confirm legal-entity identifiers before merging same-name organizations.",
            ],
        )

    for address in [row for row in nodes if row.get("type") == "Address"]:
        address_links = [
            row
            for row in relationships
            if row.get("target") == address.get("id") and row.get("label") == "Located at"
        ]
        asset_ids = _ordered_unique([row.get("source") for row in address_links])
        if len(asset_ids) < 2:
            continue
        add_insight(
            lead_type="shared_address_hub",
            title=f"Shared address hub: {address.get('label')}",
            summary=(
                f"{len(asset_ids)} declared assets resolve to the same normalized address. Shared addresses can be "
                "legitimate; verify cadastral identifiers and ownership periods before treating this as a network link."
            ),
            severity="low",
            confidence=min(float(row.get("confidence") or 0) for row in address_links),
            node_ids=[address.get("id")] + asset_ids,
            relationship_ids=[row.get("id") for row in address_links],
            evidence_ids=[
                evidence_id
                for row in address_links
                for evidence_id in (row.get("evidenceIds") or [])
            ],
            recommended_next_steps=[
                "Verify the address with cadastral or company-registry identifiers.",
                "Compare acquisition and registration dates to determine whether the overlap is meaningful.",
            ],
        )

    for relationship in [
        row
        for row in relationships
        if row.get("verificationStatus") == "candidate-match"
        and row.get("label") == "Candidate screening match"
    ]:
        candidate = node_by_id.get(str(relationship.get("target") or ""), {})
        add_insight(
            lead_type="candidate_screening_match",
            title=f"Unresolved screening candidate: {candidate.get('label') or 'record'}",
            summary=(
                "A screening source returned a possible name match. This is an identity-resolution task, not a "
                "confirmed match or an adverse finding."
            ),
            severity="medium",
            confidence=float(relationship.get("confidence") or 0),
            node_ids=[relationship.get("source"), relationship.get("target")],
            relationship_ids=[relationship.get("id")],
            evidence_ids=relationship.get("evidenceIds") or [],
            recommended_next_steps=[
                "Compare birth date, jurisdiction, identifiers, aliases, and role history with the subject.",
                "Mark the relationship verified or rejected only after identity resolution.",
            ],
        )

    insights.sort(
        key=lambda row: (
            int(row.get("priority") or 3),
            -float(row.get("confidence") or 0),
            str(row.get("title") or ""),
        )
    )
    return {
        "caseId": case_id,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(insights),
            "high": sum(1 for row in insights if row.get("severity") == "high"),
            "medium": sum(1 for row in insights if row.get("severity") == "medium"),
            "low": sum(1 for row in insights if row.get("severity") == "low"),
            "requiresReview": sum(
                1 for row in insights if row.get("verificationStatus") == "requires-review"
            ),
        },
        "insights": insights,
    }


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
    declaration_sections: List[Dict[str, object]] = []
    if declarations:
        overview_lines: List[str] = []
        property_lines: List[str] = []
        career_lines: List[str] = []
        family_lines: List[str] = []
        vehicle_lines: List[str] = []
        business_lines: List[str] = []
        finance_lines: List[str] = []
        declaration_count = len([row for row in declarations if isinstance(row, dict)])
        latest_submitted = ""

        def _parts(*values: object) -> List[str]:
            return [str(value).strip() for value in values if str(value or "").strip()]

        def _sentence(prefix: str, values: List[str]) -> str:
            return f"{prefix}: " + "; ".join(values) + "." if values else ""

        for declaration in declarations[:4]:
            if not isinstance(declaration, dict):
                continue
            summary_obj = declaration.get("summary") if isinstance(declaration.get("summary"), dict) else {}
            dossier = summary_obj.get("dossier") or {}
            counts = summary_obj.get("counts") or {}
            declarant = dossier.get("declarant") or {}
            submitted = declarant.get("submitted") or declaration.get("declarationSubmitDate") or declaration.get("dateEdited") or "unknown date"
            if not latest_submitted:
                latest_submitted = str(submitted)
            overview_lines.append(
                f"The {submitted} declaration lists {counts.get('properties', 0)} real-estate assets, "
                f"{counts.get('movableProperties', 0)} vehicle or movable-asset record(s), "
                f"{counts.get('enterprises', 0) + counts.get('linkedEnterprises', 0)} business link(s), "
                f"{counts.get('familyMembers', 0)} family member(s), {counts.get('jobs', 0)} job/income record(s), "
                f"and {counts.get('contracts', 0)} contract or obligation record(s)."
            )
            for item in (dossier.get("properties") or [])[:4]:
                line = _sentence(
                    f"Property declared in {submitted}",
                    _parts(item.get("owner"), item.get("type"), item.get("address"), item.get("area") and f"area {item.get('area')}", item.get("share") and f"share {item.get('share')}", item.get("amount")),
                )
                if line:
                    property_lines.append(line)
            for item in (dossier.get("careerAndIncome") or [])[:4]:
                line = _sentence(
                    f"Declared employment income in {submitted}",
                    _parts(item.get("owner"), item.get("organization"), item.get("position"), item.get("period") and item.get("endDate") and f"{item.get('period')} to {item.get('endDate')}", item.get("amount")),
                )
                if line:
                    career_lines.append(line)
            for item in (dossier.get("vehiclesAndMovable") or [])[:4]:
                line = _sentence(
                    f"Vehicle or movable asset declared in {submitted}",
                    _parts(item.get("owner"), item.get("type"), item.get("details"), item.get("acquired") and f"acquired {item.get('acquired')}", item.get("amount")),
                )
                if line:
                    vehicle_lines.append(line)
            for item in (dossier.get("businesses") or [])[:4]:
                line = _sentence(
                    f"Business interest declared in {submitted}",
                    _parts(item.get("name"), item.get("role"), item.get("share") and f"share {item.get('share')}", item.get("amount")),
                )
                if line:
                    business_lines.append(line)
            for item in (dossier.get("linkedBusinesses") or [])[:4]:
                line = _sentence(
                    f"Linked business declared in {submitted}",
                    _parts(item.get("name"), item.get("relation"), item.get("role"), item.get("share") and f"share {item.get('share')}", item.get("amount")),
                )
                if line:
                    business_lines.append(line)
            for item in (dossier.get("familyMembers") or [])[:4]:
                line = _sentence(
                    f"Family member listed in {submitted}",
                    _parts(item.get("name"), item.get("relation"), item.get("birthDate") and f"born {item.get('birthDate')}", item.get("position")),
                )
                if line:
                    family_lines.append(line)
            bank_totals = summary_obj.get("bankAccountTotals") or {}
            cash_totals = summary_obj.get("cashTotals") or {}
            job_totals = summary_obj.get("jobIncomeTotals") or {}
            contract_totals = summary_obj.get("contractAmountTotals") or {}
            contract_income = summary_obj.get("contractIncomeTotals") or {}
            totals_parts = []
            for label, totals in [
                ("bank account balances", bank_totals),
                ("cash", cash_totals),
                ("job income", job_totals),
                ("contract amounts", contract_totals),
                ("contract income/payments", contract_income),
            ]:
                if isinstance(totals, dict) and totals:
                    totals_parts.append(label + " " + ", ".join(f"{amount} {currency}" for currency, amount in totals.items()))
            if totals_parts:
                finance_lines.append(f"The {submitted} declaration reports " + "; ".join(totals_parts) + ".")

        if overview_lines:
            opening = (
                f"The asset-declaration review covers {declaration_count} public declaration record(s)"
                + (f", with the latest submitted on {latest_submitted}." if latest_submitted else ".")
                + " The figures below are self-declared public records and should be verified against source documents before any decision."
            )
            declaration_sections.append({"heading": "Asset Declaration Dossier", "paragraphs": [opening] + overview_lines[:3]})
        if property_lines:
            declaration_sections.append({"heading": "Declared Property Portfolio", "paragraphs": ["The property profile below summarizes real-estate holdings reported in the declarations."], "bullets": property_lines[:10]})
        if career_lines:
            declaration_sections.append({"heading": "Career and Declared Income", "paragraphs": ["Declared employment records show the roles and income amounts reported by the declarant or related persons."], "bullets": career_lines[:10]})
        if family_lines:
            declaration_sections.append({"heading": "Family and Related Parties", "paragraphs": ["Family-member records are relevant for related-party and asset-attribution review."], "bullets": family_lines[:10]})
        if vehicle_lines:
            declaration_sections.append({"heading": "Vehicles and Movable Assets", "paragraphs": ["Movable assets are summarized separately from real estate to make ownership patterns easier to review."], "bullets": vehicle_lines[:8]})
        if business_lines:
            declaration_sections.append({"heading": "Business Interests", "paragraphs": ["Declared enterprise interests and linked businesses should be cross-checked against registry and media records."], "bullets": business_lines[:8]})
        if finance_lines:
            declaration_sections.append({"heading": "Financial and Contract Notes", "paragraphs": finance_lines[:6]})

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
        *declaration_sections,
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
                    {"heading": "Asset Declaration Dossier", "paragraphs": ["narrative overview of declaration coverage and most important declared asset signals"], "bullets": []},
                    {"heading": "Declared Property Portfolio", "paragraphs": ["short interpretation of real-estate holdings"], "bullets": ["one complete sentence per important property or ownership pattern"]},
                    {"heading": "Career and Declared Income", "paragraphs": ["short interpretation of positions, organizations, years, and declared income"], "bullets": ["one complete sentence per role/income pattern"]},
                    {"heading": "Family and Related Parties", "paragraphs": ["short interpretation of listed family members and related-party relevance"], "bullets": ["one complete sentence per relevant family or related-party signal"]},
                    {"heading": "Vehicles, Businesses, and Contracts", "paragraphs": ["short interpretation of vehicles, movable assets, businesses, loans, rent, contracts, and bank/cash signals"], "bullets": ["one complete sentence per important financial or ownership signal"]},
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
            "Treat asset declarations as self-declared public records. Write them as a professional dossier, not as raw bullets. Create separate report sections for declaration overview, declared property portfolio, career and declared income, family and related parties, vehicles/movable assets, business interests, contracts/loans/rent, and bank/cash totals when data is present. Use complete sentences and explain why each category matters for due diligence. Do not dump raw declaration JSON.",
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
            "For asset declarations, write like a professional dossier: use grouped headings, narrative paragraphs, concise findings, amounts with currencies, dates where available, and clear caveats where ownership or family relationship needs verification.",
            "Avoid semicolon-only list items. Convert declaration rows into readable sentences such as: 'The 2018 declaration reports three apartments in Tbilisi, including one 158 sq.m. apartment valued at 50,000 GEL.'",
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
    demo_data_used = False

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
        demo_data_used = True
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
        is_demo=demo_data_used,
    )
    if report_id and case_id:
        try:
            graph_case, graph_report = _case_and_report_for_graph(case_id, report_id)
            graph_bundle = _build_investigation_graph_bundle(graph_case, graph_report)
            _persist_investigation_graph_bundle(graph_bundle)
        except Exception as exc:
            warnings.append(
                f"Report saved, but investigation graph normalization is pending: {exc}"
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
    request: Request = None,
):
    if workflow_v2_enabled():
        return list_cases_v2_for_legacy_route(request, limit=limit)
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
def create_due_diligence_case(payload: DueDiligenceCaseCreate, request: Request = None):
    blocked = legacy_mutation_disabled_response(request, "create_case_v2") if workflow_v2_enabled() else None
    if blocked is not None:
        return blocked
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
def get_due_diligence_case(case_id: str, request: Request = None):
    if workflow_v2_enabled():
        return get_case_v2_for_legacy_route(request, case_id)
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
def update_due_diligence_case(case_id: str, payload: DueDiligenceCaseUpdate, request: Request = None):
    blocked = legacy_mutation_disabled_response(request, "replace_intake_v2") if workflow_v2_enabled() else None
    if blocked is not None:
        return blocked
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
def archive_due_diligence_case(case_id: str, request: Request = None):
    blocked = legacy_mutation_disabled_response(request, "archive_case_draft_be5") if workflow_v2_enabled() else None
    if blocked is not None:
        return blocked
    return update_due_diligence_case(
        case_id,
        DueDiligenceCaseUpdate(status="Archived"),
        request,
    )


@router.delete("/cases/{case_id}")
def delete_due_diligence_case(case_id: str, request: Request = None):
    blocked = legacy_mutation_disabled_response(request, "archive_case_draft_be5") if workflow_v2_enabled() else None
    if blocked is not None:
        return blocked
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
def create_due_diligence_decision(case_id: str, payload: DueDiligenceDecisionCreate, request: Request = None):
    blocked = legacy_mutation_disabled_response(request, "decision_draft_be4") if workflow_v2_enabled() else None
    if blocked is not None:
        return blocked
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


@router.get("/graph/schema")
def get_due_diligence_investigation_graph_schema():
    return {
        "version": "1.1",
        "principles": [
            "Model observable connections separately from analyst conclusions.",
            "Attach provenance, confidence, and verification status to every relationship.",
            "Treat screening results and generated patterns as leads until an analyst verifies identity and context.",
            "Keep social profiles source-scoped; a display-name alias never proves that a profile is an official person.",
            "Keep node types extensible so new registries can add addresses, jurisdictions, intermediaries, and documents.",
        ],
        "nodeTypes": [
            {"type": "Person", "role": "Public official, relative, officer, or associated person", "description": "A natural person named by a source."},
            {"type": "Organization", "role": "Legal entity, institution, employer, or agency", "description": "A company, public body, trust, fund, or other organization."},
            {"type": "Intermediary", "role": "Agent or professional facilitator", "description": "A person or organization that creates, administers, or connects legal entities."},
            {"type": "Asset", "role": "Declared or discovered asset", "description": "Real property, movable property, security, or other asset."},
            {"type": "Contract", "role": "Agreement or procurement record", "description": "A contract linked to a person, organization, or public agency."},
            {"type": "Address", "role": "Declared or registered address", "description": "A normalized location that can reveal shared-registration patterns."},
            {"type": "Jurisdiction", "role": "Country or legal jurisdiction", "description": "The jurisdiction attached to an entity, address, or filing."},
            {"type": "Article", "role": "Source document", "description": "A media or public-source document captured as evidence."},
            {"type": "Screening record", "role": "Candidate identity record", "description": "A possible screening match that still requires identity resolution."},
            {"type": "Social profile", "role": "Source-scoped public social profile", "description": "A platform profile whose display name is an alias, not a resolved official identity."},
            {"type": "Social group", "role": "Public social-media group", "description": "A public group observed through a cited collection run."},
            {"type": "Social post", "role": "Public social-media post", "description": "A post preserved with its source URL, record checksum, timestamps, and engagement snapshot."},
            {"type": "Social comment", "role": "Public social-media comment", "description": "A collected comment linked to its post and source-scoped profile."},
            {"type": "Vehicle", "role": "Movable asset", "description": "A car or other vehicle supported by registry, declaration, or reviewed source evidence."},
            {"type": "Real estate", "role": "Immovable asset", "description": "Land, buildings, or other real property supported by cited evidence."},
            {"type": "Vessel", "role": "Maritime asset", "description": "A vessel identified by cited registry or source data."},
            {"type": "Airplane", "role": "Aviation asset", "description": "An aircraft identified by cited registry or source data."},
        ],
        "relationshipTypes": [
            {"label": "Family: {relationship}", "description": "A family relationship stated by a cited source."},
            {"label": "Declared ownership", "description": "A person is stated as an owner of an asset."},
            {"label": "Declared business interest", "description": "A person is stated as having a role or share in a legal entity."},
            {"label": "Held position: {role}", "description": "A person held a cited role in an organization."},
            {"label": "Party to declared contract", "description": "A person or organization is linked to a declared contract."},
            {"label": "Contract counterparty", "description": "An agency or organization is the cited counterparty to a contract."},
            {"label": "Located at", "description": "An asset or legal entity resolves to a cited address."},
            {"label": "Mentioned in article", "description": "A source search produced an article candidate that must be opened and verified."},
            {"label": "Candidate screening match", "description": "A screening result may refer to the subject; identity is not confirmed."},
        ],
        "verificationStatuses": [
            {"value": "source-stated", "label": "Source stated", "meaning": "The cited source explicitly states the connection; context still requires review."},
            {"value": "candidate-match", "label": "Candidate match", "meaning": "Name or source matching produced a lead that is not identity-resolved."},
            {"value": "analyst-added", "label": "Analyst added", "meaning": "An analyst recorded the connection and supplied a source and evidence note."},
            {"value": "verified", "label": "Verified", "meaning": "An analyst completed identity and source verification."},
            {"value": "unverified", "label": "Unverified", "meaning": "The connection has not yet been checked."},
        ],
        "leadTypes": [
            {"value": "relative_asset_or_business", "label": "Relative asset or business path", "description": "A declared relative is connected to a disclosed asset or legal entity."},
            {"value": "relative_contract_path", "label": "Relative contract path", "description": "A declared relative is connected to a disclosed contract."},
            {"value": "multi_organization_role", "label": "Multiple organization roles", "description": "One person is linked to at least three organizations."},
            {"value": "shared_address_hub", "label": "Shared address hub", "description": "At least two assets or entities resolve to the same normalized address."},
            {"value": "candidate_screening_match", "label": "Candidate screening match", "description": "A screening record still requires identity resolution."},
        ],
    }


@router.get("/cases/{case_id}/graph")
def get_due_diligence_investigation_graph(case_id: str):
    return _load_investigation_graph(case_id)


@router.get("/cases/{case_id}/graph/insights")
def get_due_diligence_investigation_graph_insights(case_id: str):
    return _build_investigation_insights(_load_investigation_graph(case_id))


@router.post("/cases/{case_id}/graph/enrich")
def enrich_due_diligence_investigation_graph(
    case_id: str, payload: InvestigationGraphEnrichRequest
):
    case_row, report = _case_and_report_for_graph(case_id, payload.report_id)
    if not report.get("reportId"):
        raise HTTPException(
            status_code=409,
            detail="Run an investigation first so the graph has saved evidence to enrich from.",
        )
    bundle = _build_investigation_graph_bundle(case_row, report)
    _persist_investigation_graph_bundle(bundle)
    graph = _load_investigation_graph(case_id)
    graph["enrichment"] = {
        "reportId": report.get("reportId"),
        "entitiesProcessed": len(bundle.get("entities") or []),
        "relationshipsProcessed": len(bundle.get("relationships") or []),
        "evidenceProcessed": len(bundle.get("evidence") or []),
        "message": "Saved evidence was normalized into the investigation graph.",
    }
    return graph


@router.post("/cases/{case_id}/graph/relationships")
def add_due_diligence_investigation_relationship(
    case_id: str, payload: InvestigationRelationshipCreate
):
    case_row, report = _case_and_report_for_graph(case_id)
    base_bundle = _build_investigation_graph_bundle(
        case_row, {"reportId": None, "payload": {}}
    )
    existing_graph = _load_investigation_graph(case_id)
    existing_ids = {str(row.get("id")) for row in existing_graph.get("nodes") or []}
    existing_ids.update(str(row.get("entityId")) for row in base_bundle.get("entities") or [])
    from_id = payload.from_entity_id or base_bundle.get("rootEntityId")
    if not from_id or str(from_id) not in existing_ids:
        raise HTTPException(
            status_code=400,
            detail="fromEntityId must identify an entity already attached to this case.",
        )

    entities = {
        str(row.get("entityId")): row for row in base_bundle.get("entities") or []
    }
    relationships: Dict[str, Dict[str, object]] = {}
    sources: Dict[str, Dict[str, object]] = {}
    evidence: Dict[str, Dict[str, object]] = {}
    target_type = _clean_decl_text(payload.target_type)[:60] or "Person"
    target_id = _graph_entity(
        entities,
        name=payload.target_name,
        entity_type=target_type,
        identity=f"manual|{target_type}|{payload.target_name}",
        entityRole={
            "Person": "Associated person",
            "Organization": "Legal entity",
            "Address": "Address",
            "Jurisdiction": "Jurisdiction",
            "Intermediary": "Intermediary",
        }.get(target_type, target_type),
        description="Entity added by an analyst with cited evidence",
    )
    source_id = _graph_source(
        sources,
        name=payload.source_name,
        url=payload.source_url or "",
        source_type="Analyst source",
    )
    evidence_id = _graph_evidence(
        evidence,
        source_id=source_id,
        source_name=payload.source_name,
        title=f"Analyst evidence: {payload.relationship_type}",
        source_url=payload.source_url or "",
        evidence_type="Analyst-submitted evidence",
        note=payload.evidence_note,
        identity=f"{payload.source_url}|{payload.evidence_note}",
        report_id=report.get("reportId"),
    )
    allowed_statuses = {"unverified", "candidate-match", "source-stated", "analyst-added", "verified"}
    verification_status = _clean_decl_text(payload.verification_status).casefold()
    if verification_status not in allowed_statuses:
        verification_status = "analyst-added"
    _graph_link(
        relationships,
        case_id=case_id,
        from_id=str(from_id),
        to_id=target_id,
        relationship_type=payload.relationship_type[:100],
        evidence_ids=[evidence_id],
        confidence=payload.confidence,
        verification_status=verification_status,
        details=payload.evidence_note,
    )
    bundle = {
        "caseId": case_id,
        "rootEntityId": base_bundle.get("rootEntityId"),
        "entities": list(entities.values()),
        "relationships": list(relationships.values()),
        "sources": list(sources.values()),
        "evidence": list(evidence.values()),
    }
    _persist_investigation_graph_bundle(bundle)
    graph = _load_investigation_graph(case_id)
    graph["enrichment"] = {
        "message": "Documented relationship added with linked evidence.",
        "relationshipId": next(iter(relationships), None),
        "evidenceId": evidence_id,
    }
    return graph


@router.post("/cases/{case_id}/graph/import")
def import_due_diligence_investigation_graph(
    case_id: str, payload: InvestigationGraphImportRequest
):
    case_row, _ = _case_and_report_for_graph(case_id)
    base_bundle = _build_investigation_graph_bundle(
        case_row, {"reportId": None, "payload": {}}
    )
    existing_graph = _load_investigation_graph(case_id)
    attached_entity_ids = {
        str(row.get("id")) for row in existing_graph.get("nodes") or [] if row.get("id")
    }
    attached_entity_ids.update(
        str(row.get("entityId"))
        for row in base_bundle.get("entities") or []
        if row.get("entityId")
    )

    external_ids = [row.external_id.strip() for row in payload.entities]
    duplicate_external_ids = sorted(
        {external_id for external_id in external_ids if external_ids.count(external_id) > 1}
    )
    if duplicate_external_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                "externalId values must be unique within an import request. Duplicates: "
                + ", ".join(duplicate_external_ids[:10])
            ),
        )

    entities = {
        str(row.get("entityId")): row for row in base_bundle.get("entities") or []
    }
    relationships: Dict[str, Dict[str, object]] = {}
    sources: Dict[str, Dict[str, object]] = {}
    evidence: Dict[str, Dict[str, object]] = {}
    source_id = _graph_source(
        sources,
        name=payload.source.name,
        url=payload.source.url or "",
        source_type=payload.source.source_type or "Imported dataset",
        publisher=payload.source.publisher,
        license=payload.source.license,
        jurisdiction=payload.source.jurisdiction,
        description=payload.source.description,
        ingestionMode=payload.source.ingestion_mode,
    )
    entity_id_by_external: Dict[str, str] = {}
    for imported in payload.entities:
        external_id = imported.external_id.strip()
        if imported.existing_entity_id:
            existing_entity_id = imported.existing_entity_id.strip()
            if existing_entity_id not in attached_entity_ids:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"existingEntityId for {external_id} must identify an entity already attached to this case."
                    ),
                )
            entity_id_by_external[external_id] = existing_entity_id
            continue
        custom_properties = _safe_investigation_properties(imported.properties)
        entity_id = _graph_entity(
            entities,
            name=imported.name,
            entity_type=_clean_decl_text(imported.entity_type)[:60],
            identity=f"{source_id}|{external_id}",
            entityRole=_clean_decl_text(imported.entity_role)[:100],
            description=_clean_decl_text(imported.description)[:1000],
            sourceId=source_id,
            sourceExternalId=external_id,
            **custom_properties,
        )
        if entity_id:
            entity_id_by_external[external_id] = entity_id

    allowed_statuses = {
        "unverified",
        "candidate-match",
        "source-stated",
        "analyst-added",
        "verified",
    }
    for imported_link in payload.relationships:
        from_external_id = imported_link.from_external_id.strip()
        to_external_id = imported_link.to_external_id.strip()
        from_id = entity_id_by_external.get(from_external_id)
        to_id = entity_id_by_external.get(to_external_id)
        if not from_id or not to_id:
            missing = [
                external_id
                for external_id, resolved in [
                    (from_external_id, from_id),
                    (to_external_id, to_id),
                ]
                if not resolved
            ]
            raise HTTPException(
                status_code=400,
                detail=(
                    "Every relationship endpoint must resolve to an entity declared in this import request. "
                    f"Unresolved externalId values: {', '.join(missing)}"
                ),
            )
        verification_status = _clean_decl_text(
            imported_link.verification_status
        ).casefold()
        if verification_status not in allowed_statuses:
            verification_status = "source-stated"
        evidence_row = imported_link.evidence
        evidence_id = _graph_evidence(
            evidence,
            source_id=source_id,
            source_name=payload.source.name,
            title=evidence_row.title,
            source_url=evidence_row.source_url or payload.source.url or "",
            evidence_type="Imported source record",
            published_at=evidence_row.published_at,
            note=evidence_row.note,
            identity=(
                f"{from_external_id}|{to_external_id}|{imported_link.relationship_type}|"
                f"{evidence_row.source_url}|{evidence_row.title}|{evidence_row.note}"
            ),
        )
        _graph_link(
            relationships,
            case_id=case_id,
            from_id=from_id,
            to_id=to_id,
            relationship_type=imported_link.relationship_type[:100],
            evidence_ids=[evidence_id],
            confidence=imported_link.confidence,
            verification_status=verification_status,
            details=imported_link.details or evidence_row.note,
            properties=imported_link.properties,
        )

    bundle = {
        "caseId": case_id,
        "rootEntityId": base_bundle.get("rootEntityId"),
        "entities": list(entities.values()),
        "relationships": list(relationships.values()),
        "sources": list(sources.values()),
        "evidence": list(evidence.values()),
    }
    _persist_investigation_graph_bundle(bundle)
    import_run_id = _investigation_id(
        "import-run", case_id, source_id, datetime.now(timezone.utc).isoformat()
    )
    import_run_query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
    MATCH (source:InvestigationDataSource {sourceId: $sourceId})
    CREATE (run:InvestigationImportRun {
      runId: $runId, caseId: $caseId, sourceId: $sourceId,
      status: 'completed', entityCount: $entityCount,
      relationshipCount: $relationshipCount, evidenceCount: $evidenceCount,
      errorCount: 0, startedAt: datetime(), completedAt: datetime()
    })
    MERGE (caseNode)-[:HAS_IMPORT_RUN]->(run)
    MERGE (source)-[:HAS_IMPORT_RUN]->(run)
    RETURN run.runId AS runId
    """
    with _db_session(get_driver()) as session:
        _execute_write(
            session,
            import_run_query,
            {
                "caseId": case_id,
                "sourceId": source_id,
                "runId": import_run_id,
                "entityCount": len(payload.entities),
                "relationshipCount": len(payload.relationships),
                "evidenceCount": len(evidence),
            },
        )
    graph = _load_investigation_graph(case_id)
    graph["importResult"] = {
        "runId": import_run_id,
        "sourceId": source_id,
        "entitiesProcessed": len(payload.entities),
        "relationshipsProcessed": len(payload.relationships),
        "evidenceProcessed": len(evidence),
        "message": "Source-scoped entities and evidence-linked relationships were imported.",
    }
    return graph


def _ftm_values(properties: Dict[str, List[str]], *names: str) -> List[str]:
    values: List[str] = []
    for name in names:
        for value in properties.get(name) or []:
            clean = str(value or "").strip()
            if clean and clean not in values:
                values.append(clean)
    return values


def _ftm_caption(schema_name: str, entity_id: str, properties: Dict[str, List[str]]) -> str:
    names = _ftm_values(
        properties,
        "name",
        "title",
        "caption",
        "legalName",
        "number",
        "registrationNumber",
    )
    return names[0] if names else f"{schema_name} {entity_id}"


def _ftm_edge_details(schema_name: str, properties: Dict[str, List[str]]) -> str:
    parts: List[str] = []
    for key in [
        "role",
        "title",
        "summary",
        "purpose",
        "amount",
        "currency",
        "startDate",
        "endDate",
        "date",
    ]:
        values = _ftm_values(properties, key)
        if values:
            parts.append(f"{key}: {', '.join(values[:3])}")
    return "; ".join(parts) or f"Imported FollowTheMoney {schema_name} relationship."


@router.post("/cases/{case_id}/graph/import/ftm")
def import_followthemoney_investigation_graph(
    case_id: str, payload: FollowTheMoneyGraphImportRequest
):
    """Import native FollowTheMoney entities without auto-merging identities.

    FtM relationship/interstitial entities become graph relationships, while
    their own stable ID and literal properties remain statement subjects.
    """
    case_row, _ = _case_and_report_for_graph(case_id)
    base_bundle = _build_investigation_graph_bundle(
        case_row, {"reportId": None, "payload": {}}
    )
    existing_graph = _load_investigation_graph(case_id)
    existing_nodes = {
        str(row.get("id")): row
        for row in existing_graph.get("nodes") or []
        if row.get("id")
    }
    attached_entity_ids = set(existing_nodes)
    attached_entity_ids.update(
        str(row.get("entityId"))
        for row in base_bundle.get("entities") or []
        if row.get("entityId")
    )

    external_ids = [entity.id.strip() for entity in payload.entities]
    duplicate_external_ids = sorted(
        {external_id for external_id in external_ids if external_ids.count(external_id) > 1}
    )
    if duplicate_external_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                "FollowTheMoney entity id values must be unique within an import request. Duplicates: "
                + ", ".join(duplicate_external_ids[:10])
            ),
        )

    validated: List[Tuple[FollowTheMoneyImportEntity, Dict[str, object], Dict[str, object]]] = []
    warnings: List[str] = []
    for entity in payload.entities:
        raw = {
            "id": entity.id,
            "schema": entity.schema_name,
            "properties": entity.properties,
            "datasets": entity.datasets or [payload.dataset.id],
            "referents": entity.referents,
            "firstSeen": entity.first_seen,
            "lastSeen": entity.last_seen,
            "lastChange": entity.last_change,
        }
        try:
            normalized, entity_warnings = validate_ftm_entity(raw)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        schema_meta = ftm_schema_metadata(str(normalized.get("schema") or ""))
        if schema_meta is None:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported FollowTheMoney schema: {normalized.get('schema')}",
            )
        validated.append((entity, normalized, schema_meta))
        warnings.extend(entity_warnings)

    entities = {
        str(row.get("entityId")): row for row in base_bundle.get("entities") or []
    }
    relationships: Dict[str, Dict[str, object]] = {}
    evidence: Dict[str, Dict[str, object]] = {}
    source_id = _investigation_id(
        "source", payload.dataset.id.strip(), payload.dataset.name.strip()
    )
    sources: Dict[str, Dict[str, object]] = {
        source_id: {
            "sourceId": source_id,
            "datasetId": payload.dataset.id.strip(),
            "name": payload.dataset.name.strip(),
            "sourceType": "FollowTheMoney dataset",
            "url": _clean_decl_text(payload.dataset.url),
            "publisher": _clean_decl_text(payload.dataset.publisher),
            "license": _clean_decl_text(payload.dataset.license),
            "jurisdiction": _clean_decl_text(payload.dataset.jurisdiction),
            "description": _clean_decl_text(payload.dataset.description),
            "ingestionMode": "followthemoney-json",
            "format": "FollowTheMoney",
        }
    }

    entity_id_by_external: Dict[str, str] = {}
    evidence_id_by_external: Dict[str, str] = {}
    node_count = 0
    edge_count = 0

    for input_entity, normalized, schema_meta in validated:
        if schema_meta.get("edge"):
            continue
        external_id = str(normalized.get("id") or "")
        schema_name = str(normalized.get("schema") or "Thing")
        properties = normalized.get("properties") or {}
        assert isinstance(properties, dict)
        caption = _ftm_caption(schema_name, external_id, properties)
        source_urls = _ftm_values(properties, "sourceUrl", "url", "website")
        published = _ftm_values(
            properties, "publishedAt", "date", "modifiedAt", "retrievedAt"
        )
        evidence_id = _graph_evidence(
            evidence,
            source_id=source_id,
            source_name=payload.dataset.name,
            title=f"{schema_name}: {caption}",
            source_url=source_urls[0] if source_urls else payload.dataset.url,
            evidence_type="FollowTheMoney source entity",
            published_at=published[0] if published else input_entity.last_seen,
            note=(
                f"Imported FollowTheMoney {schema_name} entity {external_id} "
                f"from dataset {payload.dataset.id}."
            ),
            identity=f"{payload.dataset.id}|{external_id}",
        )
        evidence_id_by_external[external_id] = evidence_id

        if input_entity.existing_entity_id:
            entity_id = input_entity.existing_entity_id.strip()
            if entity_id not in attached_entity_ids:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"existingEntityId for {external_id} must identify an entity already attached to this case."
                    ),
                )
            existing = existing_nodes.get(entity_id) or {}
            existing_properties = existing.get("properties") or {}
            entities[entity_id] = {
                "entityId": entity_id,
                "name": existing.get("label") or existing_properties.get("name") or caption,
                "entityType": existing.get("type") or existing_properties.get("entityType") or schema_name,
            }
        else:
            entity_id = _graph_entity(
                entities,
                name=caption,
                entity_type=schema_name,
                identity=f"{source_id}|{external_id}",
            )
            if not entity_id:
                raise HTTPException(
                    status_code=422,
                    detail=f"FollowTheMoney entity {external_id} has no usable caption",
                )
        entity_id_by_external[external_id] = entity_id
        row = entities[entity_id]
        names = _ftm_values(properties, "name", "alias", "weakAlias", "previousName")
        identifiers: List[str] = []
        for prop_name, prop_values in properties.items():
            if infer_ftm_property_type(str(prop_name)) == "identifier":
                identifiers.extend(str(value) for value in prop_values)
        birth_dates = _ftm_values(properties, "birthDate")
        row.update(
            {
                "sourceId": source_id,
                "sourceExternalId": external_id,
                "ftmSchema": schema_name,
                "ftmDatasets": normalized.get("datasets") or [payload.dataset.id],
                "ftmReferents": normalized.get("referents") or [],
                "ftmPropertiesJson": json.dumps(
                    properties, ensure_ascii=False, sort_keys=True
                ),
                "evidenceIds": _ordered_unique(
                    list(row.get("evidenceIds") or []) + [evidence_id]
                ),
                "firstSeen": normalized.get("firstSeen") or "",
                "lastSeen": normalized.get("lastSeen") or "",
                "lastChange": normalized.get("lastChange") or "",
                "identifierIssuer": (
                    _clean_decl_text(payload.dataset.jurisdiction)
                    or _clean_decl_text(payload.dataset.id)
                ),
                "identifierJurisdiction": _clean_decl_text(
                    payload.dataset.jurisdiction
                ),
            }
        )
        if names:
            row["aliases"] = _ordered_unique(
                list(row.get("aliases") or []) + [name for name in names if name != caption]
            )
        addresses = _ftm_values(properties, "address", "registeredAddress")
        if addresses:
            row["address"] = addresses[0]
        jurisdictions = _ftm_values(
            properties, "jurisdiction", "country", "nationality"
        )
        if jurisdictions:
            row["jurisdiction"] = jurisdictions
        if identifiers:
            row["identifiers"] = _ordered_unique(identifiers)
        if birth_dates:
            row["birthYear"] = birth_dates[0][:4]
        roles = _ftm_values(properties, "role", "position", "topics")
        if roles:
            row["entityRole"] = ", ".join(roles[:5])
        descriptions = _ftm_values(properties, "summary", "notes", "description")
        if descriptions:
            row["description"] = descriptions[0]
        node_count += 1

    for input_entity, normalized, schema_meta in validated:
        if not schema_meta.get("edge"):
            continue
        external_id = str(normalized.get("id") or "")
        schema_name = str(normalized.get("schema") or "")
        properties = normalized.get("properties") or {}
        assert isinstance(properties, dict)
        source_prop = str(schema_meta.get("sourceProp") or "")
        target_prop = str(schema_meta.get("targetProp") or "")
        source_external_ids = _ftm_values(properties, source_prop)
        target_external_ids = _ftm_values(properties, target_prop)
        if not source_external_ids or not target_external_ids:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"FollowTheMoney edge {external_id} ({schema_name}) must define "
                    f"{source_prop} and {target_prop}."
                ),
            )
        unresolved = sorted(
            {
                ref
                for ref in source_external_ids + target_external_ids
                if ref not in entity_id_by_external
            }
        )
        if unresolved:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Every FollowTheMoney relationship endpoint must resolve to an imported id "
                    "or an entity with explicit existingEntityId. Unresolved ids: "
                    + ", ".join(unresolved[:20])
                ),
            )
        source_urls = _ftm_values(properties, "sourceUrl", "url")
        published = _ftm_values(properties, "date", "startDate", "modifiedAt")
        evidence_id = _graph_evidence(
            evidence,
            source_id=source_id,
            source_name=payload.dataset.name,
            title=f"{schema_name}: {external_id}",
            source_url=source_urls[0] if source_urls else payload.dataset.url,
            evidence_type="FollowTheMoney relationship entity",
            published_at=published[0] if published else input_entity.last_seen,
            note=(
                f"Imported FollowTheMoney {schema_name} relationship entity {external_id} "
                f"from dataset {payload.dataset.id}."
            ),
            identity=f"{payload.dataset.id}|{external_id}",
        )
        evidence_id_by_external[external_id] = evidence_id
        edge_properties = {
            key: values
            for key, values in properties.items()
            if key not in {source_prop, target_prop}
        }
        edge_properties["ftmEntityId"] = external_id
        for source_external_id in source_external_ids:
            for target_external_id in target_external_ids:
                source_entity_id = entity_id_by_external[source_external_id]
                target_entity_id = entity_id_by_external[target_external_id]
                if source_entity_id == target_entity_id:
                    warnings.append(
                        f"{external_id}: ignored self-referencing {schema_name} relationship"
                    )
                    continue
                relationship_id = _investigation_id(
                    "link",
                    case_id,
                    source_entity_id,
                    target_entity_id,
                    schema_name,
                    external_id,
                )
                _graph_link(
                    relationships,
                    case_id=case_id,
                    from_id=source_entity_id,
                    to_id=target_entity_id,
                    relationship_type=schema_name,
                    evidence_ids=[evidence_id],
                    confidence=1.0,
                    verification_status="source-stated",
                    details=_ftm_edge_details(schema_name, properties),
                    relationship_id=relationship_id,
                    properties=edge_properties,
                    ftm_schema=schema_name,
                )
                edge_count += 1

    bundle = {
        "caseId": case_id,
        "rootEntityId": base_bundle.get("rootEntityId"),
        "entities": list(entities.values()),
        "relationships": list(relationships.values()),
        "sources": list(sources.values()),
        "evidence": list(evidence.values()),
    }
    _persist_investigation_graph_bundle(bundle)
    import_run_id = _investigation_id(
        "import-run",
        case_id,
        source_id,
        datetime.now(timezone.utc).isoformat(),
    )
    import_run_query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
    MATCH (source:InvestigationDataSource {sourceId: $sourceId})
    CREATE (run:InvestigationImportRun {
      runId: $runId, caseId: $caseId, sourceId: $sourceId,
      format: 'FollowTheMoney', status: 'completed', entityCount: $entityCount,
      relationshipCount: $relationshipCount, evidenceCount: $evidenceCount,
      warningCount: $warningCount, warnings: $warnings, errorCount: 0,
      startedAt: datetime(), completedAt: datetime()
    })
    MERGE (caseNode)-[:HAS_IMPORT_RUN]->(run)
    MERGE (source)-[:HAS_IMPORT_RUN]->(run)
    RETURN run.runId AS runId
    """
    with _db_session(get_driver()) as session:
        _execute_write(
            session,
            import_run_query,
            {
                "caseId": case_id,
                "sourceId": source_id,
                "runId": import_run_id,
                "entityCount": node_count,
                "relationshipCount": edge_count,
                "evidenceCount": len(evidence),
                "warningCount": len(warnings),
                "warnings": warnings[:100],
            },
        )
    graph = _load_investigation_graph(case_id)
    graph["importResult"] = {
        "runId": import_run_id,
        "sourceId": source_id,
        "datasetId": payload.dataset.id,
        "format": "FollowTheMoney",
        "entitiesProcessed": node_count,
        "relationshipsProcessed": edge_count,
        "evidenceProcessed": len(evidence),
        "warnings": warnings,
        "message": (
            "FollowTheMoney entities were validated, source-scoped, and imported with "
            "statement-level provenance; no identities were auto-merged."
        ),
    }
    return graph


@router.get("/data-sources")
def list_due_diligence_investigation_sources():
    driver = get_driver()
    query = """
    MATCH (source:InvestigationDataSource)
    OPTIONAL MATCH (caseNode:DueDiligenceCase)-[:USES_INVESTIGATION_SOURCE]->(source)
    RETURN source.sourceId AS sourceId, source.name AS name,
           coalesce(source.sourceType, '') AS sourceType,
           coalesce(source.url, '') AS url,
           count(DISTINCT caseNode) AS caseCount,
           toString(source.updatedAt) AS updatedAt
    ORDER BY source.name
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query)
    return [record.data() for record in records]


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


# ---------------------------------------------------------------------------
# One-click full check
#
# Runs every configured due-diligence source for a case and reports an honest
# per-source status. A source that is not configured, or that is blocked by a
# permission gate, must never fail the whole call and must never be silently
# dropped from the response: it is reported with "not-configured"/"blocked" and
# a detail naming the exact environment variable an operator has to set.
# ---------------------------------------------------------------------------

FULL_CHECK_STATUS_OK = "ok"
FULL_CHECK_STATUS_NO_DATA = "no-data"
FULL_CHECK_STATUS_NOT_CONFIGURED = "not-configured"
FULL_CHECK_STATUS_BLOCKED = "blocked"
FULL_CHECK_STATUS_ERROR = "error"

FULL_CHECK_SOURCE_LABELS: Dict[str, str] = {
    "wikidata": "Wikidata",
    "wikipedia": "Wikipedia",
    "opensanctions": "OpenSanctions (sanctions & PEP screening)",
    "news": "International news (GDELT)",
    "declarations": "Georgian asset declarations",
    "georgian-media": "Georgian media monitor",
    "company-registry": "Georgian company registry (Companyinfo.ge)",
    "facebook": "Facebook public groups (Apify)",
}

# Order matters: the first matching keyword wins, so more specific source names
# are checked before the generic local-media keywords.
_FULL_CHECK_WARNING_ROUTES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("wikidata", ("wikidata",)),
    ("wikipedia", ("wikipedia",)),
    ("opensanctions", ("opensanctions",)),
    ("news", ("gdelt",)),
    ("declarations", ("declaration",)),
    (
        "georgian-media",
        (
            "netgazeti",
            "publika",
            "interpressnews",
            "local media",
            "media monitor",
            "rss",
            "georgian media",
        ),
    ),
)


def _full_check_source(
    source_id: str,
    status: str,
    detail: str,
    hit_count: int = 0,
    requires_configuration: bool = False,
) -> Dict[str, object]:
    return {
        "id": source_id,
        "label": FULL_CHECK_SOURCE_LABELS.get(source_id, source_id),
        "status": status,
        "hitCount": int(hit_count or 0),
        "detail": detail,
        "requiresConfiguration": bool(requires_configuration),
    }


def _full_check_warnings_by_source(warnings: List[str]) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = {}
    for warning in warnings:
        text = str(warning or "").strip()
        if not text:
            continue
        lowered = text.casefold()
        for source_id, keywords in _FULL_CHECK_WARNING_ROUTES:
            if any(keyword in lowered for keyword in keywords):
                grouped.setdefault(source_id, []).append(text)
                break
    return grouped


# Warnings that only mean "the source ran and matched nothing". These must not
# be reported as errors: an empty result is data, a failure is not.
_FULL_CHECK_NO_MATCH_PHRASES: Tuple[str, ...] = (
    "no extractable matches",
    "no matches",
    "no mentions found",
    "found no matches",
    "returned no ",
    "no results",
)


def _full_check_is_no_match_notice(text: str) -> bool:
    lowered = str(text or "").casefold()
    return any(phrase in lowered for phrase in _FULL_CHECK_NO_MATCH_PHRASES)


def _full_check_core_source(
    source_id: str,
    hit_count: int,
    warnings: List[str],
    *,
    ok_detail: str,
    empty_detail: str,
) -> Dict[str, object]:
    """Derive an honest status for one of the sources driven by /analyze."""
    if warnings:
        joined = " ".join(warnings)
        lowered = joined.casefold()
        if "not configured" in lowered or "no api key" in lowered:
            env_var = "OPENSANCTIONS_API_KEY" if source_id == "opensanctions" else ""
            detail = (
                f"Not configured: set {env_var} to enable this source."
                if env_var
                else f"Not configured: {joined}"
            )
            return _full_check_source(
                source_id,
                FULL_CHECK_STATUS_NOT_CONFIGURED,
                detail,
                hit_count=hit_count,
                requires_configuration=True,
            )
        failures = [
            item for item in warnings if not _full_check_is_no_match_notice(item)
        ]
        notices = [item for item in warnings if _full_check_is_no_match_notice(item)]
        if hit_count:
            if not failures:
                return _full_check_source(
                    source_id, FULL_CHECK_STATUS_OK, ok_detail, hit_count=hit_count
                )
            return _full_check_source(
                source_id,
                FULL_CHECK_STATUS_OK,
                f"{ok_detail} Partial problems: {' '.join(failures)}",
                hit_count=hit_count,
            )
        if failures:
            return _full_check_source(
                source_id, FULL_CHECK_STATUS_ERROR, " ".join(failures)
            )
        # Only "nothing matched" notices: the source worked, it just found nothing.
        return _full_check_source(
            source_id, FULL_CHECK_STATUS_NO_DATA, " ".join(notices) or empty_detail
        )
    if hit_count:
        return _full_check_source(
            source_id, FULL_CHECK_STATUS_OK, ok_detail, hit_count=hit_count
        )
    return _full_check_source(source_id, FULL_CHECK_STATUS_NO_DATA, empty_detail)


def _full_check_identification_codes(case_id: str) -> List[str]:
    """Identification codes already recorded on this case's investigation graph.

    The Georgian company registry can only be queried by identification code.
    We never invent one: this returns codes that are already stored for the
    case, and an empty list when the case has none.
    """
    query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
    OPTIONAL MATCH (caseNode)-[:HAS_INVESTIGATION_ENTITY]->(entity:InvestigationEntity)
    WHERE entity.identificationCode IS NOT NULL
      AND trim(toString(entity.identificationCode)) <> ''
    WITH caseNode, collect(DISTINCT trim(toString(entity.identificationCode))) AS entityCodes
    OPTIONAL MATCH (caseNode)-[:HAS_COMPANY_ENRICHMENT_JOB]->(job:CompanyRegistryEnrichmentJob)
    WHERE job.identificationCode IS NOT NULL
      AND trim(toString(job.identificationCode)) <> ''
    WITH entityCodes + collect(DISTINCT trim(toString(job.identificationCode))) AS codes
    RETURN codes AS codes
    """
    try:
        with _db_session(get_driver()) as session:
            records = _execute_read(session, query, {"caseId": case_id})
    except Exception:
        return []
    if not records:
        return []
    raw = records[0].get("codes") or []
    seen: List[str] = []
    for value in raw:
        code = str(value or "").strip()
        if code and code not in seen:
            seen.append(code)
    return seen


def _full_check_facebook_snapshot(case_id: str) -> Dict[str, object]:
    """Count Facebook material already imported for this case.

    This is read-only on purpose. The full check never starts a paid managed
    Apify run; it only surfaces what has already been imported.
    """
    query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
    OPTIONAL MATCH (caseNode)-[:HAS_INVESTIGATION_ENTITY]->(entity:InvestigationEntity {platform: 'facebook'})
    WITH caseNode, count(DISTINCT entity) AS entityCount
    OPTIONAL MATCH (caseNode)-[:USES_INVESTIGATION_EVIDENCE]->(evidence:InvestigationEvidence {platform: 'facebook'})
    WITH caseNode, entityCount, count(DISTINCT evidence) AS evidenceCount
    OPTIONAL MATCH (run:InvestigationImportRun {caseId: $caseId, connector: 'apify', platform: 'facebook'})
    WITH entityCount, evidenceCount, run ORDER BY run.createdAt DESC
    WITH entityCount, evidenceCount, collect(run)[0] AS latest
    RETURN entityCount AS entityCount,
           evidenceCount AS evidenceCount,
           latest.runId AS lastRunId,
           toString(latest.createdAt) AS lastImportedAt
    """
    try:
        with _db_session(get_driver()) as session:
            records = _execute_read(session, query, {"caseId": case_id})
    except Exception as exc:
        return {"error": str(exc), "entityCount": 0, "evidenceCount": 0}
    if not records:
        return {"entityCount": 0, "evidenceCount": 0}
    row = records[0].data()
    return {
        "entityCount": int(row.get("entityCount") or 0),
        "evidenceCount": int(row.get("evidenceCount") or 0),
        "lastRunId": row.get("lastRunId") or None,
        "lastImportedAt": row.get("lastImportedAt") or None,
    }


def _full_check_company_registry(
    case_id: str, requested_code: Optional[str]
) -> Tuple[Dict[str, object], Optional[Dict[str, object]]]:
    """Run the Georgian company registry source, or explain why it cannot run."""
    # Imported lazily: investigation_companyinfo imports from this module.
    from .investigation_companyinfo import (
        CompanyInfoEnrichmentRequest,
        _companyinfo_config,
        enrich_company_from_companyinfo,
    )

    try:
        config = _companyinfo_config()
    except Exception as exc:
        return (
            _full_check_source(
                "company-registry",
                FULL_CHECK_STATUS_ERROR,
                f"Company registry configuration could not be read: {exc}",
            ),
            None,
        )

    if not (config.get("enabled") and config.get("permissionAcknowledged")):
        return (
            _full_check_source(
                "company-registry",
                FULL_CHECK_STATUS_BLOCKED,
                (
                    "Blocked by the reuse-permission gate. An operator must review the "
                    "Companyinfo.ge terms and then set FS_COMPANYINFO_ENABLED=1 and "
                    "FS_COMPANYINFO_PERMISSION_ACKNOWLEDGED=1."
                ),
                requires_configuration=True,
            ),
            None,
        )

    code = str(requested_code or "").strip()
    if not code:
        candidates = _full_check_identification_codes(case_id)
        code = candidates[0] if candidates else ""
    if not code:
        return (
            _full_check_source(
                "company-registry",
                FULL_CHECK_STATUS_NO_DATA,
                (
                    "The Georgian company registry can only be searched by identification "
                    "code, and this case has none on file. Add the company identification "
                    "code to the case and run the check again."
                ),
            ),
            None,
        )

    try:
        request_model = CompanyInfoEnrichmentRequest(identificationCode=code)
    except Exception as exc:
        return (
            _full_check_source(
                "company-registry",
                FULL_CHECK_STATUS_NO_DATA,
                (
                    "The identification code on file is not a valid Georgian "
                    f"identification code (9 to 11 digits): {exc}"
                ),
            ),
            None,
        )

    try:
        graph = enrich_company_from_companyinfo(case_id, request_model)
    except HTTPException as exc:
        detail = (
            exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        )
        status = (
            FULL_CHECK_STATUS_BLOCKED
            if exc.status_code == 403
            else FULL_CHECK_STATUS_ERROR
        )
        message = str(detail.get("message") or detail.get("status") or exc.detail)
        return (
            _full_check_source(
                "company-registry",
                status,
                f"Company registry lookup did not complete: {message}",
                requires_configuration=status == FULL_CHECK_STATUS_BLOCKED,
            ),
            {"identificationCode": code, "error": detail},
        )
    except Exception as exc:
        return (
            _full_check_source(
                "company-registry",
                FULL_CHECK_STATUS_ERROR,
                f"Company registry lookup failed: {exc}",
            ),
            {"identificationCode": code, "error": str(exc)},
        )

    result = graph.get("enrichmentResult") if isinstance(graph, dict) else None
    result = result if isinstance(result, dict) else {}
    counts = result.get("counts") if isinstance(result.get("counts"), dict) else {}
    hit_count = sum(int(value or 0) for value in counts.values()) if counts else 0
    if not hit_count and result.get("companyEntityId"):
        hit_count = 1
    payload = {"identificationCode": code, "enrichmentResult": result}
    if hit_count:
        return (
            _full_check_source(
                "company-registry",
                FULL_CHECK_STATUS_OK,
                f"Company registry returned {hit_count} record(s) for identification code {code}.",
                hit_count=hit_count,
            ),
            payload,
        )
    return (
        _full_check_source(
            "company-registry",
            FULL_CHECK_STATUS_NO_DATA,
            f"No company registry records were returned for identification code {code}.",
        ),
        payload,
    )


def _full_check_facebook(case_id: str) -> Tuple[Dict[str, object], Dict[str, object]]:
    """Report already-imported Facebook material. Never starts a paid Apify run."""
    from .investigation_social import _imports_enabled, _managed_starts_enabled

    snapshot = _full_check_facebook_snapshot(case_id)
    entity_count = int(snapshot.get("entityCount") or 0)
    evidence_count = int(snapshot.get("evidenceCount") or 0)
    hit_count = entity_count + evidence_count
    token_configured = bool(str(os.getenv("APIFY_API_TOKEN") or "").strip())
    payload = {
        **snapshot,
        "tokenConfigured": token_configured,
        "importsEnabled": bool(_imports_enabled()),
        "managedStartsEnabled": bool(_managed_starts_enabled()),
        "startedPaidRun": False,
        "mode": "read-only",
    }

    if snapshot.get("error"):
        return (
            _full_check_source(
                "facebook",
                FULL_CHECK_STATUS_ERROR,
                f"Stored Facebook material could not be read: {snapshot.get('error')}",
            ),
            payload,
        )
    if hit_count:
        return (
            _full_check_source(
                "facebook",
                FULL_CHECK_STATUS_OK,
                (
                    f"{hit_count} Facebook record(s) already imported for this case "
                    "(no new scrape was started)."
                ),
                hit_count=hit_count,
            ),
            payload,
        )
    if not token_configured:
        return (
            _full_check_source(
                "facebook",
                FULL_CHECK_STATUS_NOT_CONFIGURED,
                (
                    "Nothing has been imported for this case and APIFY_API_TOKEN is not "
                    "set, so Facebook data cannot be fetched. Set APIFY_API_TOKEN, then "
                    "import an existing Apify run."
                ),
                requires_configuration=True,
            ),
            payload,
        )
    if not _imports_enabled():
        return (
            _full_check_source(
                "facebook",
                FULL_CHECK_STATUS_NOT_CONFIGURED,
                (
                    "Facebook imports are switched off. Set "
                    "FS_APIFY_FACEBOOK_IMPORT_ENABLED=1 to allow them."
                ),
                requires_configuration=True,
            ),
            payload,
        )
    return (
        _full_check_source(
            "facebook",
            FULL_CHECK_STATUS_NO_DATA,
            (
                "No Facebook records have been imported for this case yet. The full check "
                "never starts a paid Apify run; import an existing run first."
            ),
        ),
        payload,
    )


@router.post("/cases/{case_id}/full-check", response_model=DueDiligenceFullCheckOut)
def run_due_diligence_full_check(
    case_id: str, payload: Optional[DueDiligenceFullCheckRequest] = None
):
    """Run every due-diligence source for a case in one call.

    Sits under /due-diligence, so the platform's purpose enforcement
    (dd-investigation) and the investigator/compliance/admin role check apply.
    No single source is allowed to fail the request: each reports its own status.
    """
    request_payload = payload or DueDiligenceFullCheckRequest()
    case_row, _existing_report = _case_and_report_for_graph(case_id)
    subject = str(request_payload.subject or "").strip() or _case_display_subject(
        case_row.get("subject"),
        case_row.get("subjectGeorgian"),
        case_row.get("subjectEnglish"),
    )
    if not subject:
        raise HTTPException(status_code=400, detail="Case has no subject to screen")
    subject_type = _normalize_subject_type(
        request_payload.subject_type or case_row.get("subjectType")
    )

    warnings: List[str] = []
    sources: List[Dict[str, object]] = []
    analysis: Dict[str, object] = {}
    analysis_failed: Optional[str] = None

    try:
        analysis = analyze_due_diligence(
            DueDiligenceAnalysisRequest(
                subject=subject,
                subjectType=subject_type,
                caseId=case_id,
                useWikidata=True,
                useWikipedia=True,
                useOpenSanctions=True,
                useNews=True,
                useDeclarations=True,
                maxNews=request_payload.max_news,
                useLocalMedia=request_payload.use_local_media,
                mediaSourceIds=request_payload.media_source_ids,
                mediaTopics=request_payload.media_topics,
                mediaMaxResults=request_payload.media_max_results,
                # Never fabricate entities that carry a real subject's name.
                demo=False,
            )
        )
    except HTTPException:
        raise
    except Exception as exc:
        analysis_failed = str(exc)
        warnings.append(f"Core source analysis failed: {exc}")

    wikidata = list(analysis.get("wikidata") or [])
    wikipedia = list(analysis.get("wikipedia") or [])
    opensanctions = list(analysis.get("opensanctions") or [])
    news = list(analysis.get("news") or [])
    declarations = list(analysis.get("declarations") or [])
    media = analysis.get("media") if isinstance(analysis.get("media"), dict) else None
    media_mentions = len((media or {}).get("mentions") or [])
    analysis_warnings = [str(item) for item in (analysis.get("warnings") or [])]
    warnings.extend(analysis_warnings)
    grouped_warnings = _full_check_warnings_by_source(analysis_warnings)

    core_specs = (
        (
            "wikidata",
            len(wikidata),
            "Matched Wikidata entities.",
            "No Wikidata entity matched this subject.",
        ),
        (
            "wikipedia",
            len(wikipedia),
            "Matched Wikipedia articles.",
            "No Wikipedia article matched this subject.",
        ),
        (
            "opensanctions",
            len(opensanctions),
            "Sanctions/PEP screening returned matches; review them.",
            "Sanctions/PEP screening ran and returned no match.",
        ),
        (
            "news",
            len(news),
            "International news mentions found.",
            "No international news mention matched this subject.",
        ),
        (
            "declarations",
            len(declarations),
            "Public asset declaration records found.",
            "No public asset declaration record matched this subject.",
        ),
        (
            "georgian-media",
            media_mentions,
            "Georgian media mentions found across the configured sources.",
            "No Georgian media mention matched this subject.",
        ),
    )
    for source_id, hit_count, ok_detail, empty_detail in core_specs:
        if analysis_failed:
            sources.append(
                _full_check_source(
                    source_id,
                    FULL_CHECK_STATUS_ERROR,
                    f"This source did not run: {analysis_failed}",
                )
            )
            continue
        sources.append(
            _full_check_core_source(
                source_id,
                hit_count,
                grouped_warnings.get(source_id, []),
                ok_detail=ok_detail,
                empty_detail=empty_detail,
            )
        )

    registry_source, registry_payload = _full_check_company_registry(
        case_id, request_payload.identification_code
    )
    sources.append(registry_source)

    facebook_source, facebook_payload = _full_check_facebook(case_id)
    sources.append(facebook_source)

    base_summary = (
        analysis.get("summary") if isinstance(analysis.get("summary"), dict) else {}
    )
    summary: Dict[str, object] = dict(base_summary)
    hit_counts = {str(row["id"]): int(row["hitCount"]) for row in sources}
    status_counts: Dict[str, int] = {
        FULL_CHECK_STATUS_OK: 0,
        FULL_CHECK_STATUS_NO_DATA: 0,
        FULL_CHECK_STATUS_NOT_CONFIGURED: 0,
        FULL_CHECK_STATUS_BLOCKED: 0,
        FULL_CHECK_STATUS_ERROR: 0,
    }
    for row in sources:
        key = str(row["status"])
        status_counts[key] = status_counts.get(key, 0) + 1
    summary.update(
        {
            "riskLevel": base_summary.get("risk_level", "Unknown"),
            "riskScore": int(base_summary.get("risk_score") or 0),
            "coreTotalHits": int(base_summary.get("total_hits") or 0),
            "totalHits": sum(hit_counts.values()),
            "sourceHitCounts": hit_counts,
            "sourceStatusCounts": status_counts,
            "sourcesChecked": len(sources),
            "sourcesWithData": status_counts[FULL_CHECK_STATUS_OK],
            "sourcesRequiringConfiguration": sum(
                1 for row in sources if row["requiresConfiguration"]
            ),
            "demo": False,
        }
    )

    return {
        "caseId": case_id,
        "subject": subject,
        "subjectType": subject_type,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "demo": False,
        "sources": sources,
        "summary": summary,
        "results": {
            "wikidata": wikidata,
            "wikipedia": wikipedia,
            "opensanctions": opensanctions,
            "news": news,
            "declarations": declarations,
            "media": media,
            "companyRegistry": registry_payload,
            "facebook": facebook_payload,
        },
        "aiReport": analysis.get("aiReport"),
        "warnings": warnings,
        "reportId": analysis.get("reportId"),
        "storedAt": analysis.get("storedAt"),
    }
