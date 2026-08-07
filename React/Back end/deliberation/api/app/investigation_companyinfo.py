import hashlib
import hmac
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote, urlsplit

import requests
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .db import get_driver
from .routes_due_diligence import (
    _build_investigation_graph_bundle,
    _case_and_report_for_graph,
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

COMPANYINFO_API_BASE = "https://api.companyinfo.ge/api"
COMPANYINFO_PUBLIC_URL = "https://companyinfo.ge/ka"
NAPR_SEARCH_URL = "https://enreg.reestri.gov.ge/main.php?m=new_index"
COMPANYINFO_SOURCE_NAME = "Companyinfo.ge corporate registry mirror"
NAPR_SOURCE_NAME = "Georgian National Agency of Public Registry (NAPR)"
COMPANYINFO_CAVEAT = (
    "Secondary source derived from NAPR and described as updating monthly. "
    "Verify material facts and source documents against NAPR."
)

_RATE_LOCK = threading.Lock()
_LAST_REQUEST_MONOTONIC = 0.0


class CompanyInfoEnrichmentRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    identification_code: str = Field(alias="identificationCode")
    force_refresh: bool = Field(default=False, alias="forceRefresh")

    @field_validator("identification_code")
    @classmethod
    def validate_identification_code(cls, value: str) -> str:
        digits = re.sub(r"\D", "", value or "")
        if not re.fullmatch(r"\d{9,11}", digits):
            raise ValueError("identificationCode must contain 9 to 11 digits")
        return digits


class NaprVerificationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str
    official_url: str = Field(alias="officialUrl")
    source_document_url: Optional[str] = Field(default=None, alias="sourceDocumentUrl")
    registration_number: Optional[str] = Field(default=None, alias="registrationNumber")
    verified_at: Optional[str] = Field(default=None, alias="verifiedAt")
    verified_by: str = Field(min_length=1, max_length=200, alias="verifiedBy")
    notes: str = Field(min_length=1, max_length=4000)
    compared_fields: Dict[str, str] = Field(default_factory=dict, alias="comparedFields")

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        clean = value.strip().casefold()
        if clean not in {"verified", "mismatch", "not-found", "inconclusive"}:
            raise ValueError("status must be verified, mismatch, not-found, or inconclusive")
        return clean

    @field_validator("official_url", "source_document_url")
    @classmethod
    def validate_napr_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        parsed = urlsplit(value.strip())
        if parsed.scheme != "https" or parsed.hostname != "enreg.reestri.gov.ge":
            raise ValueError("NAPR URLs must use https://enreg.reestri.gov.ge")
        return value.strip()

    @field_validator("compared_fields")
    @classmethod
    def validate_compared_fields(cls, value: Dict[str, str]) -> Dict[str, str]:
        output: Dict[str, str] = {}
        for key, state in value.items():
            clean_state = str(state or "").strip().casefold()
            if clean_state not in {"match", "mismatch", "not-checked"}:
                raise ValueError("comparedFields values must be match, mismatch, or not-checked")
            output[str(key)[:100]] = clean_state
        return output


class CompanyInfoAdapterError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 502,
        retry_after_seconds: Optional[int] = None,
        error_type: str = "upstream-error",
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        self.error_type = error_type


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _payload_hash(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(value: object, limit: int = 4000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _norm_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _as_dict(value: object) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    for key in ("data", "result", "company", "corporation"):
        nested = value.get(key)
        if isinstance(nested, dict):
            merged = dict(value)
            merged.update(nested)
            return merged
        if isinstance(nested, list) and nested and isinstance(nested[0], dict):
            merged = dict(value)
            merged.update(nested[0])
            return merged
    return dict(value)


def _get(mapping: object, *keys: str) -> object:
    if not isinstance(mapping, dict):
        return None
    normalized = {_norm_key(key): value for key, value in mapping.items()}
    for key in keys:
        value = normalized.get(_norm_key(key))
        if value not in (None, ""):
            return value
    return None


def _walk_dicts(value: object) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_dicts(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_dicts(nested)


def _collect_lists(payload: object, *keys: str) -> List[Dict[str, Any]]:
    target_keys = {_norm_key(key) for key in keys}
    output: List[Dict[str, Any]] = []
    seen = set()
    for row in _walk_dicts(payload):
        for key, value in row.items():
            if _norm_key(key) not in target_keys or not isinstance(value, list):
                continue
            for item in value:
                if not isinstance(item, dict):
                    continue
                signature = _payload_hash(item)
                if signature not in seen:
                    seen.add(signature)
                    output.append(item)
    return output


def _find_value(payload: object, *keys: str) -> Tuple[bool, object]:
    targets = {_norm_key(key) for key in keys}
    for row in _walk_dicts(payload):
        for key, value in row.items():
            if _norm_key(key) in targets:
                return True, value
    return False, None


def _safe_float(value: object) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("%", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def _first(*values: object) -> str:
    for value in values:
        clean = _text(value)
        if clean:
            return clean
    return ""


def _personal_identity_hash(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    key = os.getenv("FS_DD_ID_HASH_KEY", "").strip()
    if not digits or not key:
        return ""
    digest = hmac.new(key.encode("utf-8"), digits.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"hmac-sha256:{digest}"


def _companyinfo_config() -> Dict[str, object]:
    def number(name: str, default: float, minimum: float, maximum: float) -> float:
        try:
            value = float(os.getenv(name, str(default)))
        except ValueError:
            value = default
        return max(minimum, min(value, maximum))

    return {
        "enabled": os.getenv("FS_COMPANYINFO_ENABLED", "0").strip() == "1",
        "permissionAcknowledged": os.getenv(
            "FS_COMPANYINFO_PERMISSION_ACKNOWLEDGED", "0"
        ).strip()
        == "1",
        "timeoutSeconds": number("FS_COMPANYINFO_TIMEOUT_SECONDS", 12.0, 3.0, 30.0),
        "retries": int(number("FS_COMPANYINFO_RETRIES", 2, 0, 4)),
        "backoffSeconds": number("FS_COMPANYINFO_BACKOFF_SECONDS", 0.75, 0.1, 5.0),
        "minimumIntervalSeconds": number(
            "FS_COMPANYINFO_MIN_INTERVAL_SECONDS", 1.0, 0.25, 10.0
        ),
        "cacheHours": int(number("FS_COMPANYINFO_CACHE_HOURS", 24, 1, 720)),
    }


def _wait_for_rate_limit(minimum_interval: float) -> None:
    global _LAST_REQUEST_MONOTONIC
    with _RATE_LOCK:
        now = time.monotonic()
        wait_seconds = minimum_interval - (now - _LAST_REQUEST_MONOTONIC)
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        _LAST_REQUEST_MONOTONIC = time.monotonic()


def _companyinfo_get(path: str) -> object:
    config = _companyinfo_config()
    if not config["enabled"] or not config["permissionAcknowledged"]:
        raise CompanyInfoAdapterError(
            "Companyinfo connector is disabled until reuse permission/terms are acknowledged",
            status_code=403,
            error_type="permission-required",
        )
    url = f"{COMPANYINFO_API_BASE}/{path.lstrip('/')}"
    last_error: Optional[Exception] = None
    for attempt in range(int(config["retries"]) + 1):
        _wait_for_rate_limit(float(config["minimumIntervalSeconds"]))
        try:
            response = requests.get(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "FreedomSquare-DD/1.0 (low-volume public-source research)",
                },
                timeout=float(config["timeoutSeconds"]),
            )
            if response.status_code == 404:
                raise CompanyInfoAdapterError(
                    "Companyinfo record not found",
                    status_code=404,
                    error_type="not-found",
                )
            if response.status_code in {401, 403}:
                raise CompanyInfoAdapterError(
                    "Companyinfo access is not permitted by the upstream interface",
                    status_code=403,
                    error_type="permission-denied",
                )
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After") or 60)
                if attempt < int(config["retries"]):
                    time.sleep(min(retry_after, 10))
                    continue
                raise CompanyInfoAdapterError(
                    "Companyinfo rate limit reached",
                    status_code=429,
                    retry_after_seconds=retry_after,
                    error_type="rate-limited",
                )
            if response.status_code >= 500:
                raise requests.HTTPError(f"Companyinfo returned HTTP {response.status_code}")
            response.raise_for_status()
            return response.json()
        except CompanyInfoAdapterError:
            raise
        except requests.Timeout as exc:
            last_error = exc
            if attempt >= int(config["retries"]):
                raise CompanyInfoAdapterError(
                    "Companyinfo request timed out",
                    status_code=504,
                    error_type="timeout",
                ) from exc
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt >= int(config["retries"]):
                raise CompanyInfoAdapterError(
                    "Companyinfo request failed",
                    status_code=502,
                    error_type="upstream-error",
                ) from exc
        time.sleep(float(config["backoffSeconds"]) * (2**attempt))
    raise CompanyInfoAdapterError(str(last_error or "Companyinfo request failed"))


def fetch_companyinfo_company(identification_code: str) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    errors: List[Dict[str, str]] = []
    encoded = quote(identification_code, safe="")
    try:
        primary = _companyinfo_get(f"getcorporation/{encoded}")
    except CompanyInfoAdapterError as exc:
        if exc.status_code != 404:
            raise
        primary = _companyinfo_get(f"company-info/{encoded}")
    merged = _as_dict(primary)
    if not merged:
        raise CompanyInfoAdapterError(
            "Companyinfo returned an empty company record",
            status_code=404,
            error_type="not-found",
        )
    try:
        company_info = _companyinfo_get(f"company-info/{encoded}")
        merged["companyInfo"] = company_info
    except CompanyInfoAdapterError as exc:
        if exc.status_code not in {404}:
            errors.append({"stage": "company-info", "type": exc.error_type, "message": str(exc)})
    internal_id = _first(_get(merged, "id", "companyId", "corporationId"))
    if internal_id:
        try:
            relationship_graph = _companyinfo_get(
                f"relationship-graph?companyId={quote(internal_id, safe='')}"
            )
            merged["relationshipGraph"] = relationship_graph
        except CompanyInfoAdapterError as exc:
            if exc.status_code not in {404}:
                errors.append(
                    {"stage": "relationship-graph", "type": exc.error_type, "message": str(exc)}
                )
    return merged, errors


INDICATOR_DEFINITIONS = [
    ("political-donations", "Political donations", ("donations", "politicalDonations")),
    ("asset-declarations", "Asset declarations/public-official affiliations", ("declarations", "publicOfficials", "publicOfficialAffiliations")),
    ("sanctions", "Sanctions records", ("sanctions", "sanctionRecords")),
    ("state-beneficiary", "State beneficiary records", ("stateBeneficiaries", "beneficiaries", "governmentBeneficiaries")),
    ("mining-licences", "Mining licences", ("miningLicenses", "miningLicences")),
    ("procurement-blacklist", "Procurement blacklist", ("procurementBlacklist", "blacklist")),
    ("procurement-warning", "Procurement warning list", ("procurementWarnings", "warningList")),
    ("construction-permits", "Construction permits", ("constructionPermits", "buildingPermits")),
    ("privatization", "Privatization records", ("privatization", "privatisation")),
    ("government-decrees", "Government decrees", ("governmentDecrees", "decrees")),
    ("fined-declarants", "Fined declarants", ("finedDeclarants",)),
]


def _parse_date(value: object) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _value_present(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        return value.strip().casefold() not in {"", "0", "false", "no", "none", "null"}
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return value is not None


def _extract_indicators(payload: Dict[str, Any], source_updated_at: str) -> List[Dict[str, object]]:
    updated = _parse_date(source_updated_at)
    stale = bool(updated and _utc_now() - updated > timedelta(days=62))
    indicators: List[Dict[str, object]] = []
    for indicator_id, label, keys in INDICATOR_DEFINITIONS:
        found, value = _find_value(payload, *keys)
        if not found:
            value_state = "unknown"
            status = "unknown"
            record_count = 0
        else:
            present = _value_present(value)
            value_state = "present" if present else "absent"
            status = "stale" if stale else value_state
            if isinstance(value, list):
                record_count = len(value)
            elif isinstance(value, dict):
                record_count = len(value)
            else:
                record_count = 1 if present else 0
        indicators.append(
            {
                "indicatorId": indicator_id,
                "label": label,
                "status": status,
                "valueState": value_state,
                "recordCount": record_count,
                "sourceUpdatedAt": source_updated_at,
                "authorityLevel": "secondary",
                "verificationStatus": "requires-source-review" if status in {"present", "stale"} else "source-stated",
                "caveat": "A secondary-source indicator is an investigative lead, not an adverse conclusion.",
            }
        )
    return indicators


def _apply_indicator_errors(
    normalized: Dict[str, object], errors: List[Dict[str, str]]
) -> None:
    company_info_errors = [row for row in errors if row.get("stage") == "company-info"]
    if not company_info_errors:
        return
    for indicator in normalized.get("indicators") or []:
        if indicator.get("status") != "unknown":
            continue
        indicator["status"] = "error"
        indicator["error"] = {
            "type": company_info_errors[0].get("type") or "partial-source-error",
            "message": company_info_errors[0].get("message") or "Indicator source was unavailable",
        }


def _extract_documents(payload: Dict[str, Any]) -> List[str]:
    output: List[str] = []
    for row in _walk_dicts(payload):
        for key, value in row.items():
            normalized = _norm_key(key)
            if not any(token in normalized for token in ("document", "source", "pdf", "filing")):
                continue
            values = value if isinstance(value, list) else [value]
            for item in values:
                if not isinstance(item, str):
                    continue
                parsed = urlsplit(item.strip())
                if parsed.scheme in {"http", "https"} and parsed.netloc and item not in output:
                    output.append(item[:2000])
    return output[:20]


def normalize_companyinfo_payload(
    payload: Dict[str, Any], identification_code: str
) -> Dict[str, object]:
    root = _as_dict(payload)
    company = {
        "internalId": _first(_get(root, "id", "companyId", "corporationId")),
        "identificationCode": _first(
            _get(root, "identificationCode", "idCode", "identification_code"),
            identification_code,
        ),
        "name": _first(_get(root, "name", "companyName", "corporationName", "legalName")),
        "legalForm": _first(_get(root, "legalForm", "legal_form", "form")),
        "status": _first(_get(root, "status", "companyStatus", "registrationStatus")),
        "registrationDate": _first(
            _get(root, "registrationDate", "registeredAt", "registered_at", "incorporationDate")
        ),
        "registrationNumber": _first(
            _get(root, "registrationNumber", "registrationNo", "regNumber"),
            identification_code,
        ),
        "address": _first(_get(root, "address", "legalAddress", "registeredAddress")),
        "email": _first(_get(root, "email", "companyEmail")),
        "sourceUpdatedAt": _first(
            _get(root, "updatedAt", "updateDate", "sourceUpdatedAt", "lastUpdated")
        ),
    }
    relationship_groups = [
        ("director", True, _collect_lists(payload, "directors", "currentDirectors")),
        ("director", False, _collect_lists(payload, "formerDirectors", "pastDirectors")),
        ("shareholder", True, _collect_lists(payload, "shareholders", "currentShareholders")),
        ("shareholder", False, _collect_lists(payload, "formerShareholders", "pastShareholders")),
        ("owner", True, _collect_lists(payload, "owners", "currentOwners", "beneficialOwners")),
        ("owner", False, _collect_lists(payload, "formerOwners", "pastOwners")),
        ("historical-affiliation", False, _collect_lists(payload, "history", "affiliations", "historicalAffiliations")),
        ("related-company", True, _collect_lists(payload, "relatedCompanies", "relatedCorporations")),
    ]
    relationships: List[Dict[str, object]] = []
    seen = set()
    for role_type, default_current, rows in relationship_groups:
        for row in rows:
            first_name = _get(row, "firstName", "firstname")
            last_name = _get(row, "lastName", "lastname", "surname")
            name = _first(
                _get(row, "name", "fullName", "personName", "companyName", "organizationName"),
                f"{_text(first_name)} {_text(last_name)}",
            )
            if not name:
                continue
            end_date = _first(_get(row, "endDate", "endedAt", "toDate", "validTo"))
            current_value = _get(row, "isCurrent", "current", "active")
            current = (
                bool(current_value)
                if isinstance(current_value, bool)
                else default_current and not end_date
            )
            personal_id = _get(
                row, "personalNumber", "personalId", "privateNumber", "idNumber", "identificationNumber"
            )
            relation = {
                "roleType": role_type,
                "name": name,
                "internalId": _first(_get(row, "id", "personId", "companyId", "corporationId")),
                "personalIdentityHash": _personal_identity_hash(personal_id),
                "companyIdentificationCode": (
                    _first(_get(row, "identificationCode", "idCode"))
                    if role_type == "related-company"
                    else ""
                ),
                "current": current,
                "role": _first(_get(row, "role", "position", "title"), role_type),
                "startDate": _first(_get(row, "startDate", "startedAt", "fromDate", "validFrom")),
                "endDate": end_date,
                "sharePercentage": _safe_float(
                    _get(row, "sharePercentage", "ownershipPercentage", "share", "percent")
                ),
                "sourceDocumentUrl": _first(
                    _get(row, "sourceDocumentUrl", "documentUrl", "pdfUrl", "sourceUrl")
                ),
            }
            signature = _payload_hash(
                {
                    key: value
                    for key, value in relation.items()
                    if key != "personalIdentityHash"
                }
            )
            if signature not in seen:
                seen.add(signature)
                relationships.append(relation)

    source_updated_at = str(company.get("sourceUpdatedAt") or "")
    return {
        "company": company,
        "relationships": relationships,
        "indicators": _extract_indicators(payload, source_updated_at),
        "sourceDocuments": _extract_documents(payload),
    }


def build_companyinfo_bundle(
    *,
    case_id: str,
    root_entity_id: str,
    normalized: Dict[str, object],
    payload_hash: str,
    fetched_at: str,
) -> Tuple[Dict[str, object], Dict[str, object]]:
    entities: Dict[str, Dict[str, object]] = {}
    relationships: Dict[str, Dict[str, object]] = {}
    sources: Dict[str, Dict[str, object]] = {}
    evidence: Dict[str, Dict[str, object]] = {}
    company = normalized["company"]
    identification_code = str(company.get("identificationCode") or "")
    company_url = f"{COMPANYINFO_PUBLIC_URL}/corporations/{company.get('internalId')}" if company.get("internalId") else COMPANYINFO_PUBLIC_URL
    companyinfo_source_id = _graph_source(
        sources,
        name=COMPANYINFO_SOURCE_NAME,
        url=COMPANYINFO_PUBLIC_URL,
        source_type="Secondary corporate registry aggregator",
        connector="companyinfo-ge",
        sourceOwner="Transparency International Georgia",
        authorityLevel="secondary",
        authorityTier=4,
        jurisdiction="GE",
        canonicalUrl=COMPANYINFO_PUBLIC_URL,
        termsUrl="",
        termsVersion="unverified",
        license="unverified",
        attribution="Companyinfo.ge / Transparency International Georgia; underlying NAPR records",
        accessMode="undocumented-api-low-volume",
        commercialUsePermission="unknown",
        redistributionPermission="unknown",
        allowedPurpose="Documented public-interest due-diligence investigation",
        allowedFields=["company", "officers", "shareholders", "history", "public-record indicators", "source documents"],
        retentionPolicy="Case-scoped sanitized snapshots; no raw personal identifiers",
        redactionPolicy="Personal identifiers omitted from API and raw storage",
        cursorStrategy="identification-code conditional refresh",
        updateCadence="monthly",
        freshnessSlaDays=62,
        freshnessCaveat=COMPANYINFO_CAVEAT,
        permissionState="undocumented-public-api-review-required",
        ingestionMode="identification-code-enrichment",
        parserVersion="companyinfo-ge-v1",
        mappingVersion="ftm-companyinfo-v1",
        correctionPolicy="Append a new snapshot and statements; never overwrite prior evidence",
        tombstoneSupport=True,
        killSwitch="FS_COMPANYINFO_ENABLED",
        lastAttemptAt=fetched_at,
        lastSuccessAt=fetched_at,
        sourceUpdatedAt=company.get("sourceUpdatedAt") or "",
        payloadHash=payload_hash,
    )
    _graph_source(
        sources,
        name=NAPR_SOURCE_NAME,
        url=NAPR_SEARCH_URL,
        source_type="Authoritative company registry",
        connector="napr-manual-verification",
        sourceOwner="National Agency of Public Registry",
        authorityLevel="authoritative",
        authorityTier=1,
        jurisdiction="GE",
        canonicalUrl=NAPR_SEARCH_URL,
        accessMode="analyst-verification",
        commercialUsePermission="unknown",
        redistributionPermission="source-link-only-unless-permitted",
        allowedPurpose="Selective authoritative verification",
        retentionPolicy="Store analyst verification and permitted source-document references",
        redactionPolicy="No personal identifiers in API responses",
        permissionState="manual-low-volume-only",
        ingestionMode="analyst-verification",
        automationEnabled=False,
        parserVersion="manual-verification-v1",
        mappingVersion="ftm-napr-verification-v1",
        killSwitch="automation-always-disabled",
        caveat="No documented JSON API; do not bypass CAPTCHA or access controls.",
    )
    evidence_id = _graph_evidence(
        evidence,
        source_id=companyinfo_source_id,
        source_name=COMPANYINFO_SOURCE_NAME,
        title=f"Companyinfo company record: {company.get('name') or identification_code}",
        source_url=company_url,
        evidence_type="Secondary corporate registry snapshot",
        published_at=company.get("sourceUpdatedAt") or "",
        note=COMPANYINFO_CAVEAT,
        identity=f"companyinfo|{identification_code}|{payload_hash}",
    )
    evidence[evidence_id].update(
        {
            "payloadHash": payload_hash,
            "fetchedAt": fetched_at,
            "sourceUpdatedAt": company.get("sourceUpdatedAt") or "",
            "authorityLevel": "secondary",
            "sourceRecordKey": identification_code,
            "parserVersion": "companyinfo-ge-v1",
            "mappingVersion": "ftm-companyinfo-v1",
            "retrievedAt": fetched_at,
            "evidenceHash": payload_hash,
        }
    )
    for indicator in normalized.get("indicators") or []:
        indicator.update(
            {
                "sourceId": companyinfo_source_id,
                "evidenceIds": [evidence_id],
                "sourceUrl": company_url,
                "fetchedAt": fetched_at,
            }
        )
    ftm_properties = {
        key: [value]
        for key, value in {
            "name": company.get("name"),
            "registrationNumber": company.get("registrationNumber") or identification_code,
            "incorporationDate": company.get("registrationDate"),
            "legalForm": company.get("legalForm"),
            "status": company.get("status"),
            "address": company.get("address"),
            "email": company.get("email"),
            "sourceUrl": company_url,
        }.items()
        if value not in (None, "")
    }
    indicator_properties = {
        f"indicator_{str(row['indicatorId']).replace('-', '_')}": row["status"]
        for row in normalized.get("indicators") or []
    }
    ftm_properties.update({key: [value] for key, value in indicator_properties.items()})
    company_entity_id = _graph_entity(
        entities,
        name=company.get("name") or f"Company {identification_code}",
        entity_type="Organization",
        identity=f"{companyinfo_source_id}|company|{identification_code}",
        entityRole="Companyinfo company record",
        sourceId=companyinfo_source_id,
        sourceExternalId=f"company:{identification_code}",
        identificationCode=identification_code,
        identifierIssuer="GE-NAPR",
        identifierJurisdiction="GE",
        identifierType="company-registration-number",
        registrationNumber=company.get("registrationNumber") or identification_code,
        legalForm=company.get("legalForm") or "",
        companyStatus=company.get("status") or "",
        registrationDate=company.get("registrationDate") or "",
        address=company.get("address") or "",
        email=company.get("email") or "",
        companyinfoInternalId=company.get("internalId") or "",
        sourceUrl=company_url,
        sourceAuthorityLevel="secondary",
        sourceUpdatedAt=company.get("sourceUpdatedAt") or "",
        companyInfoFetchedAt=fetched_at,
        payloadHash=payload_hash,
        evidenceIds=[evidence_id],
        enrichmentIndicatorsJson=_json(normalized.get("indicators") or []),
        sourceDocuments=list(normalized.get("sourceDocuments") or []),
        ftmSchema="Company",
        ftmPropertiesJson=_json(ftm_properties),
    )

    for relation in normalized.get("relationships") or []:
        role_type = str(relation.get("roleType") or "historical-affiliation")
        party_name = str(relation.get("name") or "")
        if not party_name:
            continue
        if role_type == "related-company":
            related_code = str(relation.get("companyIdentificationCode") or "")
            party_id = _graph_entity(
                entities,
                name=party_name,
                entity_type="Organization",
                identity=f"{companyinfo_source_id}|related-company|{related_code or party_name}",
                entityRole="Related company record",
                sourceId=companyinfo_source_id,
                sourceExternalId=f"related-company:{related_code or relation.get('internalId') or party_name}",
                identificationCode=related_code,
                identifierIssuer="GE-NAPR",
                identifierJurisdiction="GE",
                identifierType="company-registration-number",
                evidenceIds=[evidence_id],
                ftmSchema="Company",
                ftmPropertiesJson=_json(
                    {
                        "name": [party_name],
                        **({"registrationNumber": [related_code]} if related_code else {}),
                    }
                ),
            )
            from_id, to_id = company_entity_id, party_id
            label = "Related company"
            ftm_schema = "Association"
        else:
            internal_id = str(relation.get("internalId") or "")
            personal_hash = str(relation.get("personalIdentityHash") or "")
            identity = internal_id or personal_hash or f"{identification_code}|{role_type}|{party_name}"
            party_id = _graph_entity(
                entities,
                name=party_name,
                entity_type="Person",
                identity=f"{companyinfo_source_id}|person|{identity}",
                entityRole=_text(relation.get("role") or role_type, 100),
                sourceId=companyinfo_source_id,
                sourceExternalId=f"person:{internal_id}" if internal_id else "",
                evidenceIds=[evidence_id],
                ftmSchema="Person",
                ftmPropertiesJson=_json({"name": [party_name]}),
                personalIdentifiersExposed=False,
            )
            from_id, to_id = party_id, company_entity_id
            current = bool(relation.get("current"))
            if role_type == "director":
                label = "Director of" if current else "Former director of"
                ftm_schema = "Directorship"
            elif role_type in {"shareholder", "owner"}:
                base = "Shareholder of" if role_type == "shareholder" else "Owner of"
                label = base if current else f"Former {base.casefold()}"
                ftm_schema = "Ownership"
            else:
                label = "Historical affiliation"
                ftm_schema = "Association"
        source_document_url = str(relation.get("sourceDocumentUrl") or "")
        relation_evidence_id = evidence_id
        if source_document_url:
            relation_evidence_id = _graph_evidence(
                evidence,
                source_id=companyinfo_source_id,
                source_name=COMPANYINFO_SOURCE_NAME,
                title=f"Companyinfo source document: {label}",
                source_url=source_document_url,
                evidence_type="Corporate registry source document",
                published_at=company.get("sourceUpdatedAt") or "",
                note=COMPANYINFO_CAVEAT,
                identity=f"document|{source_document_url}",
            )
            evidence[relation_evidence_id].update(
                {"authorityLevel": "secondary", "fetchedAt": fetched_at}
            )
        relationship_id = _investigation_id(
            "company-rel",
            case_id,
            identification_code,
            role_type,
            party_id,
            relation.get("startDate"),
            relation.get("endDate"),
            relation.get("sharePercentage"),
            relation.get("current"),
        )
        _graph_link(
            relationships,
            case_id=case_id,
            from_id=from_id,
            to_id=to_id,
            relationship_type=label,
            relationship_id=relationship_id,
            evidence_ids=[relation_evidence_id],
            confidence=0.95,
            verification_status="source-stated",
            details=COMPANYINFO_CAVEAT,
            ftm_schema=ftm_schema,
            properties={
                "roleType": role_type,
                "role": relation.get("role") or role_type,
                "current": bool(relation.get("current")),
                "startDate": relation.get("startDate") or "",
                "endDate": relation.get("endDate") or "",
                "sharePercentage": relation.get("sharePercentage"),
                "sourceDocumentUrl": source_document_url,
                "sourceAuthorityLevel": "secondary",
                "sourceUpdatedAt": company.get("sourceUpdatedAt") or "",
                "fetchedAt": fetched_at,
            },
        )

    for document_url in normalized.get("sourceDocuments") or []:
        document_id = _graph_entity(
            entities,
            name=f"Company registry source document for {company.get('name') or identification_code}",
            entity_type="Document",
            identity=f"document|{document_url}",
            entityRole="Company registry source document",
            sourceId=companyinfo_source_id,
            sourceUrl=document_url,
            evidenceIds=[evidence_id],
            ftmSchema="Document",
            ftmPropertiesJson=_json({"title": ["Company registry source document"], "sourceUrl": [document_url]}),
        )
        _graph_link(
            relationships,
            case_id=case_id,
            from_id=company_entity_id,
            to_id=document_id,
            relationship_type="Documented by registry record",
            evidence_ids=[evidence_id],
            confidence=0.95,
            verification_status="source-stated",
            properties={"sourceAuthorityLevel": "secondary"},
        )

    return (
        {
            "caseId": case_id,
            "rootEntityId": root_entity_id,
            "entities": list(entities.values()),
            "relationships": list(relationships.values()),
            "sources": list(sources.values()),
            "evidence": list(evidence.values()),
        },
        {
            "sourceId": companyinfo_source_id,
            "companyEntityId": company_entity_id,
            "entityCount": len(entities),
            "relationshipCount": len(relationships),
            "evidenceCount": len(evidence),
            "indicatorCount": len(normalized.get("indicators") or []),
            "sourceDocumentCount": len(normalized.get("sourceDocuments") or []),
        },
    )


def _create_job(case_id: str, identification_code: str, source_id: str) -> str:
    now = _utc_now()
    job_id = _investigation_id("company-job", case_id, identification_code, _iso(now))
    query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
    CREATE (job:CompanyRegistryEnrichmentJob {
      jobId: $jobId, caseId: $caseId, sourceId: $sourceId,
      identificationCode: $identificationCode, status: 'running', attemptCount: 1,
      requestedAt: datetime(), lastAttemptAt: datetime(), createdAt: datetime(), updatedAt: datetime()
    })
    MERGE (caseNode)-[:HAS_COMPANY_ENRICHMENT_JOB]->(job)
    RETURN job.jobId AS jobId
    """
    with _db_session(get_driver()) as session:
        records = _execute_write(
            session,
            query,
            {
                "caseId": case_id,
                "jobId": job_id,
                "sourceId": source_id,
                "identificationCode": identification_code,
            },
        )
    if not records:
        raise HTTPException(status_code=404, detail="Case not found")
    return job_id


def _finish_job(
    job_id: str,
    *,
    status: str,
    metrics: Optional[Dict[str, object]] = None,
    errors: Optional[List[Dict[str, object]]] = None,
    retry_after_at: str = "",
) -> None:
    metrics = metrics or {}
    query = """
    MATCH (job:CompanyRegistryEnrichmentJob {jobId: $jobId})
    SET job.status = $status, job.companyEntityId = $companyEntityId,
        job.entityCount = $entityCount, job.relationshipCount = $relationshipCount,
        job.evidenceCount = $evidenceCount, job.indicatorCount = $indicatorCount,
        job.sourceDocumentCount = $sourceDocumentCount,
        job.errorCount = size($errors), job.errorsJson = $errorsJson,
        job.retryAfterAt = CASE WHEN $retryAfterAt = '' THEN null ELSE datetime($retryAfterAt) END,
        job.lastSuccessAt = CASE WHEN $status IN ['completed', 'partial', 'cached'] THEN datetime() ELSE job.lastSuccessAt END,
        job.completedAt = datetime(), job.updatedAt = datetime()
    RETURN job.jobId AS jobId
    """
    with _db_session(get_driver()) as session:
        _execute_write(
            session,
            query,
            {
                "jobId": job_id,
                "status": status,
                "companyEntityId": metrics.get("companyEntityId") or "",
                "entityCount": int(metrics.get("entityCount") or 0),
                "relationshipCount": int(metrics.get("relationshipCount") or 0),
                "evidenceCount": int(metrics.get("evidenceCount") or 0),
                "indicatorCount": int(metrics.get("indicatorCount") or 0),
                "sourceDocumentCount": int(metrics.get("sourceDocumentCount") or 0),
                "errors": errors or [],
                "errorsJson": _json(errors or []),
                "retryAfterAt": retry_after_at,
            },
        )


def _persist_snapshot(
    *,
    case_id: str,
    job_id: str,
    source_id: str,
    company_entity_id: str,
    identification_code: str,
    payload_hash: str,
    normalized: Dict[str, object],
    fetched_at: str,
) -> str:
    snapshot_id = _investigation_id(
        "company-snapshot", source_id, identification_code, payload_hash
    )
    sanitized = {
        "company": normalized.get("company") or {},
        "relationships": [
            {key: value for key, value in row.items() if key != "personalIdentityHash"}
            for row in normalized.get("relationships") or []
        ],
        "indicators": normalized.get("indicators") or [],
        "sourceDocuments": normalized.get("sourceDocuments") or [],
    }
    query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
    MATCH (source:InvestigationDataSource {sourceId: $sourceId})
    MATCH (entity:InvestigationEntity {entityId: $companyEntityId})
    MATCH (job:CompanyRegistryEnrichmentJob {jobId: $jobId})
    MERGE (snapshot:CompanyRegistrySnapshot {snapshotId: $snapshotId})
    ON CREATE SET snapshot.createdAt = datetime()
    SET snapshot.caseId = $caseId, snapshot.sourceId = $sourceId,
        snapshot.companyEntityId = $companyEntityId,
        snapshot.identificationCode = $identificationCode,
        snapshot.payloadHash = $payloadHash,
        snapshot.sanitizedPayloadJson = $sanitizedPayloadJson,
        snapshot.rawPayloadStored = false,
        snapshot.personalIdsStored = false,
        snapshot.sourceUpdatedAt = $sourceUpdatedAt,
        snapshot.fetchedAt = datetime($fetchedAt), snapshot.updatedAt = datetime()
    MERGE (caseNode)-[:HAS_COMPANY_REGISTRY_SNAPSHOT]->(snapshot)
    MERGE (source)-[:HAS_SNAPSHOT]->(snapshot)
    MERGE (entity)-[:HAS_SOURCE_SNAPSHOT]->(snapshot)
    MERGE (job)-[:PRODUCED_SNAPSHOT]->(snapshot)
    SET source.lastAttemptAt = datetime($fetchedAt),
        source.lastSuccessAt = datetime($fetchedAt),
        source.sourceUpdatedAt = $sourceUpdatedAt,
        source.payloadHash = $payloadHash,
        source.updatedAt = datetime()
    RETURN snapshot.snapshotId AS snapshotId
    """
    with _db_session(get_driver()) as session:
        _execute_write(
            session,
            query,
            {
                "caseId": case_id,
                "jobId": job_id,
                "sourceId": source_id,
                "companyEntityId": company_entity_id,
                "snapshotId": snapshot_id,
                "identificationCode": identification_code,
                "payloadHash": payload_hash,
                "sanitizedPayloadJson": _json(sanitized),
                "sourceUpdatedAt": str((normalized.get("company") or {}).get("sourceUpdatedAt") or ""),
                "fetchedAt": fetched_at,
            },
        )
    return snapshot_id


def _cached_company(case_id: str, identification_code: str) -> Optional[Dict[str, object]]:
    source_id = _investigation_id("source", COMPANYINFO_SOURCE_NAME)
    query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_ENTITY]->(entity:InvestigationEntity {
      identificationCode: $identificationCode, sourceId: $sourceId
    })
    MATCH (caseNode)-[:USES_INVESTIGATION_SOURCE]->(source:InvestigationDataSource {sourceId: $sourceId})
    OPTIONAL MATCH (caseNode)-[:HAS_COMPANY_ENRICHMENT_JOB]->(job:CompanyRegistryEnrichmentJob {
      identificationCode: $identificationCode
    })
    RETURN entity.entityId AS companyEntityId,
           toString(source.lastSuccessAt) AS lastSuccessAt,
           source.sourceUpdatedAt AS sourceUpdatedAt,
           source.payloadHash AS payloadHash,
           job.jobId AS jobId, job.status AS jobStatus
    ORDER BY job.requestedAt DESC
    LIMIT 1
    """
    with _db_session(get_driver()) as session:
        rows = _execute_read(
            session,
            query,
            {
                "caseId": case_id,
                "identificationCode": identification_code,
                "sourceId": source_id,
            },
        )
    if not rows:
        return None
    row = rows[0].data()
    last_success = _parse_date(row.get("lastSuccessAt"))
    if not last_success:
        return None
    age_hours = (_utc_now() - last_success).total_seconds() / 3600
    if age_hours > int(_companyinfo_config()["cacheHours"]):
        return None
    row["ageHours"] = round(age_hours, 2)
    return row


def _job_row(case_id: str, job_id: str) -> Dict[str, object]:
    query = """
    MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_COMPANY_ENRICHMENT_JOB]->(job:CompanyRegistryEnrichmentJob {jobId: $jobId})
    RETURN job.jobId AS jobId, job.caseId AS caseId, job.sourceId AS sourceId,
           job.identificationCode AS identificationCode, job.status AS status,
           coalesce(job.attemptCount, 1) AS attemptCount,
           coalesce(job.companyEntityId, '') AS companyEntityId,
           coalesce(job.entityCount, 0) AS entityCount,
           coalesce(job.relationshipCount, 0) AS relationshipCount,
           coalesce(job.evidenceCount, 0) AS evidenceCount,
           coalesce(job.indicatorCount, 0) AS indicatorCount,
           coalesce(job.sourceDocumentCount, 0) AS sourceDocumentCount,
           coalesce(job.errorCount, 0) AS errorCount,
           coalesce(job.errorsJson, '[]') AS errorsJson,
           toString(job.requestedAt) AS requestedAt,
           toString(job.lastAttemptAt) AS lastAttemptAt,
           toString(job.lastSuccessAt) AS lastSuccessAt,
           toString(job.retryAfterAt) AS retryAfterAt,
           toString(job.completedAt) AS completedAt
    """
    with _db_session(get_driver()) as session:
        rows = _execute_read(session, query, {"caseId": case_id, "jobId": job_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Corporate enrichment job not found")
    row = rows[0].data()
    try:
        row["errors"] = json.loads(row.pop("errorsJson") or "[]")
    except (TypeError, ValueError):
        row["errors"] = []
    row["retryable"] = row.get("status") in {"failed", "partial", "rate-limited"}
    return row


def _corporate_dossier(case_id: str, entity_id: str) -> Dict[str, object]:
    graph = _load_investigation_graph(case_id)
    entity = next((row for row in graph.get("nodes") or [] if row.get("id") == entity_id), None)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity is not attached to this case")
    properties = entity.get("properties") or {}
    try:
        indicators = json.loads(str(properties.get("enrichmentIndicatorsJson") or "[]"))
    except (TypeError, ValueError):
        indicators = []
    evidence_by_id = {
        str(row.get("evidenceId")): row for row in graph.get("evidence") or []
    }
    affiliations = []
    for relationship in graph.get("relationships") or []:
        if entity_id not in {relationship.get("source"), relationship.get("target")}:
            continue
        if relationship.get("label") not in {
            "Director of",
            "Former director of",
            "Shareholder of",
            "Former shareholder of",
            "Owner of",
            "Former owner of",
            "Historical affiliation",
            "Related company",
        }:
            continue
        other_id = (
            relationship.get("target")
            if relationship.get("source") == entity_id
            else relationship.get("source")
        )
        other = next((row for row in graph.get("nodes") or [] if row.get("id") == other_id), {})
        relationship_properties = relationship.get("properties") or {}
        affiliations.append(
            {
                "relationshipId": relationship.get("id"),
                "label": relationship.get("label"),
                "entityId": other_id,
                "displayName": other.get("label"),
                "entityType": other.get("type"),
                "roleType": relationship_properties.get("roleType"),
                "role": relationship_properties.get("role"),
                "current": relationship_properties.get("current"),
                "startDate": relationship_properties.get("startDate"),
                "endDate": relationship_properties.get("endDate"),
                "sharePercentage": relationship_properties.get("sharePercentage"),
                "sourceDocumentUrl": relationship_properties.get("sourceDocumentUrl"),
                "sourceAuthorityLevel": relationship_properties.get("sourceAuthorityLevel"),
                "verificationStatus": relationship.get("verificationStatus"),
                "evidenceIds": relationship.get("evidenceIds") or [],
            }
        )
    contradiction_query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_ENTITY]->(entity:InvestigationEntity {entityId: $entityId})
    WITH caseNode, coalesce(entity.canonicalEntityId, entity.entityId) AS canonicalEntityId
    MATCH (caseNode)-[:HAS_INVESTIGATION_STATEMENT]->(statement:InvestigationStatement)
    WHERE statement.canonicalSubjectId = canonicalEntityId
      AND size(coalesce(statement.contradictsStatementIds, [])) > 0
    OPTIONAL MATCH (source:InvestigationDataSource {sourceId: statement.sourceId})
    RETURN statement.statementId AS statementId, statement.predicate AS predicate,
           statement.value AS value, statement.sourceId AS sourceId,
           statement.evidenceId AS evidenceId,
           statement.verificationStatus AS verificationStatus,
           statement.publishedAt AS publishedAt,
           toString(statement.lastSeen) AS retrievedAt,
           coalesce(source.authorityTier, 99) AS authorityTier,
           coalesce(source.authorityLevel, 'unknown') AS authorityLevel,
           statement.contradictsStatementIds AS contradictsStatementIds
    ORDER BY statement.predicate, statement.statementId
    """
    with _db_session(get_driver()) as session:
        contradiction_rows = _execute_read(
            session, contradiction_query, {"caseId": case_id, "entityId": entity_id}
        )
    source_documents = [
        row
        for row in evidence_by_id.values()
        if row.get("evidenceType") == "Corporate registry source document"
    ]
    contradiction_groups: Dict[str, List[Dict[str, object]]] = {}
    for record in contradiction_rows:
        row = record.data()
        contradiction_groups.setdefault(str(row.get("predicate") or "unknown"), []).append(row)
    contradictions: List[Dict[str, object]] = []
    for predicate, rows in sorted(contradiction_groups.items()):
        best_tier = min(int(row.get("authorityTier") or 99) for row in rows)
        preferred = max(
            (row for row in rows if int(row.get("authorityTier") or 99) == best_tier),
            key=lambda row: str(row.get("publishedAt") or row.get("retrievedAt") or ""),
            default={},
        )
        contradictions.append(
            {
                "conflictId": _investigation_id(
                    "statement-conflict",
                    case_id,
                    properties.get("canonicalEntityId") or entity_id,
                    predicate,
                ),
                "predicate": predicate,
                "status": "requires-review",
                "preferredStatementId": preferred.get("statementId"),
                "preferenceReason": (
                    "Lowest authority tier is preferred for the operational view; "
                    "all contradictory source statements remain preserved."
                ),
                "statements": rows,
            }
        )
    return {
        "caseId": case_id,
        "entityId": entity_id,
        "company": {
            "displayName": entity.get("label"),
            "identificationCode": properties.get("identificationCode"),
            "registrationNumber": properties.get("registrationNumber"),
            "legalForm": properties.get("legalForm"),
            "status": properties.get("companyStatus"),
            "registrationDate": properties.get("registrationDate"),
            "address": properties.get("address"),
            "email": properties.get("email"),
            "sourceUpdatedAt": properties.get("sourceUpdatedAt"),
            "fetchedAt": properties.get("companyInfoFetchedAt"),
            "payloadHash": properties.get("payloadHash"),
            "authorityLevel": properties.get("sourceAuthorityLevel"),
            "sourceUrl": properties.get("sourceUrl"),
        },
        "affiliations": affiliations,
        "indicators": indicators,
        "sourceDocuments": source_documents,
        "naprVerification": {
            "status": properties.get("naprVerificationStatus") or "manual-required",
            "officialUrl": properties.get("naprOfficialUrl") or NAPR_SEARCH_URL,
            "sourceDocumentUrl": properties.get("naprSourceDocumentUrl") or "",
            "verifiedAt": properties.get("naprVerifiedAt") or "",
            "verifiedBy": properties.get("naprVerifiedBy") or "",
            "comparedFields": json.loads(
                str(properties.get("naprComparedFieldsJson") or "{}")
            ),
        },
        "contradictions": contradictions,
        "personalIdentifiers": {
            "exposed": False,
            "storedRaw": False,
            "matching": "server-side keyed HMAC only when FS_DD_ID_HASH_KEY is configured",
        },
        "caveat": COMPANYINFO_CAVEAT,
    }


@router.get("/connectors/georgian-company-registry/capabilities")
def get_georgian_company_registry_capabilities():
    config = _companyinfo_config()
    return {
        "connectorId": "georgian-company-registry",
        "companyinfo": {
            "enabled": bool(config["enabled"] and config["permissionAcknowledged"]),
            "baseUrl": COMPANYINFO_API_BASE,
            "authorityLevel": "secondary",
            "updateCadence": "monthly",
            "permissionState": "undocumented-public-api-review-required",
            "permissionAcknowledged": config["permissionAcknowledged"],
            "enumerationEnabled": False,
            "lookupMode": "identification-code-only",
            "rateLimit": {
                "minimumIntervalSeconds": config["minimumIntervalSeconds"],
                "retries": config["retries"],
                "backoffSeconds": config["backoffSeconds"],
                "timeoutSeconds": config["timeoutSeconds"],
            },
            "cacheHours": config["cacheHours"],
            "killSwitch": "FS_COMPANYINFO_ENABLED",
            "caveat": COMPANYINFO_CAVEAT,
        },
        "napr": {
            "enabled": True,
            "automated": False,
            "authorityLevel": "authoritative",
            "permissionState": "manual-low-volume-only",
            "url": NAPR_SEARCH_URL,
            "caveat": "No documented JSON API was found; FS does not bypass CAPTCHA or access controls.",
        },
        "personalIdentifiers": {
            "acceptedFromBrowser": False,
            "returnedByApi": False,
            "storedRaw": False,
            "keyedMatchingConfigured": bool(os.getenv("FS_DD_ID_HASH_KEY", "").strip()),
        },
    }


@router.get("/cases/{case_id}/corporate-enrichment/sources")
def list_corporate_enrichment_sources(case_id: str):
    _case_and_report_for_graph(case_id)
    source_ids = [
        _investigation_id("source", COMPANYINFO_SOURCE_NAME),
        _investigation_id("source", NAPR_SOURCE_NAME),
    ]
    query = """
    UNWIND $sourceIds AS sourceId
    OPTIONAL MATCH (:DueDiligenceCase {caseId: $caseId})-[:USES_INVESTIGATION_SOURCE]->(source:InvestigationDataSource {sourceId: sourceId})
    OPTIONAL MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_COMPANY_ENRICHMENT_JOB]->(job:CompanyRegistryEnrichmentJob {sourceId: sourceId})
    RETURN sourceId, properties(source) AS sourceProperties,
           count(DISTINCT job) AS jobCount,
           max(job.lastAttemptAt) AS lastAttemptAt,
           max(job.lastSuccessAt) AS jobLastSuccessAt,
           sum(coalesce(job.errorCount, 0)) AS errorCount
    """
    with _db_session(get_driver()) as session:
        rows = _execute_read(
            session, query, {"caseId": case_id, "sourceIds": source_ids}
        )
    by_id = {str(row.get("sourceId")): row.data() for row in rows}
    definitions = [
        {
            "sourceId": source_ids[0],
            "name": COMPANYINFO_SOURCE_NAME,
            "sourceType": "Secondary corporate registry aggregator",
            "authorityLevel": "secondary",
            "freshness": {"cadence": "monthly", "state": "unknown"},
            "permissionState": "undocumented-public-api-review-required",
            "caveat": COMPANYINFO_CAVEAT,
        },
        {
            "sourceId": source_ids[1],
            "name": NAPR_SOURCE_NAME,
            "sourceType": "Authoritative company registry",
            "authorityLevel": "authoritative",
            "freshness": {"cadence": "on-demand manual verification", "state": "unknown"},
            "permissionState": "manual-low-volume-only",
            "caveat": "No automated scraping or access-control bypass.",
        },
    ]
    for definition in definitions:
        row = by_id.get(definition["sourceId"], {})
        props = row.get("sourceProperties") or {}
        definition.update(
            {
                "lastAttemptAt": str(row.get("lastAttemptAt") or props.get("lastAttemptAt") or ""),
                "lastSuccessAt": str(row.get("jobLastSuccessAt") or props.get("lastSuccessAt") or ""),
                "sourceUpdatedAt": props.get("sourceUpdatedAt") or "",
                "jobCount": int(row.get("jobCount") or 0),
                "errorCount": int(row.get("errorCount") or 0),
                "recordCount": int(row.get("jobCount") or 0),
                "rateLimitState": (
                    "disabled-permission"
                    if definition["sourceId"] == source_ids[0]
                    and not (
                        _companyinfo_config()["enabled"]
                        and _companyinfo_config()["permissionAcknowledged"]
                    )
                    else "manual-only"
                    if definition["sourceId"] == source_ids[1]
                    else "ready"
                ),
            }
        )
        if props.get("sourceUpdatedAt"):
            definition["freshness"]["state"] = "observed"
            definition["freshness"]["sourceUpdatedAt"] = props.get("sourceUpdatedAt")
    return {"caseId": case_id, "sources": definitions}


@router.get("/cases/{case_id}/corporate-enrichment/jobs/{job_id}")
def get_company_enrichment_job(case_id: str, job_id: str):
    return _job_row(case_id, job_id)


@router.post("/cases/{case_id}/corporate-enrichment/companyinfo")
def enrich_company_from_companyinfo(
    case_id: str, payload: CompanyInfoEnrichmentRequest
):
    case_row, _ = _case_and_report_for_graph(case_id)
    config = _companyinfo_config()
    if not config["enabled"] or not config["permissionAcknowledged"]:
        raise HTTPException(
            status_code=403,
            detail={
                "status": "blocked-permission",
                "permissionState": "undocumented-public-api-review-required",
                "retryable": False,
                "message": (
                    "Companyinfo enrichment is disabled until reuse permission/terms "
                    "are reviewed and acknowledged by the operator."
                ),
            },
        )
    cached = None if payload.force_refresh else _cached_company(case_id, payload.identification_code)
    if cached:
        graph = _load_investigation_graph(case_id)
        graph["enrichmentResult"] = {
            "jobId": cached.get("jobId"),
            "status": "cached",
            "companyEntityId": cached.get("companyEntityId"),
            "identificationCode": payload.identification_code,
            "cache": {"hit": True, "ageHours": cached.get("ageHours")},
            "sourceUpdatedAt": cached.get("sourceUpdatedAt"),
            "payloadHash": cached.get("payloadHash"),
            "errors": [],
            "retryable": False,
            "naprVerification": {"status": "manual-required", "url": NAPR_SEARCH_URL},
        }
        return graph

    source_id = _investigation_id("source", COMPANYINFO_SOURCE_NAME)
    job_id = _create_job(case_id, payload.identification_code, source_id)
    try:
        raw_payload, partial_errors = fetch_companyinfo_company(payload.identification_code)
    except CompanyInfoAdapterError as exc:
        retry_after_at = (
            _iso(_utc_now() + timedelta(seconds=exc.retry_after_seconds))
            if exc.retry_after_seconds
            else ""
        )
        errors = [{"stage": "companyinfo", "type": exc.error_type, "message": str(exc)}]
        status = "rate-limited" if exc.status_code == 429 else "failed"
        _finish_job(
            job_id,
            status=status,
            errors=errors,
            retry_after_at=retry_after_at,
        )
        headers = (
            {"Retry-After": str(exc.retry_after_seconds)}
            if exc.retry_after_seconds
            else None
        )
        raise HTTPException(status_code=exc.status_code, detail={"jobId": job_id, "status": status, "errors": errors, "retryAfterAt": retry_after_at}, headers=headers) from exc

    fetched_at = _iso(_utc_now())
    raw_hash = _payload_hash(raw_payload)
    normalized = normalize_companyinfo_payload(raw_payload, payload.identification_code)
    _apply_indicator_errors(normalized, partial_errors)
    company = normalized.get("company") or {}
    if not company.get("name"):
        errors = partial_errors + [
            {"stage": "normalization", "type": "invalid-payload", "message": "Company name is missing"}
        ]
        _finish_job(job_id, status="failed", errors=errors)
        raise HTTPException(
            status_code=502,
            detail={"jobId": job_id, "status": "failed", "errors": errors},
        )
    base_bundle = _build_investigation_graph_bundle(
        case_row, {"reportId": None, "payload": {}}
    )
    bundle, metrics = build_companyinfo_bundle(
        case_id=case_id,
        root_entity_id=str(base_bundle.get("rootEntityId") or ""),
        normalized=normalized,
        payload_hash=raw_hash,
        fetched_at=fetched_at,
    )
    base_entities = {
        str(row.get("entityId")): row for row in base_bundle.get("entities") or []
    }
    for row in bundle.get("entities") or []:
        base_entities[str(row.get("entityId"))] = row
    bundle["entities"] = list(base_entities.values())
    _persist_investigation_graph_bundle(bundle)
    snapshot_id = _persist_snapshot(
        case_id=case_id,
        job_id=job_id,
        source_id=str(metrics.get("sourceId") or source_id),
        company_entity_id=str(metrics.get("companyEntityId") or ""),
        identification_code=payload.identification_code,
        payload_hash=raw_hash,
        normalized=normalized,
        fetched_at=fetched_at,
    )
    status = "partial" if partial_errors else "completed"
    _finish_job(job_id, status=status, metrics=metrics, errors=partial_errors)
    graph = _load_investigation_graph(case_id)
    graph["enrichmentResult"] = {
        "jobId": job_id,
        "status": status,
        "companyEntityId": metrics.get("companyEntityId"),
        "identificationCode": payload.identification_code,
        "snapshotId": snapshot_id,
        "payloadHash": raw_hash,
        "sourceUpdatedAt": company.get("sourceUpdatedAt") or "",
        "fetchedAt": fetched_at,
        "cache": {"hit": False, "ttlHours": _companyinfo_config()["cacheHours"]},
        "counts": {key: value for key, value in metrics.items() if key.endswith("Count")},
        "errors": partial_errors,
        "retryable": status == "partial",
        "naprVerification": {"status": "manual-required", "url": NAPR_SEARCH_URL},
        "personalIdentifiers": {"returned": False, "storedRaw": False},
        "caveat": COMPANYINFO_CAVEAT,
    }
    return graph


@router.get("/cases/{case_id}/entities/{entity_id}/corporate-registry")
def get_company_registry_dossier(case_id: str, entity_id: str):
    return _corporate_dossier(case_id, entity_id)


@router.post("/cases/{case_id}/entities/{entity_id}/corporate-registry/napr-verification")
def record_napr_verification(
    case_id: str, entity_id: str, payload: NaprVerificationRequest
):
    graph = _load_investigation_graph(case_id)
    entity = next((row for row in graph.get("nodes") or [] if row.get("id") == entity_id), None)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity is not attached to this case")
    entity_properties = entity.get("properties") or {}
    identification_code = str(entity_properties.get("identificationCode") or "")
    if not identification_code:
        raise HTTPException(status_code=409, detail="Entity has no company identification code")
    sources: Dict[str, Dict[str, object]] = {}
    evidence: Dict[str, Dict[str, object]] = {}
    entities: Dict[str, Dict[str, object]] = {
        entity_id: {
            "entityId": entity_id,
            "name": entity.get("label"),
            "entityType": entity.get("type"),
            "naprVerificationStatus": payload.status,
            "naprOfficialUrl": payload.official_url,
            "naprSourceDocumentUrl": payload.source_document_url or "",
            "naprVerifiedAt": payload.verified_at or _iso(_utc_now()),
            "naprVerifiedBy": payload.verified_by,
            "naprComparedFieldsJson": _json(payload.compared_fields),
        }
    }
    links: Dict[str, Dict[str, object]] = {}
    source_id = _graph_source(
        sources,
        name=NAPR_SOURCE_NAME,
        url=NAPR_SEARCH_URL,
        source_type="Authoritative company registry",
        connector="napr-manual-verification",
        sourceOwner="National Agency of Public Registry",
        authorityLevel="authoritative",
        authorityTier=1,
        jurisdiction="GE",
        canonicalUrl=NAPR_SEARCH_URL,
        accessMode="analyst-verification",
        parserVersion="manual-verification-v1",
        mappingVersion="ftm-napr-verification-v1",
        permissionState="manual-low-volume-only",
        ingestionMode="analyst-verification",
        automationEnabled=False,
    )
    evidence_id = _graph_evidence(
        evidence,
        source_id=source_id,
        source_name=NAPR_SOURCE_NAME,
        title=f"NAPR verification for {entity.get('label')}",
        source_url=payload.source_document_url or payload.official_url,
        evidence_type="Authoritative registry verification",
        published_at=payload.verified_at or _iso(_utc_now()),
        note=payload.notes,
        identity=f"napr|{identification_code}|{payload.status}|{payload.source_document_url or payload.official_url}",
    )
    evidence[evidence_id].update(
        {
            "authorityLevel": "authoritative",
            "verificationStatus": payload.status,
            "verifiedBy": payload.verified_by,
            "comparedFieldsJson": _json(payload.compared_fields),
            "parserVersion": "manual-verification-v1",
            "mappingVersion": "ftm-napr-verification-v1",
            "retrievedAt": payload.verified_at or _iso(_utc_now()),
        }
    )
    document_id = _graph_entity(
        entities,
        name=f"NAPR verification record for {entity.get('label')}",
        entity_type="Document",
        identity=f"napr-document|{identification_code}|{payload.source_document_url or payload.official_url}",
        entityRole="Authoritative registry verification record",
        sourceId=source_id,
        sourceUrl=payload.source_document_url or payload.official_url,
        authorityLevel="authoritative",
        evidenceIds=[evidence_id],
        ftmSchema="Document",
        ftmPropertiesJson=_json(
            {
                "title": [f"NAPR verification record for {entity.get('label')}"],
                "sourceUrl": [payload.source_document_url or payload.official_url],
            }
        ),
    )
    _graph_link(
        links,
        case_id=case_id,
        from_id=entity_id,
        to_id=document_id,
        relationship_type="NAPR verification",
        evidence_ids=[evidence_id],
        confidence=1.0,
        verification_status="verified" if payload.status == "verified" else "analyst-added",
        details=payload.notes,
        properties={
            "naprStatus": payload.status,
            "authorityLevel": "authoritative",
            "registrationNumber": payload.registration_number or "",
            "comparedFieldsJson": _json(payload.compared_fields),
        },
    )
    bundle = {
        "caseId": case_id,
        "rootEntityId": next(
            (row.get("id") for row in graph.get("nodes") or [] if row.get("isRoot")),
            entity_id,
        ),
        "entities": list(entities.values()),
        "relationships": list(links.values()),
        "sources": list(sources.values()),
        "evidence": list(evidence.values()),
    }
    _persist_investigation_graph_bundle(bundle)
    return _corporate_dossier(case_id, entity_id)
