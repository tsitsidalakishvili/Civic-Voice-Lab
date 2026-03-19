import csv
import io
import math
import os
import time
import uuid
import logging
import sys
from urllib.parse import urlparse
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .audience_discovery_chunker import build_chunks
from .audience_discovery_clustering import cluster_chunks
from .audience_discovery_crawler import CrawlPage, CrawlResult, crawl_site
from .audience_discovery_embeddings import EmbeddingsService
from .audience_discovery_entities import extract_entities
from .audience_discovery_evidence import verify_evidence
from .audience_discovery_domain_rules import augment_segments_for_domain
from .audience_discovery_metrics import compute_metrics
from .audience_discovery_messaging import generate_messaging
from .audience_discovery_neo4j import ensure_schema, knn_search, upsert_clusters, upsert_chunks, upsert_pages
from .audience_discovery_segments import (
    attach_segment_ids,
    generate_segment_drafts,
    validate_segments,
)
from .content_extractor import extract_page_content

router = APIRouter()

RUN_STORE: Dict[str, dict] = {}
EMBEDDINGS = EmbeddingsService(dim=256)
LOG = logging.getLogger("uvicorn.error")
LOG.setLevel(logging.INFO)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _env_bool(key: str, default: bool = True) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _looks_like_sitemap_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(".xml") or "sitemap" in path


def _truncate_text(value: str, limit: int = 160) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _safe_print(line: str):
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((line + "\n").encode("utf-8", errors="replace"))
        sys.stdout.flush()


def _log_run_summary(run: dict):
    if not _env_bool("ADE_LOG_RUN_SUMMARY", True):
        return

    pages = run.get("pages", [])
    segments = run.get("segments", [])
    clusters = run.get("clusters", [])
    errors = run.get("errors", [])
    notes = run.get("notes", [])

    status_counts = {"success": 0, "failed": 0, "skipped": 0, "other": 0}
    for page in pages:
        status = (page.get("crawlStatus") or "").lower()
        if status in status_counts:
            status_counts[status] += 1
        else:
            status_counts["other"] += 1

    summary_lines = [
        f"ADE run {run.get('runId')} completed",
        f"ADE url={run.get('url')}",
        (
            "ADE pages="
            f"{len(pages)} (success={status_counts['success']}, "
            f"failed={status_counts['failed']}, skipped={status_counts['skipped']}, "
            f"other={status_counts['other']})"
        ),
        (
            "ADE chunks="
            f"{run.get('summary', {}).get('chunksCreated')} "
            f"clusters={len(clusters)} segments={len(segments)} "
            f"runtime={run.get('runtimeSeconds')}s"
        ),
    ]
    for line in summary_lines:
        LOG.info(line)
        _safe_print(line)

    if errors:
        for item in errors[:5]:
            LOG.warning("ADE error: %s", item)
            _safe_print(f"ADE error: {item}")
        if len(errors) > 5:
            LOG.warning("ADE error: ... %s more", len(errors) - 5)
            _safe_print(f"ADE error: ... {len(errors) - 5} more")

    if notes:
        for note in notes:
            LOG.info("ADE note: %s", note)
            _safe_print(f"ADE note: {note}")

    if segments:
        sorted_segments = sorted(
            segments, key=lambda seg: seg.get("confidence", 0), reverse=True
        )[:5]
        for segment in sorted_segments:
            evidence = segment.get("evidence") or []
            first_quote = ""
            first_url = ""
            if evidence:
                first_quote = _truncate_text(evidence[0].get("quote", ""))
                first_url = evidence[0].get("url", "")
            line = (
                "ADE segment: "
                f"{segment.get('name')} (confidence={float(segment.get('confidence', 0)):.2f}, "
                f"evidence={len(evidence)}) {first_quote} {first_url}"
            )
            LOG.info(line)
            _safe_print(line)


class AnalysisStartRequest(BaseModel):
    url: Optional[str] = ""
    urls: List[str] = []
    sitemap_url: Optional[str] = Field(default="", alias="sitemapUrl")
    seed_urls: List[str] = Field(default_factory=list, alias="seedUrls")
    crawl_depth: int = Field(default=1, alias="crawlDepth", ge=0, le=2)
    crawl_timeout_s: int = Field(default=12, alias="crawlTimeoutS", ge=3, le=60)
    max_pages: int = Field(default=200, alias="maxPages", ge=1, le=1000)
    allowed_domains: List[str] = Field(default_factory=list, alias="allowedDomains")
    product_rules: List[str] = Field(default_factory=list, alias="productRules")
    cluster_count: Optional[int] = Field(default=None, alias="clusterCount")
    description: Optional[str] = ""
    brand: Optional[str] = ""
    locale: Optional[str] = ""


class EvidenceSnippet(BaseModel):
    quote: str
    url: str
    chunk_id: Optional[str] = Field(default=None, alias="chunkId")
    start_offset: Optional[int] = Field(default=None, alias="startOffset")
    end_offset: Optional[int] = Field(default=None, alias="endOffset")
    is_sample: bool = Field(default=False, alias="isSample")


class SegmentOut(BaseModel):
    segment_id: str = Field(alias="segmentId")
    name: str
    rationale: str
    confidence: float
    evidence: List[EvidenceSnippet]
    confirmed: bool = False
    verified: bool = False
    page_id: str = Field(default="", alias="pageId")
    page_url: str = Field(default="", alias="pageUrl")


class MessagingOut(BaseModel):
    segment_id: str = Field(alias="segmentId")
    name: str
    headlines: List[str]
    tone: str
    ctas: List[str]


class PageSummary(BaseModel):
    page_id: str = Field(alias="pageId")
    url: str
    title: str
    word_count: int = Field(alias="wordCount")
    crawl_status: str = Field(alias="crawlStatus")
    chunk_count: int = Field(default=0, alias="chunkCount")
    meta_description: Optional[str] = Field(default="", alias="metaDescription")
    canonical_url: Optional[str] = Field(default="", alias="canonicalUrl")
    headings: List[str] = []
    breadcrumbs: List[str] = []


class ClusterOut(BaseModel):
    cluster_id: str = Field(alias="clusterId")
    cluster_size: int = Field(alias="clusterSize")
    chunk_ids: List[str] = Field(alias="chunkIds")
    sample_snippets: List[str] = Field(alias="sampleSnippets")
    label: Optional[str] = ""


class StageStatus(BaseModel):
    id: str
    label: str
    status: str
    count: Optional[int] = None
    detail: Optional[str] = None
    duration_sec: Optional[float] = Field(default=None, alias="durationSec")


class AudienceDiscoverySummary(BaseModel):
    coverage: float
    explainability: float
    evidence_pass_rate: float = Field(alias="evidencePassRate")
    runtime_seconds: float = Field(alias="runtimeSeconds")
    p95_runtime_seconds: float = Field(alias="p95RuntimeSeconds")
    pages_crawled: int = Field(alias="pagesCrawled")
    segments_generated: int = Field(alias="segmentsGenerated")
    verified_segments: int = Field(alias="verifiedSegments")
    chunks_created: int = Field(alias="chunksCreated")
    clusters_created: int = Field(alias="clustersCreated")


class AnalysisStatusOut(BaseModel):
    run_id: str = Field(alias="runId")
    status: str
    created_at: str = Field(alias="createdAt")
    stages: List[StageStatus]


class AnalysisStartOut(AnalysisStatusOut):
    description: Optional[str] = ""
    brand: Optional[str] = ""
    locale: Optional[str] = ""


class AnalysisPagesOut(BaseModel):
    run_id: str = Field(alias="runId")
    pages: List[PageSummary]


class AnalysisSegmentsOut(BaseModel):
    run_id: str = Field(alias="runId")
    segments: List[SegmentOut]


class AnalysisClustersOut(BaseModel):
    run_id: str = Field(alias="runId")
    clusters: List[ClusterOut]


class AnalysisMessagingOut(BaseModel):
    run_id: str = Field(alias="runId")
    messaging: List[MessagingOut]


class AnalysisMetricsOut(BaseModel):
    run_id: str = Field(alias="runId")
    summary: AudienceDiscoverySummary


class ChunkOut(BaseModel):
    chunk_id: str = Field(alias="chunkId")
    page_id: str = Field(alias="pageId")
    url: str
    text: str
    start_offset: int = Field(alias="startOffset")
    end_offset: int = Field(alias="endOffset")


class AnalysisChunksOut(BaseModel):
    run_id: str = Field(alias="runId")
    page_id: str = Field(alias="pageId")
    chunks: List[ChunkOut]


class AnalysisClusterChunksOut(BaseModel):
    run_id: str = Field(alias="runId")
    cluster_id: str = Field(alias="clusterId")
    chunks: List[ChunkOut]


def _init_stages() -> List[dict]:
    now = time.time()
    return [
        {"id": "crawl", "label": "Crawling", "status": "running", "startedAt": now},
        {"id": "chunk", "label": "Chunking", "status": "pending", "startedAt": None},
        {"id": "embed", "label": "Embeddings", "status": "pending", "startedAt": None},
        {"id": "cluster", "label": "Clustering", "status": "pending", "startedAt": None},
        {"id": "segments", "label": "Segment extraction", "status": "pending", "startedAt": None},
        {"id": "evidence", "label": "Evidence verification", "status": "pending", "startedAt": None},
        {"id": "messaging", "label": "Messaging", "status": "pending", "startedAt": None},
        {"id": "store", "label": "Neo4j storage", "status": "pending", "startedAt": None},
    ]


def _complete_stage(stages: List[dict], stage_id: str, count: Optional[int] = None):
    for stage in stages:
        if stage["id"] == stage_id:
            stage["status"] = "success"
            if count is not None:
                stage["count"] = count
            if stage.get("startedAt"):
                stage["durationSec"] = round(time.time() - stage["startedAt"], 2)
            break


def _start_stage(stages: List[dict], stage_id: str):
    for stage in stages:
        if stage["id"] == stage_id:
            stage["status"] = "running"
            stage["startedAt"] = time.time()
            break


def _finalize_run(
    payload: AnalysisStartRequest,
    crawl_result: CrawlResult,
    run_url: str,
    stages: List[dict],
    start_time: float,
    cluster_count: Optional[int],
    extra_notes: Optional[List[str]] = None,
) -> dict:
    _complete_stage(stages, "crawl", count=len(crawl_result.pages))

    _start_stage(stages, "chunk")
    pages: List[dict] = []
    page_summaries: List[dict] = []
    chunks: List[dict] = []
    combined_text = ""
    run_id = str(uuid.uuid4())
    errors: List[str] = []

    for page in crawl_result.pages:
        page_id = str(uuid.uuid4())
        if page.status != "success":
            page_summaries.append(
                PageSummary(
                    pageId=page_id,
                    url=page.url,
                    title="Skipped",
                    wordCount=0,
                    crawlStatus=page.status,
                    chunkCount=0,
                ).model_dump(by_alias=True)
            )
            pages.append(
                {
                    "page_id": page_id,
                    "url": page.url,
                    "title": "Skipped",
                    "raw_html": "",
                    "cleaned_text": "",
                    "crawl_status": page.status,
                }
            )
            continue
        content = extract_page_content(
            page.html, page.url, page.content_type, page.raw_bytes
        )
        normalized_text, page_chunks = build_chunks(
            content["cleaned_text"], content["headings"]
        )
        for idx, chunk in enumerate(page_chunks):
            chunks.append(
                {
                    "chunkId": f"{page_id}-{idx + 1}",
                    "pageId": page_id,
                    "url": page.url,
                    "text": chunk["text"],
                    "startOffset": chunk["start_offset"],
                    "endOffset": chunk["end_offset"],
                    "sectionHeading": chunk.get("section_heading") or "",
                    "entities": extract_entities(chunk["text"]),
                }
            )
        page_summary = PageSummary(
            pageId=page_id,
            url=page.url,
            title=content["title"],
            wordCount=len(normalized_text.split()),
            crawlStatus=page.status,
            chunkCount=len(page_chunks),
            metaDescription=content["meta_description"],
            canonicalUrl=content["canonical_url"],
            headings=content["headings"],
            breadcrumbs=content["breadcrumbs"],
        ).model_dump(by_alias=True)
        page_summaries.append(page_summary)
        pages.append(
            {
                "page_id": page_id,
                "url": page.url,
                "title": content["title"],
                "raw_html": page.html,
                "cleaned_text": normalized_text,
                "crawl_status": page.status,
            }
        )
        combined_text = f"{combined_text}\n{normalized_text}".strip()

    _complete_stage(stages, "chunk", count=len(chunks))

    _start_stage(stages, "embed")
    try:
        embeddings = EMBEDDINGS.embed([chunk["text"] for chunk in chunks])
        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding.vector
            chunk["embeddingModel"] = embedding.model
            chunk["embeddingTimestamp"] = embedding.timestamp
            chunk["textHash"] = embedding.text_hash
        _complete_stage(stages, "embed", count=len(chunks))
    except Exception as exc:
        errors.append(f"embedding failure: {exc}")
        for stage in stages:
            if stage["id"] == "embed":
                stage["status"] = "error"
                stage["detail"] = str(exc)
        embeddings = []

    _start_stage(stages, "cluster")
    try:
        clusters = cluster_chunks(chunks, cluster_count=cluster_count)
        _complete_stage(stages, "cluster", count=len(clusters))
    except Exception as exc:
        clusters = []
        errors.append(f"clustering failure: {exc}")
        for stage in stages:
            if stage["id"] == "cluster":
                stage["status"] = "error"
                stage["detail"] = str(exc)

    _start_stage(stages, "store")
    storage_error = ""
    try:
        ensure_schema(dimensions=256)
        upsert_pages(run_id, pages)
        upsert_chunks(
            [
                {
                    "chunk_id": chunk["chunkId"],
                    "page_id": chunk["pageId"],
                    "url": chunk["url"],
                    "text": chunk["text"],
                    "start_offset": chunk["startOffset"],
                    "end_offset": chunk["endOffset"],
                    "embedding": chunk["embedding"],
                }
                for chunk in chunks
            ]
        )
        upsert_clusters(run_id, clusters)
        _complete_stage(stages, "store")
    except Exception as exc:
        storage_error = str(exc)
        errors.append(f"neo4j write failure: {storage_error}")
        for stage in stages:
            if stage["id"] == "store":
                stage["status"] = "warning"
                stage["detail"] = storage_error

    _start_stage(stages, "segments")
    segments = []
    for page in pages:
        if page["crawl_status"] != "success":
            continue
        retrieval_text = page["cleaned_text"]
        if not storage_error:
            try:
                page_embedding = EMBEDDINGS.embed([page["cleaned_text"]])[0]
                knn_rows = knn_search(page_embedding.vector, k=8)
                if knn_rows:
                    retrieval_text = " ".join(row.get("text", "") for row in knn_rows)
            except Exception as exc:
                errors.append(f"neo4j retrieval failure: {exc}")
        raw_segments = generate_segment_drafts(
            retrieval_text, payload.description or "", payload.locale or ""
        )
        if raw_segments.get("error"):
            errors.append(f"llm json failure: {raw_segments['error']}")
        validated = validate_segments(raw_segments["parsed"])
        page_segments = attach_segment_ids(
            validated, page_id=page["page_id"], page_url=page["url"]
        )
        page_segments = augment_segments_for_domain(
            page["url"], page["cleaned_text"], page_segments, page["page_id"], page["url"]
        )
        segments.extend(page_segments)
    _complete_stage(stages, "segments", count=len(segments))

    _start_stage(stages, "evidence")
    segments = verify_evidence(segments, chunks)
    _complete_stage(
        stages, "evidence", count=len([segment for segment in segments if segment["verified"]])
    )

    evidence_rejections = sum(
        len(segment.get("rejectedEvidence", [])) for segment in segments
    )

    for segment in segments:
        segment["confirmed"] = False

    _start_stage(stages, "messaging")
    confirmed_count = len([segment for segment in segments if segment.get("confirmed")])
    _complete_stage(stages, "messaging", count=confirmed_count)
    for stage in stages:
        if stage["id"] == "messaging":
            stage["detail"] = "Generated on demand for confirmed segments."
            break

    runtime = round(time.time() - start_time, 2)
    notes = []
    if not pages:
        notes.append("No product pages detected; analyzed the primary URL only.")
    if not chunks:
        notes.append("No chunks created; check crawl settings and page content.")
    if crawl_result.logs:
        notes.append("See crawl logs for skipped or failed pages.")
    if evidence_rejections:
        notes.append(f"Rejected {evidence_rejections} evidence quotes not found in text.")
    if extra_notes:
        notes.extend(extra_notes)

    run = {
        "runId": run_id,
        "status": "completed",
        "createdAt": _now_iso(),
        "url": run_url,
        "description": payload.description or "",
        "brand": payload.brand or "",
        "locale": payload.locale or "",
        "pages": page_summaries,
        "pagesRaw": pages,
        "chunks": chunks,
        "clusters": clusters,
        "segments": segments,
        "stages": stages,
        "runtimeSeconds": runtime,
        "logs": crawl_result.logs,
        "errors": errors,
        "storageError": storage_error,
        "notes": notes,
    }
    run["p95RuntimeSeconds"] = _p95_runtime(runtime)
    run["summary"] = compute_metrics(run)
    RUN_STORE[run_id] = run
    return run


def _run_analysis(payload: AnalysisStartRequest) -> dict:
    start = time.time()
    stages = _init_stages()

    sitemap_url = (payload.sitemap_url or "").strip()
    seed_urls = payload.seed_urls or payload.urls or []
    seed_urls = [item.strip() for item in seed_urls if item.strip()]
    primary_url = (payload.url or "").strip()
    if primary_url:
        if _looks_like_sitemap_url(primary_url) and not sitemap_url:
            sitemap_url = primary_url
        else:
            seed_urls.append(primary_url)
    if not sitemap_url and not seed_urls:
        raise HTTPException(status_code=400, detail="Provide a sitemap URL or product URLs.")

    env_timeout = _env_int("ADE_CRAWL_TIMEOUT_S", payload.crawl_timeout_s)
    env_max_pages = _env_int("ADE_MAX_PAGES", payload.max_pages)
    env_cluster_count = _env_int("ADE_CLUSTER_COUNT", 0)
    crawl_timeout = env_timeout if payload.crawl_timeout_s == 12 else payload.crawl_timeout_s
    max_pages = env_max_pages if payload.max_pages == 200 else payload.max_pages
    cluster_count = (
        payload.cluster_count
        if payload.cluster_count is not None
        else (env_cluster_count if env_cluster_count > 0 else None)
    )

    crawl_result = crawl_site(
        sitemap_url=sitemap_url or None,
        seed_urls=seed_urls,
        depth=payload.crawl_depth,
        allowed_domains=payload.allowed_domains,
        product_rules=payload.product_rules,
        timeout=crawl_timeout,
        max_pages=max_pages,
    )
    run_url = sitemap_url or (seed_urls[0] if seed_urls else "")
    return _finalize_run(payload, crawl_result, run_url, stages, start, cluster_count)


def _get_run(run_id: str) -> dict:
    run = RUN_STORE.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


def _get_chunks_for_page(run: dict, page_id: str) -> List[dict]:
    return [
        chunk
        for chunk in run.get("chunks", [])
        if chunk.get("pageId") == page_id
    ]


def _get_chunks_for_cluster(run: dict, cluster_id: str) -> List[dict]:
    cluster = next(
        (cluster for cluster in run.get("clusters", []) if cluster.get("clusterId") == cluster_id),
        None,
    )
    if not cluster:
        return []
    cluster_chunk_ids = set(cluster.get("chunkIds", []))
    return [
        chunk for chunk in run.get("chunks", []) if chunk.get("chunkId") in cluster_chunk_ids
    ]


def _p95_runtime(current_runtime: float) -> float:
    durations = [
        run.get("runtimeSeconds")
        for run in RUN_STORE.values()
        if run.get("runtimeSeconds") is not None
    ]
    durations.append(current_runtime)
    if not durations:
        return 0.0
    durations = sorted(durations)
    index = max(0, math.ceil(0.95 * len(durations)) - 1)
    return round(durations[index], 2)


@router.post("/analysis/start", response_model=AnalysisStartOut)
def start_analysis(payload: AnalysisStartRequest):
    run = _run_analysis(payload)
    try:
        _log_run_summary(run)
    except Exception as exc:
        LOG.warning("ADE run logging failed: %s", exc)
    return AnalysisStartOut(
        runId=run["runId"],
        status=run["status"],
        createdAt=run["createdAt"],
        stages=[StageStatus(**stage) for stage in run["stages"]],
        description=run.get("description"),
        brand=run.get("brand"),
        locale=run.get("locale"),
    )


@router.post("/analysis/upload", response_model=AnalysisStartOut)
async def start_analysis_upload(
    file: UploadFile = File(...),
    description: str = Form(""),
    brand: str = Form(""),
    locale: str = Form(""),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Upload a PDF file.")
    content_type = (file.content_type or "").lower()
    if "pdf" not in content_type and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    payload = AnalysisStartRequest(
        url="",
        urls=[],
        description=description,
        brand=brand,
        locale=locale,
    )
    crawl_result = CrawlResult(
        pages=[
            CrawlPage(
                url=file.filename or "uploaded.pdf",
                status="success",
                html="",
                content_type=content_type or "application/pdf",
                raw_bytes=raw_bytes,
            )
        ],
        logs=[f"Uploaded file: {file.filename or 'uploaded.pdf'}"],
    )
    env_cluster_count = _env_int("ADE_CLUSTER_COUNT", 0)
    cluster_count = env_cluster_count if env_cluster_count > 0 else None
    stages = _init_stages()
    run = _finalize_run(
        payload,
        crawl_result,
        run_url="",
        stages=stages,
        start_time=time.time(),
        cluster_count=cluster_count,
        extra_notes=[f"Uploaded file: {file.filename or 'uploaded.pdf'}"],
    )
    try:
        _log_run_summary(run)
    except Exception as exc:
        LOG.warning("ADE run logging failed: %s", exc)
    return AnalysisStartOut(
        runId=run["runId"],
        status=run["status"],
        createdAt=run["createdAt"],
        stages=[StageStatus(**stage) for stage in run["stages"]],
        description=run.get("description"),
        brand=run.get("brand"),
        locale=run.get("locale"),
    )


@router.get("/analysis/{run_id}/status", response_model=AnalysisStatusOut)
def get_status(run_id: str):
    run = _get_run(run_id)
    return AnalysisStatusOut(
        runId=run["runId"],
        status=run["status"],
        createdAt=run["createdAt"],
        stages=[StageStatus(**stage) for stage in run["stages"]],
    )


@router.get("/analysis/{run_id}/pages", response_model=AnalysisPagesOut)
def get_pages(run_id: str):
    run = _get_run(run_id)
    return AnalysisPagesOut(runId=run["runId"], pages=run["pages"])


@router.get("/analysis/{run_id}/segments", response_model=AnalysisSegmentsOut)
def get_segments(run_id: str):
    run = _get_run(run_id)
    return AnalysisSegmentsOut(runId=run["runId"], segments=run["segments"])


@router.get("/analysis/{run_id}/clusters", response_model=AnalysisClustersOut)
def get_clusters(run_id: str):
    run = _get_run(run_id)
    return AnalysisClustersOut(runId=run["runId"], clusters=run["clusters"])


@router.get("/analysis/{run_id}/pages/{page_id}/chunks", response_model=AnalysisChunksOut)
def get_page_chunks(run_id: str, page_id: str):
    run = _get_run(run_id)
    chunks = _get_chunks_for_page(run, page_id)
    return AnalysisChunksOut(runId=run["runId"], pageId=page_id, chunks=chunks)


@router.get(
    "/analysis/{run_id}/clusters/{cluster_id}/chunks", response_model=AnalysisClusterChunksOut
)
def get_cluster_chunks(run_id: str, cluster_id: str):
    run = _get_run(run_id)
    chunks = _get_chunks_for_cluster(run, cluster_id)
    return AnalysisClusterChunksOut(runId=run["runId"], clusterId=cluster_id, chunks=chunks)


class SegmentConfirmRequest(BaseModel):
    segment_ids: List[str] = Field(alias="segmentIds")
    action: str = Field(default="confirm")


@router.post("/analysis/{run_id}/segments/confirm", response_model=AnalysisSegmentsOut)
def confirm_segments(run_id: str, payload: SegmentConfirmRequest):
    run = _get_run(run_id)
    action = payload.action.lower().strip()
    if action not in {"confirm", "discard"}:
        raise HTTPException(status_code=400, detail="Action must be confirm or discard.")
    for segment in run["segments"]:
        if segment["segmentId"] in payload.segment_ids:
            segment["confirmed"] = action == "confirm"
    return AnalysisSegmentsOut(runId=run["runId"], segments=run["segments"])


@router.get("/analysis/{run_id}/messaging", response_model=AnalysisMessagingOut)
def get_messaging(run_id: str):
    run = _get_run(run_id)
    brand = run.get("brand") or ""
    locale = run.get("locale") or ""
    messaging = generate_messaging(run["segments"], brand, locale)
    return AnalysisMessagingOut(runId=run["runId"], messaging=messaging)


@router.get("/analysis/{run_id}/metrics", response_model=AnalysisMetricsOut)
def get_metrics(run_id: str):
    run = _get_run(run_id)
    return AnalysisMetricsOut(runId=run["runId"], summary=run["summary"])


@router.get("/analysis/{run_id}/export/json")
def export_json(run_id: str):
    run = _get_run(run_id)
    run_export = dict(run)
    run_export["messaging"] = generate_messaging(
        run_export.get("segments", []),
        run_export.get("brand") or "",
        run_export.get("locale") or "",
    )
    return run_export


@router.get("/analysis/{run_id}/export/csv")
def export_csv(run_id: str):
    run = _get_run(run_id)
    messaging_map = {
        item["segmentId"]: item
        for item in generate_messaging(
            run.get("segments", []), run.get("brand") or "", run.get("locale") or ""
        )
    }
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "segment_id",
            "segment_name",
            "rationale",
            "confirmed",
            "evidence_quote",
            "evidence_url",
            "headline_1",
            "headline_2",
            "headline_3",
            "tone",
            "cta_1",
            "cta_2",
            "cta_3",
        ]
    )
    for segment in run["segments"]:
        evidence = segment.get("evidence") or []
        messaging = messaging_map.get(segment.get("segmentId"), {})
        headlines = messaging.get("headlines") or []
        ctas = messaging.get("ctas") or []
        if not evidence:
            writer.writerow(
                [
                    segment.get("segmentId"),
                    segment.get("name"),
                    segment.get("rationale"),
                    segment.get("confirmed"),
                    "",
                    "",
                    headlines[0] if len(headlines) > 0 else "",
                    headlines[1] if len(headlines) > 1 else "",
                    headlines[2] if len(headlines) > 2 else "",
                    messaging.get("tone", ""),
                    ctas[0] if len(ctas) > 0 else "",
                    ctas[1] if len(ctas) > 1 else "",
                    ctas[2] if len(ctas) > 2 else "",
                ]
            )
        else:
            for item in evidence:
                writer.writerow(
                    [
                        segment.get("segmentId"),
                        segment.get("name"),
                        segment.get("rationale"),
                        segment.get("confirmed"),
                        item.get("quote"),
                        item.get("url"),
                        headlines[0] if len(headlines) > 0 else "",
                        headlines[1] if len(headlines) > 1 else "",
                        headlines[2] if len(headlines) > 2 else "",
                        messaging.get("tone", ""),
                        ctas[0] if len(ctas) > 0 else "",
                        ctas[1] if len(ctas) > 1 else "",
                        ctas[2] if len(ctas) > 2 else "",
                    ]
                )
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audience-discovery.csv"},
    )
