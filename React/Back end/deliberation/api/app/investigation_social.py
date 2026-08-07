import hashlib
import json
import os
import re
import secrets
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import requests
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .db import get_driver
from .routes_due_diligence import (
    _build_investigation_graph_bundle,
    _case_and_report_for_graph,
    _clean_decl_text,
    _db_session,
    _execute_read,
    _execute_write,
    _graph_entity,
    _graph_evidence,
    _graph_link,
    _graph_source,
    _investigation_id,
    _load_investigation_graph,
    _persist_investigation_graph_bundle,
)


router = APIRouter()

DEFAULT_APIFY_FACEBOOK_ACTOR_ID = "apify~facebook-groups-scraper"
DEFAULT_APIFY_FACEBOOK_ACTOR_NAME = "apify/facebook-groups-scraper"
APIFY_API_BASE = "https://api.apify.com/v2"
APIFY_ACTOR_PUBLIC_URL = "https://apify.com/apify/facebook-groups-scraper"
APIFY_CONNECTOR_ID = "apify-facebook-public-groups"
APIFY_OUTPUT_MAPPING_VERSION = "apify-facebook-public-groups-v2"
APIFY_PRICING_REFERENCE_URL = "https://apify.com/apify/facebook-groups-scraper/pricing"
APIFY_PRICING_VERIFIED_AT = "2026-08-07"
APIFY_TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}
APIFY_ACTIVE_STATUSES = {"READY", "RUNNING"}
APIFY_RETRYABLE_HTTP_STATUSES = (429, 500, 502, 503, 504)


APIFY_FACEBOOK_ACTORS: Dict[str, Dict[str, object]] = {
    DEFAULT_APIFY_FACEBOOK_ACTOR_ID: {
        "actorId": DEFAULT_APIFY_FACEBOOK_ACTOR_ID,
        "name": DEFAULT_APIFY_FACEBOOK_ACTOR_NAME,
        "url": APIFY_ACTOR_PUBLIC_URL,
        "schemaVersion": APIFY_OUTPUT_MAPPING_VERSION,
        "maintainer": "Apify",
        "startAllowed": True,
        "freeTierPolicy": "operator-capped-pay-per-result",
        "pricing": {
            "mode": "dynamic-external",
            "referenceUrl": APIFY_PRICING_REFERENCE_URL,
            "lastVerifiedAt": APIFY_PRICING_VERIFIED_AT,
            "note": "Verify the live Actor price before every run; FS does not assume a fixed price.",
        },
        "aliases": [DEFAULT_APIFY_FACEBOOK_ACTOR_NAME],
    },
    "2chN8UQcH1CfxLRNE": {
        "actorId": "2chN8UQcH1CfxLRNE",
        "name": "scrapium/facebook-groups-scraper",
        "url": "https://apify.com/scrapium/facebook-groups-scraper",
        "schemaVersion": "scrapium-facebook-groups-output-v1",
        "maintainer": "Scrapium",
        "startAllowed": False,
        "freeTierPolicy": "import-existing-output-only",
        "pricing": {
            "mode": "dynamic-external",
            "referenceUrl": "https://apify.com/scrapium/facebook-groups-scraper/pricing",
            "lastVerifiedAt": APIFY_PRICING_VERIFIED_AT,
            "note": "Rental pricing can exceed the free allowance; FS will never start this Actor.",
        },
        "aliases": ["scrapium/facebook-groups-scraper"],
    },
}


def _actor_alias_index() -> Dict[str, str]:
    output: Dict[str, str] = {}
    for actor_id, actor in APIFY_FACEBOOK_ACTORS.items():
        for value in [actor_id, actor.get("name"), *(actor.get("aliases") or [])]:
            clean = str(value or "").strip().casefold()
            if clean:
                output[clean] = actor_id
    return output


APIFY_ACTOR_ALIASES = _actor_alias_index()


class ApifyFacebookImportRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    actor_id: str = Field(
        default=DEFAULT_APIFY_FACEBOOK_ACTOR_ID,
        min_length=1,
        max_length=160,
        alias="actorId",
    )
    run_id: Optional[str] = Field(default=None, max_length=200, alias="runId")
    dataset_id: Optional[str] = Field(default=None, max_length=200, alias="datasetId")
    items: Optional[List[Dict[str, Any]]] = Field(default=None, max_length=1000)
    max_items: int = Field(default=200, ge=1, le=1000, alias="maxItems")
    include_top_comments: bool = Field(default=True, alias="includeTopComments")
    promote_posts_to_graph: bool = Field(default=True, alias="promotePostsToGraph")
    lawful_basis: str = Field(min_length=10, max_length=500, alias="lawfulBasis")
    investigation_purpose: str = Field(
        min_length=10, max_length=500, alias="investigationPurpose"
    )
    retention_days: int = Field(default=180, ge=7, le=730, alias="retentionDays")

    @model_validator(mode="after")
    def validate_input_source(self):
        choices = [self.run_id is not None, self.dataset_id is not None, self.items is not None]
        if sum(choices) != 1:
            raise ValueError("Provide exactly one of runId, datasetId, or items")
        if self.items is not None and len(self.items) > self.max_items:
            raise ValueError("items cannot contain more records than maxItems")
        return self


class ApifyFacebookStartRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    actor_id: str = Field(
        default=DEFAULT_APIFY_FACEBOOK_ACTOR_ID,
        min_length=1,
        max_length=160,
        alias="actorId",
    )
    group_urls: List[str] = Field(min_length=1, max_length=5, alias="groupUrls")
    max_items: int = Field(default=100, ge=1, le=500, alias="maxItems")
    max_total_charge_usd: float = Field(
        default=1.0, gt=0, lt=5, alias="maxTotalChargeUsd"
    )
    only_posts_newer_than: Optional[str] = Field(
        default=None, min_length=4, max_length=50, alias="onlyPostsNewerThan"
    )
    include_top_comments: bool = Field(default=True, alias="includeTopComments")
    promote_posts_to_graph: bool = Field(default=True, alias="promotePostsToGraph")
    lawful_basis: str = Field(min_length=10, max_length=500, alias="lawfulBasis")
    investigation_purpose: str = Field(
        min_length=10, max_length=500, alias="investigationPurpose"
    )
    retention_days: int = Field(default=180, ge=7, le=730, alias="retentionDays")

    @model_validator(mode="after")
    def validate_public_groups(self):
        normalized: List[str] = []
        for value in self.group_urls:
            clean = _public_facebook_group_url(value)
            if not clean:
                raise ValueError(
                    "groupUrls must contain only explicit public facebook.com/groups/... URLs"
                )
            if clean not in normalized:
                normalized.append(clean)
        if not normalized:
            raise ValueError("At least one distinct public Facebook group URL is required")
        self.group_urls = normalized
        return self


class ApifyWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_type: str = Field(default="", alias="eventType", max_length=100)
    event_data: Dict[str, Any] = Field(default_factory=dict, alias="eventData")
    resource: Dict[str, Any] = Field(default_factory=dict)


class ApifyRetentionCleanupRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dry_run: bool = Field(default=True, alias="dryRun")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "")).strip().casefold()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_csv(name: str) -> List[str]:
    return [
        value.strip()
        for value in str(os.getenv(name, "")).split(",")
        if value.strip()
    ]


def _env_money(name: str, default: float, maximum: float) -> float:
    try:
        value = float(str(os.getenv(name, "")).strip() or default)
    except ValueError:
        value = default
    return round(max(0.01, min(value, maximum)), 2)


def _imports_enabled() -> bool:
    return _env_flag("FS_APIFY_FACEBOOK_IMPORT_ENABLED", True)


def _managed_starts_enabled() -> bool:
    return _env_flag("FS_APIFY_FACEBOOK_START_ENABLED", False)


def _monthly_budget_usd() -> float:
    return _env_money("FS_APIFY_FACEBOOK_MONTHLY_BUDGET_USD", 4.5, 4.99)


def _maximum_run_charge_usd() -> float:
    return _env_money("FS_APIFY_FACEBOOK_MAX_RUN_CHARGE_USD", 1.0, 4.99)


def _public_facebook_group_url(value: object) -> str:
    clean = _clean_url(value)
    if not clean:
        return ""
    parsed = urlsplit(clean)
    host = (parsed.hostname or "").casefold()
    if host not in {"facebook.com", "www.facebook.com", "m.facebook.com"}:
        return ""
    segments = [part for part in parsed.path.split("/") if part]
    if len(segments) < 2 or segments[0].casefold() != "groups":
        return ""
    if segments[1].casefold() in {"feed", "discover", "create", "joins"}:
        return ""
    return f"https://www.facebook.com/groups/{segments[1]}"


def _resolve_actor(actor_id: object, *, for_start: bool = False) -> Dict[str, object]:
    requested = str(actor_id or "").strip()
    canonical_id = APIFY_ACTOR_ALIASES.get(requested.casefold())
    if not canonical_id:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "APIFY_ACTOR_NOT_ALLOWLISTED",
                "message": "The selected Apify Actor is not allowlisted for this connector.",
                "actorId": requested,
                "allowedActorIds": sorted(APIFY_FACEBOOK_ACTORS),
                "retryable": False,
            },
        )
    actor = dict(APIFY_FACEBOOK_ACTORS[canonical_id])
    if for_start and not bool(actor.get("startAllowed")):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "APIFY_ACTOR_IMPORT_ONLY",
                "message": "This Actor is allowlisted only for importing existing output.",
                "actorId": canonical_id,
                "retryable": False,
            },
        )
    return actor


def _retrying_get_session() -> requests.Session:
    retry = Retry(
        total=4,
        connect=3,
        read=3,
        status=4,
        backoff_factor=0.6,
        status_forcelist=APIFY_RETRYABLE_HTTP_STATUSES,
        allowed_methods=frozenset({"GET", "HEAD"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    return session


def _apify_error_detail(code: str, message: str, *, retryable: bool) -> Dict[str, object]:
    return {"code": code, "message": message, "retryable": retryable}


def _apify_get_json(
    path: str, *, params: Optional[Dict[str, object]] = None, timeout: int = 30
) -> Tuple[Dict[str, Any] | List[Any], Dict[str, str]]:
    headers = _apify_headers()
    try:
        with _retrying_get_session() as session:
            response = session.get(
                f"{APIFY_API_BASE}/{path.lstrip('/')}",
                headers=headers,
                params=params,
                timeout=timeout,
            )
        response.raise_for_status()
        return response.json(), dict(response.headers)
    except requests.HTTPError as exc:
        response = exc.response
        status_code = int(response.status_code) if response is not None else 502
        retryable = status_code in APIFY_RETRYABLE_HTTP_STATUSES
        public_status = 503 if status_code == 429 else 502
        raise HTTPException(
            status_code=public_status,
            detail=_apify_error_detail(
                "APIFY_RATE_LIMITED" if status_code == 429 else "APIFY_REQUEST_FAILED",
                f"Apify request failed with HTTP {status_code}.",
                retryable=retryable,
            ),
        ) from exc
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail=_apify_error_detail(
                "APIFY_REQUEST_FAILED",
                "Apify could not be reached or returned invalid JSON.",
                retryable=True,
            ),
        ) from exc


def _actor_details(actor: Dict[str, object]) -> Dict[str, object]:
    result, _ = _apify_get_json(f"actors/{actor['actorId']}", timeout=20)
    data = (result or {}).get("data") if isinstance(result, dict) else None
    if not isinstance(data, dict) or not data.get("id"):
        raise HTTPException(
            status_code=502,
            detail=_apify_error_detail(
                "APIFY_ACTOR_METADATA_INVALID",
                "Apify returned invalid Actor metadata.",
                retryable=True,
            ),
        )
    return {
        "resolvedActorId": str(data.get("id") or ""),
        "actorName": "/".join(
            value
            for value in [str(data.get("username") or ""), str(data.get("name") or "")]
            if value
        )
        or str(actor.get("name") or ""),
        "modifiedAt": str(data.get("modifiedAt") or ""),
    }


def _verify_actor_identity(
    actor: Dict[str, object], actual_actor_id: object
) -> Dict[str, object]:
    details = _actor_details(actor)
    actual = str(actual_actor_id or "").strip()
    if actual and actual != str(details.get("resolvedActorId") or ""):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "APIFY_ACTOR_MISMATCH",
                "message": "The run or dataset belongs to a different Actor than actorId.",
                "expectedActorId": details.get("resolvedActorId"),
                "actualActorId": actual,
                "retryable": False,
            },
        )
    return details


def _safe_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _record_checksum(value: object) -> str:
    return hashlib.sha256(_safe_json(value).encode("utf-8")).hexdigest()


def _excerpt(value: object, limit: int = 2000) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _first_text(*values: object) -> str:
    for value in values:
        clean = str(value or "").strip()
        if clean:
            return clean
    return ""


def _safe_count(value: object) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _clean_url(value: object) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return candidate[:2000]


def _stable_external_key(kind: str, *values: object) -> str:
    clean_values = [str(value or "").strip() for value in values]
    first = next((value for value in clean_values if value), "")
    if first:
        return f"{kind}:{first}"
    digest = hashlib.sha256("|".join(clean_values).encode("utf-8")).hexdigest()[:24]
    return f"{kind}:anonymous-{digest}"


def _group_identity(item: Dict[str, Any]) -> Tuple[str, str, str]:
    group_title = _first_text(item.get("groupTitle"), "Facebook public group")
    input_url = _clean_url(item.get("inputUrl"))
    facebook_url = _clean_url(item.get("facebookUrl"))
    group_url = input_url
    if not group_url and facebook_url:
        match = re.search(r"(https?://(?:www\.)?facebook\.com/groups/[^/?#]+)", facebook_url)
        group_url = match.group(1) if match else ""
    group_key = _stable_external_key("group", group_url, group_title)
    return group_key, group_title, group_url


def _profile_payload(
    raw_profile: object,
    *,
    fallback_name: object = "",
    fallback_url: object = "",
    group_key: str,
) -> Dict[str, str]:
    profile = raw_profile if isinstance(raw_profile, dict) else {}
    profile_id = _first_text(profile.get("id"), profile.get("profileId"))
    profile_name = _first_text(
        profile.get("name"), profile.get("profileName"), fallback_name, "Unidentified Facebook profile"
    )
    profile_url = _clean_url(
        _first_text(profile.get("profileUrl"), profile.get("url"), fallback_url)
    )
    # A name alone is not a safe cross-group identifier. The group is included
    # whenever the actor did not return a durable platform id or profile URL.
    external_key = _stable_external_key(
        "profile",
        profile_id,
        profile_url,
        f"{group_key}|{profile_name}",
    )
    return {
        "externalKey": external_key,
        "platformId": profile_id,
        "name": profile_name,
        "profileUrl": profile_url,
    }


def _reactions_json(value: object) -> str:
    if isinstance(value, dict):
        clean = {
            str(key)[:80]: int(count)
            for key, count in value.items()
            if isinstance(count, (int, float))
        }
        return _safe_json(clean)[:4000]
    if isinstance(value, list):
        clean_rows = []
        for row in value[:50]:
            if not isinstance(row, dict):
                continue
            clean_rows.append(
                {
                    str(key)[:80]: val
                    for key, val in row.items()
                    if isinstance(val, (str, int, float, bool))
                }
            )
        return _safe_json(clean_rows)[:4000]
    return ""


def _attachment_ocr(item: Dict[str, Any]) -> str:
    output: List[str] = []
    attachments = item.get("attachments")
    if not isinstance(attachments, list):
        return ""
    for attachment in attachments[:20]:
        if not isinstance(attachment, dict):
            continue
        for key in ("ocrText", "ocr", "text"):
            value = attachment.get(key)
            if isinstance(value, str) and value.strip():
                output.append(value.strip())
    return _excerpt("\n".join(output), 4000)


def _apify_headers() -> Dict[str, str]:
    token = os.getenv("APIFY_API_TOKEN", "").strip()
    if not token:
        raise HTTPException(
            status_code=503,
            detail=(
                "APIFY_API_TOKEN is not configured. Export dataset items and submit them in "
                "items, or configure the token server-side."
            ),
        )
    return {"Authorization": f"Bearer {token}"}


def _charged_item_count(charged_events: object) -> int:
    if not isinstance(charged_events, dict):
        return 0
    candidates = []
    for key, value in charged_events.items():
        normalized = str(key or "").casefold()
        if any(token in normalized for token in ("result", "post", "data-extracted", "dataset-item")):
            candidates.append(_safe_count(value))
    return max(candidates, default=0)


def _run_provenance(run_data: Dict[str, Any]) -> Dict[str, object]:
    pricing_info = run_data.get("pricingInfo")
    options = run_data.get("options")
    charged_events = run_data.get("chargedEventCounts")
    return {
        "runStatus": str(run_data.get("status") or "").upper(),
        "statusMessage": _excerpt(run_data.get("statusMessage"), 500),
        "resolvedActorId": str(run_data.get("actId") or ""),
        "actorBuildId": str(run_data.get("buildId") or ""),
        "actorBuildNumber": str(run_data.get("buildNumber") or ""),
        "actorTaskId": str(run_data.get("actorTaskId") or ""),
        "startedAt": str(run_data.get("startedAt") or ""),
        "finishedAt": str(run_data.get("finishedAt") or ""),
        "pricingModel": str(
            (pricing_info or {}).get("pricingModel")
            if isinstance(pricing_info, dict)
            else ""
        ),
        "usageTotalUsd": float(run_data.get("usageTotalUsd") or 0.0),
        "usageUsd": run_data.get("usageUsd") if isinstance(run_data.get("usageUsd"), dict) else {},
        "chargedEventCounts": charged_events if isinstance(charged_events, dict) else {},
        "chargedItemCount": _charged_item_count(charged_events),
        "requestedMaxItems": _safe_count(
            (options or {}).get("maxItems") if isinstance(options, dict) else 0
        ),
        "requestedCostCapUsd": float(
            ((options or {}).get("maxTotalChargeUsd") or 0.0)
            if isinstance(options, dict)
            else 0.0
        ),
    }


def _fetch_run_data(run_id: str) -> Dict[str, Any]:
    result, _ = _apify_get_json(f"actor-runs/{run_id}", timeout=30)
    run_data = (result or {}).get("data") if isinstance(result, dict) else None
    if not isinstance(run_data, dict) or not run_data.get("id"):
        raise HTTPException(
            status_code=502,
            detail=_apify_error_detail(
                "APIFY_RUN_METADATA_INVALID",
                "Apify returned invalid run metadata.",
                retryable=True,
            ),
        )
    return run_data


def _require_succeeded_run(run_data: Dict[str, Any]) -> None:
    run_status = str(run_data.get("status") or "").upper()
    if run_status == "SUCCEEDED":
        return
    if run_status in APIFY_ACTIVE_STATUSES or run_status not in APIFY_TERMINAL_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "APIFY_RUN_NOT_READY",
                "message": "Only terminal SUCCEEDED runs can be imported.",
                "runStatus": run_status or "UNKNOWN",
                "retryable": True,
            },
        )
    raise HTTPException(
        status_code=409,
        detail={
            "code": "APIFY_RUN_NOT_IMPORTABLE",
            "message": "The Apify run ended without succeeding; partial output was not imported.",
            "runStatus": run_status,
            "retryable": False,
        },
    )


def _fetch_dataset_data(dataset_id: str) -> Dict[str, Any]:
    result, _ = _apify_get_json(f"datasets/{dataset_id}", timeout=30)
    dataset = (result or {}).get("data") if isinstance(result, dict) else None
    if not isinstance(dataset, dict) or not dataset.get("id"):
        raise HTTPException(
            status_code=502,
            detail=_apify_error_detail(
                "APIFY_DATASET_METADATA_INVALID",
                "Apify returned invalid dataset metadata.",
                retryable=True,
            ),
        )
    return dataset


def _item_schema_rejection(item: object) -> str:
    if not isinstance(item, dict):
        return "non-object-row"
    recognized = any(
        item.get(key) not in (None, "")
        for key in ("id", "legacyId", "feedbackId", "facebookId", "url", "text")
    )
    diagnostic = any(
        item.get(key) not in (None, "", [], {})
        for key in ("error", "errors", "errorMessage", "errorDescription", "requestError")
    )
    if diagnostic and not recognized:
        return "diagnostic-or-error-row"
    if not recognized:
        return "unsupported-record-type"
    for key in ("topComments", "attachments", "collaborators", "textReferences"):
        if item.get(key) is not None and not isinstance(item.get(key), list):
            return f"invalid-{key}-shape"
    if item.get("user") is not None and not isinstance(item.get("user"), dict):
        return "invalid-user-shape"
    return ""


def _filter_actor_items(items: List[object]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    accepted: List[Dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    for item in items:
        reason = _item_schema_rejection(item)
        if reason:
            reasons[reason] += 1
            continue
        accepted.append(item)
    return accepted, dict(sorted(reasons.items()))


def _fetch_dataset_items(
    dataset_id: str, *, max_items: int, source_total: int
) -> Tuple[List[object], Dict[str, object]]:
    fetched: List[object] = []
    offset = 0
    page_count = 0
    target = max_items + 1
    while len(fetched) < target:
        page_size = min(250, target - len(fetched))
        result, headers = _apify_get_json(
            f"datasets/{dataset_id}/items",
            params={
                "clean": "true",
                "format": "json",
                "offset": offset,
                "limit": page_size,
            },
            timeout=60,
        )
        if not isinstance(result, list):
            raise HTTPException(
                status_code=502,
                detail=_apify_error_detail(
                    "APIFY_DATASET_SHAPE_INVALID",
                    "Apify returned an unexpected dataset item shape.",
                    retryable=True,
                ),
            )
        page_count += 1
        fetched.extend(result)
        header_total = headers.get("X-Apify-Pagination-Total") or headers.get(
            "x-apify-pagination-total"
        )
        if not source_total and header_total:
            try:
                source_total = max(0, int(header_total))
            except ValueError:
                pass
        offset += page_size
        if source_total and offset >= source_total:
            break
        if len(result) < page_size and not source_total:
            break
    return fetched, {
        "fetchPageCount": page_count,
        "rawItemsFetched": len(fetched),
        "sourceTotalItems": source_total,
    }


def _fetch_apify_items(
    payload: ApifyFacebookImportRequest,
) -> Tuple[List[Dict[str, Any]], str, str, Dict[str, object]]:
    actor = _resolve_actor(payload.actor_id)
    fetched_at = _utc_now().isoformat()
    if payload.items is not None:
        valid, rejection_reasons = _filter_actor_items(list(payload.items))
        return valid[: payload.max_items], "", "", {
            "actor": actor,
            "actorDetails": {},
            "actorRun": {},
            "dataset": {},
            "fetchedAt": fetched_at,
            "fetchPageCount": 0,
            "rawItemsFetched": len(payload.items),
            "sourceTotalItems": len(payload.items),
            "schemaRejectedItems": sum(rejection_reasons.values()),
            "schemaRejectionReasons": rejection_reasons,
            "truncated": len(valid) > payload.max_items,
            "inputMode": "exported-items",
        }

    run_id = str(payload.run_id or "").strip()
    dataset_id = str(payload.dataset_id or "").strip()
    run_data: Dict[str, Any] = {}
    dataset: Dict[str, Any] = {}
    if run_id:
        run_data = _fetch_run_data(run_id)
        _require_succeeded_run(run_data)
        actor_details = _verify_actor_identity(actor, run_data.get("actId"))
        dataset_id = str(run_data.get("defaultDatasetId") or "").strip()
        if not dataset_id:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "APIFY_DATASET_NOT_READY",
                    "message": "The succeeded run does not expose a default dataset.",
                    "runStatus": "SUCCEEDED",
                    "retryable": True,
                },
            )
        dataset = _fetch_dataset_data(dataset_id)
    else:
        dataset = _fetch_dataset_data(dataset_id)
        actual_run_id = str(dataset.get("actRunId") or "").strip()
        if actual_run_id:
            run_data = _fetch_run_data(actual_run_id)
            _require_succeeded_run(run_data)
            run_id = actual_run_id
        actual_actor_id = dataset.get("actId") or run_data.get("actId")
        actor_details = _verify_actor_identity(actor, actual_actor_id) if actual_actor_id else {}

    if run_data:
        run_dataset_id = str(run_data.get("defaultDatasetId") or "")
        if run_dataset_id and str(dataset.get("id") or "") != run_dataset_id:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "APIFY_RUN_DATASET_MISMATCH",
                    "message": "The selected dataset is not the verified run's default dataset.",
                    "retryable": False,
                },
            )
    # Pagination offsets address stored rows, while clean=true can omit empty rows.
    # Use itemCount (not cleanItemCount) so omitted rows cannot make us stop early.
    source_total = _safe_count(dataset.get("itemCount"))
    raw_items, pagination = _fetch_dataset_items(
        dataset_id, max_items=payload.max_items, source_total=source_total
    )
    valid, rejection_reasons = _filter_actor_items(raw_items)
    truncated = (
        len(valid) > payload.max_items
        or (source_total > int(pagination.get("rawItemsFetched") or 0))
    )
    return valid[: payload.max_items], run_id, dataset_id, {
        "actor": actor,
        "actorDetails": actor_details,
        "actorRun": _run_provenance(run_data) if run_data else {},
        "dataset": {
            "datasetId": str(dataset.get("id") or dataset_id),
            "createdAt": str(dataset.get("createdAt") or ""),
            "modifiedAt": str(dataset.get("modifiedAt") or ""),
            "itemCount": _safe_count(dataset.get("itemCount")),
            "cleanItemCount": _safe_count(dataset.get("cleanItemCount")),
            "actorRunId": str(dataset.get("actRunId") or ""),
        },
        "fetchedAt": fetched_at,
        **pagination,
        "schemaRejectedItems": sum(rejection_reasons.values()),
        "schemaRejectionReasons": rejection_reasons,
        "truncated": bool(truncated),
        "inputMode": "run" if payload.run_id else "dataset",
    }


def _add_profile_entity(
    entities: Dict[str, Dict[str, object]],
    *,
    profile: Dict[str, str],
    source_id: str,
    evidence_id: str,
    retention_expires_at: str,
) -> Optional[str]:
    ftm_properties: Dict[str, List[str]] = {"name": [profile["name"]]}
    if profile.get("platformId"):
        ftm_properties["idNumber"] = [f"facebook-profile:{profile['platformId']}"]
    if profile.get("profileUrl"):
        ftm_properties["sourceUrl"] = [profile["profileUrl"]]
    identity = f"{source_id}|{profile['externalKey']}"
    resolved_id = _investigation_id("entity", "Social profile", identity)
    existing = entities.get(resolved_id) or {}
    aliases = []
    for value in [existing.get("name")] + list(existing.get("aliases") or []) + [
        profile["name"]
    ]:
        clean = str(value or "").strip()
        if clean and clean not in aliases:
            aliases.append(clean)
    return _graph_entity(
        entities,
        name=profile["name"],
        entity_type="Social profile",
        identity=identity,
        entityRole="Source-scoped Facebook profile",
        sourceId=source_id,
        sourceExternalId=profile["externalKey"],
        platform="facebook",
        platformProfileId=profile.get("platformId", ""),
        profileUrl=profile.get("profileUrl", ""),
        aliases=aliases,
        evidenceIds=[evidence_id],
        retentionExpiresAt=retention_expires_at,
        retentionAction="remove-source-content-at-expiry",
        ftmSchema="Person",
        ftmPropertiesJson=_safe_json(ftm_properties),
        identityStatus="unresolved",
        identityPolicy="Never merge with a Person without analyst resolution",
    )


def build_apify_facebook_bundle(
    *,
    case_id: str,
    root_entity_id: str,
    actor_id: str,
    items: List[Dict[str, Any]],
    lawful_basis: str,
    investigation_purpose: str,
    retention_days: int,
    include_top_comments: bool,
    promote_posts_to_graph: bool,
    run_id: str = "",
    dataset_id: str = "",
    fetch_metadata: Optional[Dict[str, object]] = None,
) -> Tuple[Dict[str, object], Dict[str, object]]:
    entities: Dict[str, Dict[str, object]] = {}
    links: Dict[str, Dict[str, object]] = {}
    sources: Dict[str, Dict[str, object]] = {}
    evidence: Dict[str, Dict[str, object]] = {}
    retention_expires_at = (_utc_now() + timedelta(days=retention_days)).isoformat()
    fetch_metadata = fetch_metadata or {}
    actor = dict(fetch_metadata.get("actor") or _resolve_actor(actor_id))
    actor_details = dict(fetch_metadata.get("actorDetails") or {})
    actor_run = dict(fetch_metadata.get("actorRun") or {})
    actor_name = str(actor.get("name") or actor_id)
    actor_url = str(actor.get("url") or "")
    actor_schema_version = str(actor.get("schemaVersion") or APIFY_OUTPUT_MAPPING_VERSION)
    source_name = f"Facebook public groups via Apify · {actor_name}"
    source_id = _graph_source(
        sources,
        name=source_name,
        url=actor_url,
        source_type="Public social-media dataset",
        connector="apify",
        platform="facebook",
        actorId=str(actor.get("actorId") or actor_id),
        actorName=actor_name,
        resolvedActorId=actor_details.get("resolvedActorId") or actor_run.get("resolvedActorId"),
        externalRunId=run_id,
        externalDatasetId=dataset_id,
        ingestionMode="apify-dataset-import",
        actorSchemaVersion=actor_schema_version,
        actorBuildId=actor_run.get("actorBuildId"),
        actorBuildNumber=actor_run.get("actorBuildNumber"),
        pricingModel=actor_run.get("pricingModel"),
        usageTotalUsd=actor_run.get("usageTotalUsd"),
        chargedItemCount=actor_run.get("chargedItemCount"),
        chargedEventCountsJson=_safe_json(actor_run.get("chargedEventCounts") or {}),
        requestedCostCapUsd=actor_run.get("requestedCostCapUsd"),
        fetchedAt=fetch_metadata.get("fetchedAt") or _utc_now().isoformat(),
        sourceTotalItems=fetch_metadata.get("sourceTotalItems") or 0,
        datasetTruncated=bool(fetch_metadata.get("truncated")),
        schemaRejectedItems=fetch_metadata.get("schemaRejectedItems") or 0,
        lawfulBasis=lawful_basis,
        investigationPurpose=investigation_purpose,
        retentionDays=retention_days,
        retentionEnforcement="case-scoped-cleanup",
        rawArtifactPolicy="checksum-and-source-excerpt-only",
        publicContentOnly=True,
        collectionPolicy="Public groups only; no credentials or private-group access",
        actorUrl=actor_url,
    )

    accepted = 0
    rejected = 0
    duplicate_count = 0
    seen_post_keys = set()
    checksums: List[str] = []
    for item in items:
        checksum = _record_checksum(item)
        post_url = _clean_url(_first_text(item.get("url"), item.get("facebookUrl")))
        post_key = _stable_external_key(
            "post",
            item.get("id"),
            item.get("legacyId"),
            item.get("facebookId"),
            post_url,
        )
        if post_key in seen_post_keys:
            duplicate_count += 1
            continue
        seen_post_keys.add(post_key)
        text = _excerpt(item.get("text"), 4000)
        group_key, group_title, group_url = _group_identity(item)
        author = _profile_payload(item.get("user"), group_key=group_key)
        if not any([item.get("id"), item.get("legacyId"), item.get("facebookId"), post_url, text]):
            rejected += 1
            continue
        accepted += 1
        checksums.append(checksum)
        published_at = _first_text(item.get("time"), item.get("date"))
        evidence_id = _graph_evidence(
            evidence,
            source_id=source_id,
            source_name=source_name,
            title=f"Facebook post in {group_title}",
            source_url=post_url or group_url,
            evidence_type="Public Facebook group post",
            published_at=published_at,
            note=text,
            identity=f"{actor_id}|{post_key}",
        )
        evidence[evidence_id].update(
            {
                "sourceRecordKey": post_key,
                "rawRecordChecksum": checksum,
                "retentionExpiresAt": retention_expires_at,
                "collectionMethod": "Apify actor dataset import",
                "platform": "facebook",
                "groupTitle": group_title,
                "externalRunId": run_id,
                "externalDatasetId": dataset_id,
                "actorId": str(actor.get("actorId") or actor_id),
                "actorName": actor_name,
                "actorSchemaVersion": actor_schema_version,
                "actorBuildId": actor_run.get("actorBuildId") or "",
                "actorBuildNumber": actor_run.get("actorBuildNumber") or "",
                "fetchedAt": fetch_metadata.get("fetchedAt") or "",
                "rawArtifactPolicy": "checksum-and-source-excerpt-only",
            }
        )

        group_ftm = {"name": [group_title]}
        if group_url:
            group_ftm["sourceUrl"] = [group_url]
        group_ftm["idNumber"] = [f"facebook-{group_key}"]
        group_id = _graph_entity(
            entities,
            name=group_title,
            entity_type="Social group",
            identity=f"{source_id}|{group_key}",
            entityRole="Public Facebook group",
            sourceId=source_id,
            sourceExternalId=group_key,
            platform="facebook",
            groupUrl=group_url,
            evidenceIds=[evidence_id],
            retentionExpiresAt=retention_expires_at,
            retentionAction="remove-source-content-at-expiry",
            ftmSchema="Organization",
            ftmPropertiesJson=_safe_json(group_ftm),
        )
        author_id = _add_profile_entity(
            entities,
            profile=author,
            source_id=source_id,
            evidence_id=evidence_id,
            retention_expires_at=retention_expires_at,
        )

        if promote_posts_to_graph:
            post_title = _excerpt(text, 96) or f"Facebook post {post_key.rsplit(':', 1)[-1]}"
            post_ftm: Dict[str, List[str]] = {"title": [post_title]}
            if text:
                post_ftm["bodyText"] = [text]
            if published_at:
                post_ftm["publishedAt"] = [published_at]
            if post_url:
                post_ftm["sourceUrl"] = [post_url]
            post_id = _graph_entity(
                entities,
                name=post_title,
                entity_type="Social post",
                identity=f"{source_id}|{post_key}",
                entityRole="Public Facebook group post",
                sourceId=source_id,
                sourceExternalId=post_key,
                platform="facebook",
                postUrl=post_url,
                publishedAt=published_at,
                contentText=text,
                likesCount=_safe_count(item.get("likesCount")),
                sharesCount=_safe_count(item.get("sharesCount")),
                commentsCount=_safe_count(item.get("commentsCount")),
                reactionCountsJson=_reactions_json(item.get("reactions")),
                attachmentCount=len(item.get("attachments") or [])
                if isinstance(item.get("attachments"), list)
                else 0,
                attachmentOcrText=_attachment_ocr(item),
                rawRecordChecksum=checksum,
                retentionExpiresAt=retention_expires_at,
                retentionAction="remove-source-content-at-expiry",
                actorSchemaVersion=actor_schema_version,
                actorBuildNumber=actor_run.get("actorBuildNumber") or "",
                evidenceIds=[evidence_id],
                ftmSchema="Article",
                ftmPropertiesJson=_safe_json(post_ftm),
            )
            _graph_link(
                links,
                case_id=case_id,
                from_id=author_id,
                to_id=post_id,
                relationship_type="Published social post",
                evidence_ids=[evidence_id],
                confidence=1.0,
                verification_status="source-stated",
                details="The actor record identifies this display profile as the post author.",
                properties={
                    "platform": "facebook",
                    "publishedAt": published_at,
                    "retentionExpiresAt": retention_expires_at,
                    "actorSchemaVersion": actor_schema_version,
                },
            )
            _graph_link(
                links,
                case_id=case_id,
                from_id=post_id,
                to_id=group_id,
                relationship_type="Posted in social group",
                evidence_ids=[evidence_id],
                confidence=1.0,
                verification_status="source-stated",
                details="The post was observed in this public Facebook group.",
                properties={
                    "platform": "facebook",
                    "retentionExpiresAt": retention_expires_at,
                    "actorSchemaVersion": actor_schema_version,
                },
            )

            if include_top_comments:
                comments = item.get("topComments")
                for raw_comment in comments[:20] if isinstance(comments, list) else []:
                    if not isinstance(raw_comment, dict):
                        continue
                    comment_text = _excerpt(raw_comment.get("text"), 2000)
                    comment_url = _clean_url(raw_comment.get("commentUrl"))
                    comment_key = _stable_external_key(
                        "comment",
                        raw_comment.get("id"),
                        raw_comment.get("feedbackId"),
                        comment_url,
                        f"{post_key}|{comment_text}",
                    )
                    comment_evidence_id = _graph_evidence(
                        evidence,
                        source_id=source_id,
                        source_name=source_name,
                        title=f"Top comment on {post_title[:80]}",
                        source_url=comment_url or post_url,
                        evidence_type="Public Facebook comment",
                        published_at=raw_comment.get("date"),
                        note=comment_text,
                        identity=f"{actor_id}|{comment_key}",
                    )
                    evidence[comment_evidence_id].update(
                        {
                            "sourceRecordKey": comment_key,
                            "parentSourceRecordKey": post_key,
                            "rawRecordChecksum": _record_checksum(raw_comment),
                            "retentionExpiresAt": retention_expires_at,
                            "collectionMethod": "Apify actor dataset import",
                            "platform": "facebook",
                            "externalRunId": run_id,
                            "externalDatasetId": dataset_id,
                            "actorId": str(actor.get("actorId") or actor_id),
                            "actorName": actor_name,
                            "actorSchemaVersion": actor_schema_version,
                            "actorBuildId": actor_run.get("actorBuildId") or "",
                            "actorBuildNumber": actor_run.get("actorBuildNumber") or "",
                            "fetchedAt": fetch_metadata.get("fetchedAt") or "",
                            "rawArtifactPolicy": "checksum-and-source-excerpt-only",
                        }
                    )
                    commenter = _profile_payload(
                        {
                            "profileId": raw_comment.get("profileId"),
                            "profileName": raw_comment.get("profileName"),
                            "profileUrl": raw_comment.get("profileUrl"),
                        },
                        group_key=group_key,
                    )
                    commenter_id = _add_profile_entity(
                        entities,
                        profile=commenter,
                        source_id=source_id,
                        evidence_id=comment_evidence_id,
                        retention_expires_at=retention_expires_at,
                    )
                    comment_title = _excerpt(comment_text, 96) or "Facebook comment"
                    comment_ftm: Dict[str, List[str]] = {"title": [comment_title]}
                    if comment_text:
                        comment_ftm["bodyText"] = [comment_text]
                    if raw_comment.get("date"):
                        comment_ftm["publishedAt"] = [str(raw_comment.get("date"))]
                    if comment_url:
                        comment_ftm["sourceUrl"] = [comment_url]
                    comment_id = _graph_entity(
                        entities,
                        name=comment_title,
                        entity_type="Social comment",
                        identity=f"{source_id}|{comment_key}",
                        entityRole="Public Facebook comment",
                        sourceId=source_id,
                        sourceExternalId=comment_key,
                        platform="facebook",
                        commentUrl=comment_url,
                        publishedAt=_first_text(raw_comment.get("date")),
                        contentText=comment_text,
                        likesCount=_safe_count(raw_comment.get("likesCount")),
                        threadingDepth=_safe_count(raw_comment.get("threadingDepth")),
                        retentionExpiresAt=retention_expires_at,
                        retentionAction="remove-source-content-at-expiry",
                        actorSchemaVersion=actor_schema_version,
                        actorBuildNumber=actor_run.get("actorBuildNumber") or "",
                        evidenceIds=[comment_evidence_id],
                        ftmSchema="Article",
                        ftmPropertiesJson=_safe_json(comment_ftm),
                    )
                    _graph_link(
                        links,
                        case_id=case_id,
                        from_id=commenter_id,
                        to_id=comment_id,
                        relationship_type="Published social comment",
                        evidence_ids=[comment_evidence_id],
                        confidence=1.0,
                        verification_status="source-stated",
                        properties={
                            "platform": "facebook",
                            "retentionExpiresAt": retention_expires_at,
                            "actorSchemaVersion": actor_schema_version,
                        },
                    )
                    _graph_link(
                        links,
                        case_id=case_id,
                        from_id=comment_id,
                        to_id=post_id,
                        relationship_type="Commented on social post",
                        evidence_ids=[comment_evidence_id],
                        confidence=1.0,
                        verification_status="source-stated",
                        properties={
                            "platform": "facebook",
                            "retentionExpiresAt": retention_expires_at,
                            "actorSchemaVersion": actor_schema_version,
                        },
                    )

    bundle = {
        "caseId": case_id,
        "rootEntityId": root_entity_id,
        "entities": list(entities.values()),
        "relationships": list(links.values()),
        "sources": list(sources.values()),
        "evidence": list(evidence.values()),
    }
    metrics = {
        "sourceId": source_id,
        "itemsReceived": int(fetch_metadata.get("rawItemsFetched") or len(items)),
        "itemsAccepted": accepted,
        "itemsRejected": rejected + int(fetch_metadata.get("schemaRejectedItems") or 0),
        "schemaRejectedItems": int(fetch_metadata.get("schemaRejectedItems") or 0),
        "schemaRejectionReasons": dict(fetch_metadata.get("schemaRejectionReasons") or {}),
        "duplicateItems": duplicate_count,
        "entitiesProcessed": len(entities),
        "relationshipsProcessed": len(links),
        "evidenceProcessed": len(evidence),
        "rawRecordChecksums": checksums,
        "retentionExpiresAt": retention_expires_at,
        "retentionEnforcement": "case-scoped-cleanup",
        "rawArtifactPolicy": "checksum-and-source-excerpt-only",
        "actor": {
            "actorId": str(actor.get("actorId") or actor_id),
            "name": actor_name,
            "url": actor_url,
            "schemaVersion": actor_schema_version,
            "resolvedActorId": actor_details.get("resolvedActorId")
            or actor_run.get("resolvedActorId")
            or "",
            "buildId": actor_run.get("actorBuildId") or "",
            "buildNumber": actor_run.get("actorBuildNumber") or "",
        },
        "runStatus": actor_run.get("runStatus") or ("SUCCEEDED" if run_id else "NOT_APPLICABLE"),
        "pricingModel": actor_run.get("pricingModel") or "",
        "usageTotalUsd": actor_run.get("usageTotalUsd") or 0.0,
        "chargedItemCount": actor_run.get("chargedItemCount") or 0,
        "chargedEventCounts": actor_run.get("chargedEventCounts") or {},
        "requestedCostCapUsd": actor_run.get("requestedCostCapUsd") or 0.0,
        "sourceTotalItems": int(fetch_metadata.get("sourceTotalItems") or len(items)),
        "truncated": bool(fetch_metadata.get("truncated")),
        "fetchPageCount": int(fetch_metadata.get("fetchPageCount") or 0),
        "fetchedAt": str(fetch_metadata.get("fetchedAt") or _utc_now().isoformat()),
        "inputMode": str(fetch_metadata.get("inputMode") or "exported-items"),
    }
    return bundle, metrics


def _persist_social_import_run(
    *,
    case_id: str,
    source_id: str,
    actor_id: str,
    external_run_id: str,
    external_dataset_id: str,
    payload: ApifyFacebookImportRequest,
    metrics: Dict[str, object],
) -> str:
    identity = external_run_id or external_dataset_id or _record_checksum(
        metrics.get("rawRecordChecksums") or []
    )
    run_id = _investigation_id("import-run", case_id, source_id, actor_id, identity)
    query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
    MATCH (source:InvestigationDataSource {sourceId: $sourceId})
    MERGE (run:InvestigationImportRun {runId: $runId})
    ON CREATE SET run.createdAt = datetime(), run.startedAt = datetime()
    SET run.caseId = $caseId, run.sourceId = $sourceId,
        run.status = 'completed', run.connector = 'apify', run.platform = 'facebook',
        run.actorId = $actorId, run.externalRunId = $externalRunId,
        run.externalDatasetId = $externalDatasetId,
        run.rawItemCount = $rawItemCount, run.acceptedItemCount = $acceptedItemCount,
        run.rejectedItemCount = $rejectedItemCount, run.duplicateItemCount = $duplicateItemCount,
        run.entityCount = $entityCount, run.relationshipCount = $relationshipCount,
        run.evidenceCount = $evidenceCount, run.errorCount = $errorCount,
        run.maxItems = $maxItems, run.lawfulBasis = $lawfulBasis,
        run.investigationPurpose = $investigationPurpose,
        run.retentionDays = $retentionDays,
        run.retentionExpiresAt = datetime($retentionExpiresAt),
        run.retentionEnforcement = $retentionEnforcement,
        run.rawArtifactPolicy = $rawArtifactPolicy,
        run.actorName = $actorName, run.actorUrl = $actorUrl,
        run.resolvedActorId = $resolvedActorId,
        run.actorSchemaVersion = $actorSchemaVersion,
        run.actorBuildId = $actorBuildId, run.actorBuildNumber = $actorBuildNumber,
        run.externalRunStatus = $externalRunStatus,
        run.pricingModel = $pricingModel, run.usageTotalUsd = $usageTotalUsd,
        run.requestedCostCapUsd = $requestedCostCapUsd,
        run.chargedItemCount = $chargedItemCount,
        run.chargedEventCountsJson = $chargedEventCountsJson,
        run.sourceTotalItems = $sourceTotalItems, run.datasetTruncated = $datasetTruncated,
        run.fetchPageCount = $fetchPageCount, run.fetchedAt = datetime($fetchedAt),
        run.schemaRejectedItemCount = $schemaRejectedItemCount,
        run.schemaRejectionReasonsJson = $schemaRejectionReasonsJson,
        run.inputMode = $inputMode,
        run.inputFingerprint = $inputFingerprint,
        run.completedAt = datetime(), run.updatedAt = datetime()
    MERGE (caseNode)-[:HAS_IMPORT_RUN]->(run)
    MERGE (source)-[:HAS_IMPORT_RUN]->(run)
    RETURN run.runId AS runId
    """
    actor = dict(metrics.get("actor") or {})
    params = {
        "caseId": case_id,
        "sourceId": source_id,
        "runId": run_id,
        "actorId": actor.get("actorId") or actor_id,
        "actorName": actor.get("name") or "",
        "actorUrl": actor.get("url") or "",
        "resolvedActorId": actor.get("resolvedActorId") or "",
        "actorSchemaVersion": actor.get("schemaVersion") or "",
        "actorBuildId": actor.get("buildId") or "",
        "actorBuildNumber": actor.get("buildNumber") or "",
        "externalRunId": external_run_id,
        "externalDatasetId": external_dataset_id,
        "rawItemCount": int(metrics.get("itemsReceived") or 0),
        "acceptedItemCount": int(metrics.get("itemsAccepted") or 0),
        "rejectedItemCount": int(metrics.get("itemsRejected") or 0),
        "duplicateItemCount": int(metrics.get("duplicateItems") or 0),
        "entityCount": int(metrics.get("entitiesProcessed") or 0),
        "relationshipCount": int(metrics.get("relationshipsProcessed") or 0),
        "evidenceCount": int(metrics.get("evidenceProcessed") or 0),
        "errorCount": int(metrics.get("itemsRejected") or 0),
        "maxItems": payload.max_items,
        "lawfulBasis": payload.lawful_basis,
        "investigationPurpose": payload.investigation_purpose,
        "retentionDays": payload.retention_days,
        "retentionExpiresAt": metrics.get("retentionExpiresAt"),
        "retentionEnforcement": metrics.get("retentionEnforcement") or "",
        "rawArtifactPolicy": metrics.get("rawArtifactPolicy") or "",
        "externalRunStatus": metrics.get("runStatus") or "",
        "pricingModel": metrics.get("pricingModel") or "",
        "usageTotalUsd": float(metrics.get("usageTotalUsd") or 0.0),
        "requestedCostCapUsd": float(metrics.get("requestedCostCapUsd") or 0.0),
        "chargedItemCount": int(metrics.get("chargedItemCount") or 0),
        "chargedEventCountsJson": _safe_json(metrics.get("chargedEventCounts") or {}),
        "sourceTotalItems": int(metrics.get("sourceTotalItems") or 0),
        "datasetTruncated": bool(metrics.get("truncated")),
        "fetchPageCount": int(metrics.get("fetchPageCount") or 0),
        "fetchedAt": metrics.get("fetchedAt") or _utc_now().isoformat(),
        "schemaRejectedItemCount": int(metrics.get("schemaRejectedItems") or 0),
        "schemaRejectionReasonsJson": _safe_json(metrics.get("schemaRejectionReasons") or {}),
        "inputMode": metrics.get("inputMode") or "",
        "inputFingerprint": _record_checksum(
            {
                "actorId": actor_id,
                "runId": external_run_id,
                "datasetId": external_dataset_id,
                "checksums": metrics.get("rawRecordChecksums") or [],
            }
        ),
    }
    with _db_session(get_driver()) as session:
        records = _execute_write(session, query, params)
    if not records:
        raise HTTPException(status_code=404, detail="Case or imported data source not found")
    return run_id


@router.get("/connectors/apify-facebook/capabilities")
def get_apify_facebook_connector_capabilities():
    token_configured = bool(os.getenv("APIFY_API_TOKEN", "").strip())
    allowed_cases = _env_csv("FS_APIFY_FACEBOOK_ALLOWED_CASES")
    allowed_operators = _env_csv("FS_APIFY_FACEBOOK_ALLOWED_OPERATORS")
    start_enabled = (
        _managed_starts_enabled()
        and token_configured
        and bool(allowed_cases)
        and bool(allowed_operators)
    )
    return {
        "connectorId": APIFY_CONNECTOR_ID,
        "configured": token_configured,
        "enabled": _imports_enabled(),
        "killSwitch": {
            "environmentVariable": "FS_APIFY_FACEBOOK_IMPORT_ENABLED",
            "importsEnabled": _imports_enabled(),
        },
        "actor": {
            "actorId": DEFAULT_APIFY_FACEBOOK_ACTOR_ID,
            "name": DEFAULT_APIFY_FACEBOOK_ACTOR_NAME,
            "url": APIFY_ACTOR_PUBLIC_URL,
            "schemaVersion": APIFY_OUTPUT_MAPPING_VERSION,
        },
        "actors": [
            {
                key: value
                for key, value in actor.items()
                if key != "aliases"
            }
            for actor in APIFY_FACEBOOK_ACTORS.values()
        ],
        "supportedInputs": ["runId", "datasetId", "items"],
        "maxItemsPerImport": 1000,
        "startsPaidRuns": bool(start_enabled),
        "managedRuns": {
            "implemented": True,
            "enabled": bool(start_enabled),
            "disabledByDefault": True,
            "requiresServerToken": True,
            "requiresAllowedCase": True,
            "requiresAllowedOperator": True,
            "oneActiveRunPerCase": True,
            "publicGroupUrlsOnly": True,
            "maxItemsPerRun": 500,
            "maxRunChargeUsd": _maximum_run_charge_usd(),
            "monthlyProjectBudgetUsd": _monthly_budget_usd(),
            "budgetScope": "FS-managed Apify runs only",
            "statusMode": "polling-or-verified-webhook",
        },
        "budgetPolicy": (
            "Existing output imports do not start Actors. Optional managed starts remain disabled "
            "until the operator configures token, case/operator allowlists, and hard cost caps."
        ),
        "identityPolicy": (
            "Facebook profiles are source-scoped and display names are aliases. They are never "
            "merged into official people without analyst review."
        ),
        "privacyPolicy": {
            "publicGroupsOnly": True,
            "requiresLawfulBasis": True,
            "requiresInvestigationPurpose": True,
            "rawRecordsStored": False,
            "rawChecksumsStored": True,
            "rawArtifactPolicy": "checksum-and-source-excerpt-only",
            "retentionDays": {"minimum": 7, "default": 180, "maximum": 730},
            "retentionEnforcement": {
                "mode": "case-scoped-cleanup",
                "dryRunDefault": True,
                "automaticScheduleConfigured": False,
                "deletionRequiresEnvironmentApproval": True,
                "environmentVariable": "FS_APIFY_FACEBOOK_RETENTION_DELETE_ENABLED",
            },
        },
        "runImportPolicy": {
            "requiredTerminalStatus": "SUCCEEDED",
            "partialRunningOrFailedOutputImported": False,
            "actorIdentityVerified": True,
            "datasetPagination": True,
            "truncationReported": True,
            "schemaVersion": APIFY_OUTPUT_MAPPING_VERSION,
            "diagnosticRowsRejected": True,
        },
        "authentication": {
            "apifyTokenLocation": "server-only Authorization header",
            "apiProtection": "Freedom Square global auth middleware",
            "webhookSecretRequired": True,
        },
    }


def _execute_apify_facebook_import(
    case_id: str, payload: ApifyFacebookImportRequest
) -> Dict[str, object]:
    if not _imports_enabled():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "APIFY_IMPORT_DISABLED",
                "message": "The Apify Facebook import kill switch is off.",
                "retryable": False,
            },
        )
    case_row, _ = _case_and_report_for_graph(case_id)
    base_bundle = _build_investigation_graph_bundle(
        case_row, {"reportId": None, "payload": {}}
    )
    items, external_run_id, external_dataset_id, fetch_metadata = _fetch_apify_items(payload)
    actor = dict(fetch_metadata.get("actor") or {})
    canonical_actor_id = str(actor.get("actorId") or payload.actor_id)
    social_bundle, metrics = build_apify_facebook_bundle(
        case_id=case_id,
        root_entity_id=str(base_bundle.get("rootEntityId") or ""),
        actor_id=canonical_actor_id,
        items=items,
        lawful_basis=payload.lawful_basis,
        investigation_purpose=payload.investigation_purpose,
        retention_days=payload.retention_days,
        include_top_comments=payload.include_top_comments,
        promote_posts_to_graph=payload.promote_posts_to_graph,
        run_id=external_run_id,
        dataset_id=external_dataset_id,
        fetch_metadata=fetch_metadata,
    )
    if int(metrics.get("itemsAccepted") or 0) == 0:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "APIFY_NO_IMPORTABLE_RECORDS",
                "message": "No importable Facebook post records were found in the supplied dataset.",
                "schemaRejectedItems": metrics.get("schemaRejectedItems") or 0,
                "schemaRejectionReasons": metrics.get("schemaRejectionReasons") or {},
                "retryable": False,
            },
        )
    base_entities = {
        str(row.get("entityId")): row for row in base_bundle.get("entities") or []
    }
    for row in social_bundle.get("entities") or []:
        base_entities[str(row.get("entityId"))] = row
    social_bundle["entities"] = list(base_entities.values())
    _persist_investigation_graph_bundle(social_bundle)
    run_id = _persist_social_import_run(
        case_id=case_id,
        source_id=str(metrics.get("sourceId") or ""),
        actor_id=canonical_actor_id,
        external_run_id=external_run_id,
        external_dataset_id=external_dataset_id,
        payload=payload,
        metrics=metrics,
    )
    graph = _load_investigation_graph(case_id)
    graph["importResult"] = {
        "runId": run_id,
        "sourceId": metrics.get("sourceId"),
        "actorId": canonical_actor_id,
        "externalRunId": external_run_id,
        "externalDatasetId": external_dataset_id,
        **{key: value for key, value in metrics.items() if key != "rawRecordChecksums"},
        "identityPolicy": (
            "Social display names were saved as sourced aliases on source-scoped profiles; "
            "no profile was merged with an official person."
        ),
        "message": "Public Facebook group records were imported with evidence and provenance.",
    }
    return graph


@router.post("/cases/{case_id}/social/import/apify-facebook")
def import_apify_facebook_public_groups(
    case_id: str, payload: ApifyFacebookImportRequest
):
    return _execute_apify_facebook_import(case_id, payload)


def _authorize_managed_operation(case_id: str, operator_id: str) -> None:
    allowed_cases = set(_env_csv("FS_APIFY_FACEBOOK_ALLOWED_CASES"))
    allowed_operators = set(_env_csv("FS_APIFY_FACEBOOK_ALLOWED_OPERATORS"))
    if not allowed_cases or not allowed_operators:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "APIFY_MANAGED_AUTHORIZATION_NOT_CONFIGURED",
                "message": "Managed Apify operations require explicit case and operator allowlists.",
                "retryable": False,
            },
        )
    if case_id not in allowed_cases or operator_id not in allowed_operators:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "APIFY_MANAGED_OPERATION_FORBIDDEN",
                "message": "This case/operator pair is not authorized for managed Apify operations.",
                "retryable": False,
            },
        )


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    iso_format = getattr(value, "iso_format", None)
    if callable(iso_format):
        return iso_format()
    return str(value)


def _parse_json_object(value: object) -> Dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _connector_run_contract(properties: Dict[str, object]) -> Dict[str, object]:
    row = {str(key): _json_safe(value) for key, value in properties.items()}
    status_value = str(row.get("status") or "unknown")
    retryable = status_value in {"running", "ready-to-import", "import-failed", "start-unknown"}
    return {
        "connectorRunId": row.get("connectorRunId"),
        "caseId": row.get("caseId"),
        "connectorId": APIFY_CONNECTOR_ID,
        "status": status_value,
        "retryable": retryable,
        "actor": {
            "actorId": row.get("actorId") or "",
            "name": row.get("actorName") or "",
            "url": row.get("actorUrl") or "",
            "schemaVersion": row.get("actorSchemaVersion") or "",
            "resolvedActorId": row.get("resolvedActorId") or "",
            "buildId": row.get("actorBuildId") or "",
            "buildNumber": row.get("actorBuildNumber") or "",
        },
        "external": {
            "runId": row.get("externalRunId") or "",
            "datasetId": row.get("externalDatasetId") or "",
            "runStatus": row.get("externalRunStatus") or "",
            "statusMessage": row.get("externalStatusMessage") or "",
        },
        "request": {
            "groupUrls": list(row.get("groupUrls") or []),
            "maxItems": int(row.get("maxItems") or 0),
            "maxTotalChargeUsd": float(row.get("requestedCostCapUsd") or 0.0),
            "onlyPostsNewerThan": row.get("onlyPostsNewerThan") or None,
            "includeTopComments": bool(row.get("includeTopComments", True)),
            "promotePostsToGraph": bool(row.get("promotePostsToGraph", True)),
            "lawfulBasis": row.get("lawfulBasis") or "",
            "investigationPurpose": row.get("investigationPurpose") or "",
            "retentionDays": int(row.get("retentionDays") or 0),
            "operatorId": row.get("operatorId") or "",
        },
        "usage": {
            "pricingModel": row.get("pricingModel") or "",
            "usageTotalUsd": float(row.get("usageTotalUsd") or 0.0),
            "chargedItemCount": int(row.get("chargedItemCount") or 0),
            "chargedEventCounts": _parse_json_object(row.get("chargedEventCountsJson")),
            "monthlyProjectBudgetUsd": float(row.get("monthlyBudgetUsd") or _monthly_budget_usd()),
            "monthlyReservedAtStartUsd": float(row.get("monthlyReservedAtStartUsd") or 0.0),
        },
        "import": {
            "importRunId": row.get("importRunId") or "",
            "sourceId": row.get("sourceId") or "",
            "itemsAccepted": int(row.get("acceptedItemCount") or 0),
            "itemsRejected": int(row.get("rejectedItemCount") or 0),
            "duplicateItems": int(row.get("duplicateItemCount") or 0),
            "truncated": bool(row.get("datasetTruncated", False)),
        },
        "error": (
            {
                "code": row.get("errorCode") or "APIFY_CONNECTOR_ERROR",
                "message": row.get("errorMessage") or "Connector operation failed.",
                "at": row.get("errorAt") or None,
            }
            if row.get("errorMessage")
            else None
        ),
        "timestamps": {
            "createdAt": row.get("createdAt") or None,
            "startedAt": row.get("startedAt") or None,
            "lastCheckedAt": row.get("lastCheckedAt") or None,
            "completedAt": row.get("completedAt") or None,
        },
        "idempotencyKeyHash": row.get("idempotencyKeyHash") or "",
    }


def _load_connector_run(case_id: str, connector_run_id: str) -> Dict[str, object]:
    query = """
    MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_CONNECTOR_RUN]->
          (run:InvestigationConnectorRun {connectorRunId: $connectorRunId})
    RETURN properties(run) AS run
    """
    with _db_session(get_driver()) as session:
        records = _execute_read(
            session, query, {"caseId": case_id, "connectorRunId": connector_run_id}
        )
    if not records:
        raise HTTPException(status_code=404, detail="Apify connector run not found for this case")
    return dict(records[0].get("run") or {})


def _list_connector_runs(case_id: str, limit: int = 50) -> List[Dict[str, object]]:
    _case_and_report_for_graph(case_id)
    query = """
    MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_CONNECTOR_RUN]->
          (run:InvestigationConnectorRun {connector: 'apify', platform: 'facebook'})
    RETURN properties(run) AS run
    ORDER BY run.createdAt DESC
    LIMIT $limit
    """
    with _db_session(get_driver()) as session:
        records = _execute_read(session, query, {"caseId": case_id, "limit": int(limit)})
    return [_connector_run_contract(dict(record.get("run") or {})) for record in records]


def _reserve_connector_run(
    *,
    case_id: str,
    connector_run_id: str,
    idempotency_key_hash: str,
    operator_id: str,
    payload: ApifyFacebookStartRequest,
    actor: Dict[str, object],
) -> Dict[str, object]:
    month_start = _utc_now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
    SET caseNode.apifyRunReservationLockAt = datetime()
    CALL {
      WITH caseNode
      OPTIONAL MATCH (caseNode)-[:HAS_CONNECTOR_RUN]->(active:InvestigationConnectorRun)
      WHERE active.connector = 'apify' AND active.platform = 'facebook'
        AND active.status IN ['starting', 'start-unknown', 'running', 'ready-to-import', 'importing']
      RETURN count(active) AS activeCount
    }
    CALL {
      WITH caseNode
      OPTIONAL MATCH (caseNode)-[:HAS_CONNECTOR_RUN]->(monthly:InvestigationConnectorRun)
      WHERE monthly.connector = 'apify' AND monthly.platform = 'facebook'
        AND monthly.startedAt >= datetime($monthStart)
      RETURN coalesce(sum(monthly.requestedCostCapUsd), 0.0) AS monthlyReserved
    }
    WITH caseNode, activeCount, monthlyReserved
    WHERE activeCount = 0 AND monthlyReserved + $requestedCostCapUsd <= $monthlyBudgetUsd
    CREATE (run:InvestigationConnectorRun {
      connectorRunId: $connectorRunId, caseId: $caseId,
      connector: 'apify', platform: 'facebook', status: 'starting',
      actorId: $actorId, actorName: $actorName, actorUrl: $actorUrl,
      actorSchemaVersion: $actorSchemaVersion,
      operatorId: $operatorId, groupUrls: $groupUrls,
      maxItems: $maxItems, requestedCostCapUsd: $requestedCostCapUsd,
      monthlyBudgetUsd: $monthlyBudgetUsd,
      monthlyReservedAtStartUsd: monthlyReserved + $requestedCostCapUsd,
      onlyPostsNewerThan: $onlyPostsNewerThan,
      includeTopComments: $includeTopComments,
      promotePostsToGraph: $promotePostsToGraph,
      lawfulBasis: $lawfulBasis, investigationPurpose: $investigationPurpose,
      retentionDays: $retentionDays,
      idempotencyKeyHash: $idempotencyKeyHash,
      createdAt: datetime(), startedAt: datetime(), updatedAt: datetime()
    })
    MERGE (caseNode)-[:HAS_CONNECTOR_RUN]->(run)
    RETURN properties(run) AS run
    """
    params = {
        "caseId": case_id,
        "connectorRunId": connector_run_id,
        "idempotencyKeyHash": idempotency_key_hash,
        "operatorId": operator_id,
        "actorId": actor.get("actorId"),
        "actorName": actor.get("name"),
        "actorUrl": actor.get("url"),
        "actorSchemaVersion": actor.get("schemaVersion"),
        "groupUrls": payload.group_urls,
        "maxItems": payload.max_items,
        "requestedCostCapUsd": round(payload.max_total_charge_usd, 2),
        "monthlyBudgetUsd": _monthly_budget_usd(),
        "monthStart": month_start.isoformat(),
        "onlyPostsNewerThan": payload.only_posts_newer_than or "",
        "includeTopComments": payload.include_top_comments,
        "promotePostsToGraph": payload.promote_posts_to_graph,
        "lawfulBasis": payload.lawful_basis,
        "investigationPurpose": payload.investigation_purpose,
        "retentionDays": payload.retention_days,
    }
    with _db_session(get_driver()) as session:
        records = _execute_write(session, query, params)
    if records:
        return dict(records[0].get("run") or {})
    current = _list_connector_runs(case_id, limit=100)
    active = next(
        (
            row
            for row in current
            if row.get("status")
            in {"starting", "start-unknown", "running", "ready-to-import", "importing"}
        ),
        None,
    )
    if active:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "APIFY_CASE_RUN_ALREADY_ACTIVE",
                "message": "Only one managed Apify run can be active for a case.",
                "connectorRunId": active.get("connectorRunId"),
                "retryable": True,
            },
        )
    raise HTTPException(
        status_code=409,
        detail={
            "code": "APIFY_MONTHLY_BUDGET_RESERVED",
            "message": "The managed-run request would exceed the configured monthly project budget.",
            "monthlyProjectBudgetUsd": _monthly_budget_usd(),
            "retryable": False,
        },
    )


def _set_connector_run_fields(connector_run_id: str, fields: Dict[str, object]) -> None:
    query = """
    MATCH (run:InvestigationConnectorRun {connectorRunId: $connectorRunId})
    SET run += $fields, run.updatedAt = datetime()
    """
    with _db_session(get_driver()) as session:
        _execute_write(
            session,
            query,
            {"connectorRunId": connector_run_id, "fields": fields},
        )


def _start_apify_actor(
    actor: Dict[str, object], payload: ApifyFacebookStartRequest
) -> Tuple[Dict[str, Any], Dict[str, object]]:
    actor_details = _actor_details(actor)
    actor_input: Dict[str, object] = {
        "startUrls": [{"url": url} for url in payload.group_urls],
        "resultsLimit": payload.max_items,
        "viewOption": "CHRONOLOGICAL",
    }
    if payload.only_posts_newer_than:
        actor_input["onlyPostsNewerThan"] = payload.only_posts_newer_than
    try:
        response = requests.post(
            f"{APIFY_API_BASE}/actors/{actor['actorId']}/runs",
            headers={**_apify_headers(), "Content-Type": "application/json"},
            params={
                "maxItems": payload.max_items,
                "maxTotalChargeUsd": round(payload.max_total_charge_usd, 2),
                "restartOnError": "false",
            },
            json=actor_input,
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
    except requests.Timeout as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "APIFY_START_OUTCOME_UNKNOWN",
                "message": "The start request timed out; check Apify Console before retrying.",
                "retryable": False,
            },
        ) from exc
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail=_apify_error_detail(
                "APIFY_START_FAILED",
                "Apify rejected or could not process the capped run start.",
                retryable=True,
            ),
        ) from exc
    run_data = (result or {}).get("data") if isinstance(result, dict) else None
    if not isinstance(run_data, dict) or not run_data.get("id"):
        raise HTTPException(
            status_code=502,
            detail=_apify_error_detail(
                "APIFY_START_RESPONSE_INVALID",
                "Apify returned invalid run metadata after start.",
                retryable=False,
            ),
        )
    if str(run_data.get("actId") or "") != str(actor_details.get("resolvedActorId") or ""):
        raise HTTPException(
            status_code=502,
            detail=_apify_error_detail(
                "APIFY_STARTED_ACTOR_MISMATCH",
                "Apify started a run for an unexpected Actor.",
                retryable=False,
            ),
        )
    return run_data, actor_details


def _external_connector_status(run_status: str) -> str:
    normalized = str(run_status or "").upper()
    if normalized == "SUCCEEDED":
        return "ready-to-import"
    if normalized in APIFY_ACTIVE_STATUSES:
        return "running"
    if normalized in {"FAILED", "ABORTED", "TIMED-OUT"}:
        return "failed"
    return "running"


def _record_external_run(
    connector_run_id: str,
    run_data: Dict[str, Any],
    *,
    actor_details: Optional[Dict[str, object]] = None,
) -> None:
    provenance = _run_provenance(run_data)
    connector_status = _external_connector_status(str(provenance.get("runStatus") or ""))
    fields: Dict[str, object] = {
        "status": connector_status,
        "externalRunId": str(run_data.get("id") or ""),
        "externalDatasetId": str(run_data.get("defaultDatasetId") or ""),
        "externalRunStatus": provenance.get("runStatus") or "",
        "externalStatusMessage": provenance.get("statusMessage") or "",
        "resolvedActorId": (actor_details or {}).get("resolvedActorId")
        or provenance.get("resolvedActorId")
        or "",
        "actorBuildId": provenance.get("actorBuildId") or "",
        "actorBuildNumber": provenance.get("actorBuildNumber") or "",
        "pricingModel": provenance.get("pricingModel") or "",
        "usageTotalUsd": float(provenance.get("usageTotalUsd") or 0.0),
        "chargedItemCount": int(provenance.get("chargedItemCount") or 0),
        "chargedEventCountsJson": _safe_json(provenance.get("chargedEventCounts") or {}),
        "lastCheckedAt": _utc_now().isoformat(),
    }
    if connector_status == "failed":
        fields.update(
            {
                "errorCode": "APIFY_RUN_FAILED",
                "errorMessage": f"Apify run ended with {provenance.get('runStatus') or 'UNKNOWN'}.",
                "errorAt": _utc_now().isoformat(),
                "completedAt": _utc_now().isoformat(),
            }
        )
    _set_connector_run_fields(connector_run_id, fields)


def _refresh_connector_run(case_id: str, connector_run_id: str) -> Dict[str, object]:
    run = _load_connector_run(case_id, connector_run_id)
    if str(run.get("status") or "") == "completed":
        return _connector_run_contract(run)
    external_run_id = str(run.get("externalRunId") or "")
    if not external_run_id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "APIFY_EXTERNAL_RUN_UNKNOWN",
                "message": "The connector run has no verified Apify run ID.",
                "retryable": False,
            },
        )
    actor = _resolve_actor(run.get("actorId"))
    run_data = _fetch_run_data(external_run_id)
    actor_details = _verify_actor_identity(actor, run_data.get("actId"))
    _record_external_run(connector_run_id, run_data, actor_details=actor_details)
    run_status = str(run_data.get("status") or "").upper()
    if run_status != "SUCCEEDED":
        return _connector_run_contract(_load_connector_run(case_id, connector_run_id))
    _set_connector_run_fields(connector_run_id, {"status": "importing"})
    import_payload = ApifyFacebookImportRequest.model_validate(
        {
            "actorId": run.get("actorId"),
            "runId": external_run_id,
            "maxItems": int(run.get("maxItems") or 100),
            "includeTopComments": bool(run.get("includeTopComments", True)),
            "promotePostsToGraph": bool(run.get("promotePostsToGraph", True)),
            "lawfulBasis": run.get("lawfulBasis"),
            "investigationPurpose": run.get("investigationPurpose"),
            "retentionDays": int(run.get("retentionDays") or 180),
        }
    )
    try:
        graph = _execute_apify_facebook_import(case_id, import_payload)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        _set_connector_run_fields(
            connector_run_id,
            {
                "status": "import-failed",
                "errorCode": detail.get("code") or "APIFY_IMPORT_FAILED",
                "errorMessage": _excerpt(detail.get("message"), 1000),
                "errorAt": _utc_now().isoformat(),
            },
        )
        raise
    import_result = dict(graph.get("importResult") or {})
    _set_connector_run_fields(
        connector_run_id,
        {
            "status": "completed",
            "importRunId": import_result.get("runId") or "",
            "sourceId": import_result.get("sourceId") or "",
            "acceptedItemCount": int(import_result.get("itemsAccepted") or 0),
            "rejectedItemCount": int(import_result.get("itemsRejected") or 0),
            "duplicateItemCount": int(import_result.get("duplicateItems") or 0),
            "datasetTruncated": bool(import_result.get("truncated")),
            "errorCode": "",
            "errorMessage": "",
            "completedAt": _utc_now().isoformat(),
            "lastCheckedAt": _utc_now().isoformat(),
        },
    )
    return _connector_run_contract(_load_connector_run(case_id, connector_run_id))


def _refresh_connector_run_background(case_id: str, connector_run_id: str) -> None:
    try:
        _refresh_connector_run(case_id, connector_run_id)
    except Exception as exc:
        _set_connector_run_fields(
            connector_run_id,
            {
                "status": "import-failed",
                "errorCode": "APIFY_BACKGROUND_REFRESH_FAILED",
                "errorMessage": _excerpt(exc, 1000),
                "errorAt": _utc_now().isoformat(),
            },
        )


@router.post(
    "/cases/{case_id}/social/apify-facebook/runs",
    status_code=status.HTTP_202_ACCEPTED,
)
def start_apify_facebook_run(
    case_id: str,
    payload: ApifyFacebookStartRequest,
    idempotency_key: str = Header(min_length=12, max_length=200, alias="Idempotency-Key"),
    operator_id: str = Header(min_length=2, max_length=160, alias="X-FS-Operator-Id"),
):
    if not _managed_starts_enabled():
        raise HTTPException(
            status_code=403,
            detail={
                "code": "APIFY_MANAGED_START_DISABLED",
                "message": "Managed Apify run starts are disabled; import an existing run or dataset.",
                "retryable": False,
            },
        )
    if not _imports_enabled():
        raise HTTPException(status_code=503, detail="Apify Facebook connector is disabled")
    _case_and_report_for_graph(case_id)
    _authorize_managed_operation(case_id, operator_id)
    actor = _resolve_actor(payload.actor_id, for_start=True)
    maximum_charge = _maximum_run_charge_usd()
    if payload.max_total_charge_usd > maximum_charge:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "APIFY_RUN_CAP_TOO_HIGH",
                "message": "maxTotalChargeUsd exceeds the configured per-run cap.",
                "configuredMaximumUsd": maximum_charge,
                "retryable": False,
            },
        )
    idempotency_hash = _record_checksum(idempotency_key)
    connector_run_id = _investigation_id(
        "connector-run", case_id, APIFY_CONNECTOR_ID, idempotency_hash
    )
    try:
        existing = _load_connector_run(case_id, connector_run_id)
        return _connector_run_contract(existing)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
    _reserve_connector_run(
        case_id=case_id,
        connector_run_id=connector_run_id,
        idempotency_key_hash=idempotency_hash,
        operator_id=operator_id,
        payload=payload,
        actor=actor,
    )
    try:
        run_data, actor_details = _start_apify_actor(actor, payload)
        _record_external_run(connector_run_id, run_data, actor_details=actor_details)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        uncertain = detail.get("code") == "APIFY_START_OUTCOME_UNKNOWN"
        _set_connector_run_fields(
            connector_run_id,
            {
                "status": "start-unknown" if uncertain else "start-failed",
                "errorCode": detail.get("code") or "APIFY_START_FAILED",
                "errorMessage": _excerpt(detail.get("message"), 1000),
                "errorAt": _utc_now().isoformat(),
                "completedAt": "" if uncertain else _utc_now().isoformat(),
            },
        )
        raise
    return _connector_run_contract(_load_connector_run(case_id, connector_run_id))


@router.get("/cases/{case_id}/social/apify-facebook/runs")
def list_apify_facebook_runs(
    case_id: str, limit: int = Query(default=50, ge=1, le=200)
):
    return {"caseId": case_id, "runs": _list_connector_runs(case_id, limit)}


@router.get("/cases/{case_id}/social/apify-facebook/runs/{connector_run_id}")
def get_apify_facebook_run(case_id: str, connector_run_id: str):
    return _connector_run_contract(_load_connector_run(case_id, connector_run_id))


@router.post("/cases/{case_id}/social/apify-facebook/runs/{connector_run_id}/refresh")
def refresh_apify_facebook_run(
    case_id: str,
    connector_run_id: str,
    operator_id: str = Header(min_length=2, max_length=160, alias="X-FS-Operator-Id"),
):
    _authorize_managed_operation(case_id, operator_id)
    return _refresh_connector_run(case_id, connector_run_id)


def _claim_webhook_dispatch(dispatch_id: str, external_run_id: str) -> bool:
    marker = uuid.uuid4().hex
    query = """
    MERGE (dispatch:InvestigationWebhookDispatch {dispatchId: $dispatchId})
    ON CREATE SET dispatch.createdAt = datetime(), dispatch.creationMarker = $marker,
                  dispatch.externalRunId = $externalRunId, dispatch.connector = 'apify'
    SET dispatch.lastSeenAt = datetime(),
        dispatch.deliveryCount = coalesce(dispatch.deliveryCount, 0) + 1
    RETURN dispatch.creationMarker = $marker AS claimed
    """
    with _db_session(get_driver()) as session:
        records = _execute_write(
            session,
            query,
            {"dispatchId": dispatch_id, "externalRunId": external_run_id, "marker": marker},
        )
    return bool(records and records[0].get("claimed"))


def _find_connector_run_by_external_id(external_run_id: str) -> Tuple[str, str]:
    query = """
    MATCH (caseNode:DueDiligenceCase)-[:HAS_CONNECTOR_RUN]->
          (run:InvestigationConnectorRun {externalRunId: $externalRunId})
    RETURN caseNode.caseId AS caseId, run.connectorRunId AS connectorRunId
    LIMIT 1
    """
    with _db_session(get_driver()) as session:
        records = _execute_read(session, query, {"externalRunId": external_run_id})
    if not records:
        raise HTTPException(status_code=404, detail="Managed connector run not found")
    return str(records[0].get("caseId") or ""), str(records[0].get("connectorRunId") or "")


@router.post(
    "/connectors/apify-facebook/webhooks/run",
    status_code=status.HTTP_202_ACCEPTED,
)
def receive_apify_facebook_webhook(
    payload: ApifyWebhookPayload,
    background_tasks: BackgroundTasks,
    request: Request,
    webhook_secret: str = Header(min_length=16, alias="X-FS-Apify-Webhook-Secret"),
):
    configured_secret = str(os.getenv("FS_APIFY_FACEBOOK_WEBHOOK_SECRET", "")).strip()
    if not configured_secret:
        raise HTTPException(status_code=503, detail="Apify webhook secret is not configured")
    if not secrets.compare_digest(webhook_secret, configured_secret):
        raise HTTPException(status_code=401, detail="Invalid Apify webhook secret")
    dispatch_id = str(request.headers.get("X-Apify-Webhook-Dispatch-Id") or "").strip()
    if not dispatch_id:
        raise HTTPException(status_code=400, detail="Missing X-Apify-Webhook-Dispatch-Id")
    event_type = payload.event_type.upper()
    if event_type not in {
        "ACTOR.RUN.SUCCEEDED",
        "ACTOR.RUN.FAILED",
        "ACTOR.RUN.ABORTED",
        "ACTOR.RUN.TIMED_OUT",
    }:
        raise HTTPException(status_code=422, detail="Unsupported Apify webhook eventType")
    external_run_id = str(
        payload.event_data.get("actorRunId")
        or payload.resource.get("id")
        or ""
    ).strip()
    if not external_run_id:
        raise HTTPException(status_code=422, detail="Webhook does not identify an Actor run")
    case_id, connector_run_id = _find_connector_run_by_external_id(external_run_id)
    claimed = _claim_webhook_dispatch(dispatch_id, external_run_id)
    if claimed:
        background_tasks.add_task(
            _refresh_connector_run_background, case_id, connector_run_id
        )
    return {
        "accepted": True,
        "duplicate": not claimed,
        "dispatchId": dispatch_id,
        "connectorRunId": connector_run_id,
        "verification": "Run state will be fetched from Apify; webhook body is not trusted.",
    }


def _expired_social_counts(case_id: str, now: str) -> Dict[str, int]:
    queries = {
        "evidence": """
          MATCH (:DueDiligenceCase {caseId: $caseId})-[:USES_INVESTIGATION_EVIDENCE]->
                (e:InvestigationEvidence)-[:FROM_SOURCE]->(s:InvestigationDataSource)
          WHERE s.connector = 'apify' AND e.platform = 'facebook'
            AND e.retentionExpiresAt IS NOT NULL
            AND datetime(e.retentionExpiresAt) <= datetime($now)
          RETURN count(DISTINCT e) AS count
        """,
        "statements": """
          MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_STATEMENT]->
                (st:InvestigationStatement)-[:SUPPORTED_BY]->(e:InvestigationEvidence)
          MATCH (e)-[:FROM_SOURCE]->(s:InvestigationDataSource)
          WHERE s.connector = 'apify' AND e.platform = 'facebook'
            AND e.retentionExpiresAt IS NOT NULL
            AND datetime(e.retentionExpiresAt) <= datetime($now)
          RETURN count(DISTINCT st) AS count
        """,
        "relationships": """
          MATCH (a:InvestigationEntity)-[rel:INVESTIGATION_LINK {caseId: $caseId}]-(b)
          WHERE rel.platform = 'facebook' AND rel.retentionExpiresAt IS NOT NULL
            AND datetime(rel.retentionExpiresAt) <= datetime($now)
          RETURN count(DISTINCT rel) AS count
        """,
        "entities": """
          MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_ENTITY]->
                (entity:InvestigationEntity {platform: 'facebook'})
          WHERE entity.retentionExpiresAt IS NOT NULL
            AND datetime(entity.retentionExpiresAt) <= datetime($now)
          RETURN count(DISTINCT entity) AS count
        """,
    }
    output: Dict[str, int] = {}
    with _db_session(get_driver()) as session:
        for key, query in queries.items():
            records = _execute_read(session, query, {"caseId": case_id, "now": now})
            output[key] = int(records[0].get("count") or 0) if records else 0
    return output


def _delete_expired_social_content(case_id: str, now: str) -> Dict[str, int]:
    expired_ids_query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})-[:USES_INVESTIGATION_EVIDENCE]->
          (e:InvestigationEvidence)-[:FROM_SOURCE]->(s:InvestigationDataSource)
    WHERE s.connector = 'apify' AND e.platform = 'facebook'
      AND e.retentionExpiresAt IS NOT NULL
      AND datetime(e.retentionExpiresAt) <= datetime($now)
    RETURN collect(DISTINCT e.evidenceId) AS evidenceIds
    """
    with _db_session(get_driver()) as session:
        records = _execute_read(
            session, expired_ids_query, {"caseId": case_id, "now": now}
        )
        evidence_ids = list(records[0].get("evidenceIds") or []) if records else []
        if not evidence_ids:
            return {"evidence": 0, "statements": 0, "relationships": 0, "entities": 0}
        params = {"caseId": case_id, "now": now, "evidenceIds": evidence_ids}
        statements = _execute_write(
            session,
            """
            MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_STATEMENT]->
                  (statement:InvestigationStatement)
            WHERE statement.evidenceId IN $evidenceIds
            WITH collect(DISTINCT statement) AS rows
            FOREACH (row IN rows | DETACH DELETE row)
            RETURN size(rows) AS count
            """,
            params,
        )
        relationships = _execute_write(
            session,
            """
            MATCH (:InvestigationEntity)-[rel:INVESTIGATION_LINK {caseId: $caseId}]-(:InvestigationEntity)
            WHERE any(evidenceId IN coalesce(rel.evidenceIds, []) WHERE evidenceId IN $evidenceIds)
              AND all(evidenceId IN coalesce(rel.evidenceIds, []) WHERE evidenceId IN $evidenceIds)
            WITH collect(DISTINCT rel) AS rows
            FOREACH (row IN rows | DELETE row)
            RETURN size(rows) AS count
            """,
            params,
        )
        _execute_write(
            session,
            """
            MATCH (entity:InvestigationEntity)-[link:HAS_INVESTIGATION_NAME {caseId: $caseId}]->()
            WHERE any(evidenceId IN coalesce(link.evidenceIds, []) WHERE evidenceId IN $evidenceIds)
              AND all(evidenceId IN coalesce(link.evidenceIds, []) WHERE evidenceId IN $evidenceIds)
            DELETE link
            """,
            params,
        )
        _execute_write(
            session,
            """
            MATCH (entity:InvestigationEntity)-[link:HAS_MATCH_VALUE {caseId: $caseId}]->()
            WHERE any(evidenceId IN coalesce(link.evidenceIds, []) WHERE evidenceId IN $evidenceIds)
              AND all(evidenceId IN coalesce(link.evidenceIds, []) WHERE evidenceId IN $evidenceIds)
            DELETE link
            """,
            params,
        )
        entities = _execute_write(
            session,
            """
            MATCH (caseNode:DueDiligenceCase {caseId: $caseId})-[caseLink:HAS_INVESTIGATION_ENTITY]->
                  (entity:InvestigationEntity {platform: 'facebook'})
            WHERE entity.retentionExpiresAt IS NOT NULL
              AND datetime(entity.retentionExpiresAt) <= datetime($now)
              AND NOT (entity)-[:HAS_STATEMENT]->(:InvestigationStatement {caseId: $caseId})
              AND NOT (entity)-[:INVESTIGATION_LINK {caseId: $caseId}]-()
            WITH collect(caseLink) AS rows
            FOREACH (row IN rows | DELETE row)
            RETURN size(rows) AS count
            """,
            params,
        )
        evidence = _execute_write(
            session,
            """
            MATCH (caseNode:DueDiligenceCase {caseId: $caseId})-
                  [caseLink:USES_INVESTIGATION_EVIDENCE]->(e:InvestigationEvidence)
            WHERE e.evidenceId IN $evidenceIds
            DELETE caseLink
            RETURN count(DISTINCT e) AS count
            """,
            params,
        )
        _execute_write(
            session,
            """
            MATCH (e:InvestigationEvidence)
            WHERE e.evidenceId IN $evidenceIds
              AND NOT (:DueDiligenceCase)-[:USES_INVESTIGATION_EVIDENCE]->(e)
            DETACH DELETE e
            """,
            params,
        )
        _execute_write(
            session,
            """
            MATCH (entity:InvestigationEntity {platform: 'facebook'})
            WHERE NOT (:DueDiligenceCase)-[:HAS_INVESTIGATION_ENTITY]->(entity)
            DETACH DELETE entity
            """,
            params,
        )
        _execute_write(
            session,
            """
            MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_IMPORT_RUN]->
                  (run:InvestigationImportRun {connector: 'apify', platform: 'facebook'})
            WHERE run.retentionExpiresAt IS NOT NULL
              AND run.retentionExpiresAt <= datetime($now)
            SET run.contentExpiredAt = datetime($now),
                run.retentionStatus = 'source-content-removed'
            """,
            params,
        )
    return {
        "evidence": int(evidence[0].get("count") or 0) if evidence else 0,
        "statements": int(statements[0].get("count") or 0) if statements else 0,
        "relationships": int(relationships[0].get("count") or 0) if relationships else 0,
        "entities": int(entities[0].get("count") or 0) if entities else 0,
    }


@router.post("/cases/{case_id}/social/retention/cleanup")
def cleanup_expired_social_content(
    case_id: str,
    payload: ApifyRetentionCleanupRequest,
    operator_id: str = Header(min_length=2, max_length=160, alias="X-FS-Operator-Id"),
):
    _case_and_report_for_graph(case_id)
    _authorize_managed_operation(case_id, operator_id)
    now = _utc_now().isoformat()
    candidates = _expired_social_counts(case_id, now)
    if payload.dry_run:
        return {
            "caseId": case_id,
            "dryRun": True,
            "evaluatedAt": now,
            "candidates": candidates,
            "deleted": {key: 0 for key in candidates},
            "auditPreserved": ["source metadata", "import run metadata", "checksums/fingerprints"],
        }
    if not _env_flag("FS_APIFY_FACEBOOK_RETENTION_DELETE_ENABLED", False):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "APIFY_RETENTION_DELETE_DISABLED",
                "message": "Retention deletion requires FS_APIFY_FACEBOOK_RETENTION_DELETE_ENABLED=1.",
                "retryable": False,
            },
        )
    deleted = _delete_expired_social_content(case_id, now)
    return {
        "caseId": case_id,
        "dryRun": False,
        "evaluatedAt": now,
        "candidates": candidates,
        "deleted": deleted,
        "auditPreserved": ["source metadata", "import run metadata", "checksums/fingerprints"],
    }
