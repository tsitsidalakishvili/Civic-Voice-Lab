from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field, model_validator

from .core.auth_store import (
    decrypt_short_secret,
    encrypt_short_secret,
    keyed_hash,
    normalize_exact_email,
)
from .core.config import get_settings
from .core.errors import CONTRACT_VERSION, error_response
from .core.rate_limit import rate_limiter
from .db import get_active_database, get_driver

router = APIRouter(prefix="/privacy/v1", tags=["privacy-compliance"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).astimezone(timezone.utc).isoformat()


def _read(query: str, params: dict | None = None) -> list[dict]:
    driver = get_driver()
    with driver.session(database=get_active_database()) as session:
        return [record.data() for record in session.run(query, params or {})]


def _write(query: str, params: dict | None = None) -> list[dict]:
    driver = get_driver()
    with driver.session(database=get_active_database()) as session:
        if hasattr(session, "execute_write"):
            return session.execute_write(
                lambda tx: [record.data() for record in tx.run(query, params or {})]
            )
        return session.write_transaction(
            lambda tx: [record.data() for record in tx.run(query, params or {})]
        )


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or uuid4())


def _principal_id(request: Request) -> str:
    principal = getattr(request.state, "principal", None) or {}
    return str(principal.get("principalId") or "anonymous")


def _audit(
    request: Request,
    event_type: str,
    resource_type: str,
    resource_id: str,
    *,
    outcome: str = "success",
    purpose_id: str = "",
    fields: list[str] | None = None,
    reason_code: str = "",
) -> None:
    settings = get_settings()
    principal = getattr(request.state, "principal", None) or {}
    _write(
        """
        CREATE (event:ComplianceAuditEvent {
          eventId: $eventId, eventType: $eventType,
          actorId: $actorId, actorProvider: $actorProvider,
          resourceType: $resourceType, resourceId: $resourceId,
          purposeId: $purposeId, outcome: $outcome,
          fieldNames: $fieldNames, reasonCode: $reasonCode,
          requestId: $requestId, ipHash: $ipHash,
          userAgentHash: $userAgentHash, createdAt: datetime()
        })
        """,
        {
            "eventId": str(uuid4()),
            "eventType": event_type[:80],
            "actorId": str(principal.get("principalId") or "anonymous")[:100],
            "actorProvider": str(principal.get("provider") or "")[:30],
            "resourceType": resource_type[:80],
            "resourceId": resource_id[:120],
            "purposeId": purpose_id[:100],
            "outcome": outcome[:30],
            "fieldNames": sorted(set(fields or [])),
            "reasonCode": reason_code[:80],
            "requestId": _request_id(request)[:80],
            "ipHash": keyed_hash(
                settings,
                "compliance-ip",
                str(request.client.host if request.client else ""),
            ),
            "userAgentHash": keyed_hash(
                settings,
                "compliance-ua",
                str(request.headers.get("User-Agent") or ""),
            ),
        },
    )


class SubjectAddress(BaseModel):
    type: Literal["email", "phone"]
    value: str = Field(min_length=3, max_length=320)


class SubjectReference(BaseModel):
    subject_id: str | None = Field(default=None, alias="subjectId")
    address: SubjectAddress | None = None

    @model_validator(mode="after")
    def validate_reference(self):
        if bool(self.subject_id) == bool(self.address):
            raise ValueError("Provide exactly one of subjectId or address.")
        return self


def _normalize_address(address: SubjectAddress) -> str:
    if address.type == "email":
        return normalize_exact_email(address.value)
    candidate = "".join(char for char in str(address.value).strip() if char.isdigit() or char == "+")
    if len(candidate.replace("+", "")) < 7:
        raise ValueError("A valid phone number is required.")
    return candidate


def _subject_key(subject: SubjectReference) -> str:
    settings = get_settings()
    if subject.subject_id:
        return keyed_hash(settings, "privacy-subject-id", subject.subject_id.strip())
    normalized = _normalize_address(subject.address)  # type: ignore[arg-type]
    return keyed_hash(settings, f"privacy-address-{subject.address.type}", normalized)  # type: ignore[union-attr]


class PurposeCreate(BaseModel):
    purpose_id: str = Field(alias="purposeId", min_length=2, max_length=100)
    version: int = Field(default=1, ge=1)
    name: str = Field(min_length=2, max_length=200)
    workflow: str = Field(min_length=2, max_length=100)
    lawful_basis_article5: str = Field(alias="lawfulBasisArticle5", min_length=2, max_length=200)
    special_category_basis_article6: str | None = Field(
        default=None, alias="specialCategoryBasisArticle6", max_length=200
    )
    status: Literal["draft", "active", "disabled"] = "draft"
    owner: str = ""
    counsel_decision: Literal["approved", "pending", "rejected"] = Field(
        default="pending", alias="counselDecision"
    )


class NoticeCreate(BaseModel):
    purpose_id: str = Field(alias="purposeId")
    version: int = Field(ge=1)
    locale: Literal["ka", "en"]
    summary: str = Field(min_length=2, max_length=1000)
    content: str = Field(min_length=2, max_length=30000)
    controller: dict = Field(default_factory=dict)
    effective_from: str = Field(alias="effectiveFrom")
    status: Literal["draft", "active", "retired"] = "draft"


class FieldPolicyCreate(BaseModel):
    purpose_id: str = Field(alias="purposeId")
    purpose_version: int = Field(alias="purposeVersion", ge=1)
    field: str = Field(min_length=1, max_length=160)
    classification: Literal[
        "public", "contact", "personal", "sensitive", "special-category"
    ]
    collection: Literal["required", "optional", "prohibited"] = "prohibited"
    allowed_roles: list[str] = Field(default_factory=list, alias="allowedRoles")
    masked: bool = True
    export_allowed: bool = Field(default=False, alias="exportAllowed")
    retention_category: str = Field(default="", alias="retentionCategory")
    counsel_decision: Literal["approved", "pending", "rejected"] = Field(
        default="pending", alias="counselDecision"
    )


@router.post("/admin/purposes", status_code=201)
def create_purpose(request: Request, payload: PurposeCreate):
    version_id = f"{payload.purpose_id}:v{payload.version}"
    rows = _write(
        """
        MERGE (purpose:ProcessingPurpose {purposeVersionId: $purposeVersionId})
        ON CREATE SET purpose.createdAt = datetime(), purpose.createdBy = $actorId
        SET purpose.purposeId = $purposeId, purpose.version = $version,
            purpose.name = $name, purpose.workflow = $workflow,
            purpose.lawfulBasisArticle5 = $lawfulBasisArticle5,
            purpose.specialCategoryBasisArticle6 = $specialCategoryBasisArticle6,
            purpose.status = $status, purpose.owner = $owner,
            purpose.counselDecision = $counselDecision,
            purpose.updatedAt = datetime()
        RETURN purpose{.*} AS purpose
        """,
        {
            **payload.model_dump(by_alias=True),
            "purposeVersionId": version_id,
            "actorId": _principal_id(request),
        },
    )
    _audit(request, "purpose_configured", "ProcessingPurpose", version_id)
    return {"contractVersion": CONTRACT_VERSION, **(rows[0]["purpose"] if rows else {})}


@router.post("/admin/notices", status_code=201)
def create_notice(request: Request, payload: NoticeCreate):
    notice_id = f"{payload.purpose_id}:{payload.locale}:v{payload.version}"
    content_hash = hashlib.sha256(payload.content.encode("utf-8")).hexdigest()
    rows = _write(
        """
        MATCH (purpose:ProcessingPurpose {purposeId: $purposeId})
        WHERE purpose.status IN ['active', 'draft']
        WITH purpose ORDER BY purpose.version DESC LIMIT 1
        MERGE (notice:NoticeVersion {noticeVersionId: $noticeVersionId})
        ON CREATE SET notice.createdAt = datetime(), notice.createdBy = $actorId
        SET notice.purposeId = $purposeId, notice.version = $version,
            notice.locale = $locale, notice.summary = $summary,
            notice.content = $content, notice.contentHash = $contentHash,
            notice.controllerJson = $controllerJson,
            notice.effectiveFrom = datetime($effectiveFrom),
            notice.status = $status, notice.updatedAt = datetime()
        MERGE (purpose)-[:HAS_NOTICE_VERSION]->(notice)
        RETURN notice.noticeVersionId AS noticeVersionId
        """,
        {
            "purposeId": payload.purpose_id,
            "noticeVersionId": notice_id,
            "version": payload.version,
            "locale": payload.locale,
            "summary": payload.summary,
            "content": payload.content,
            "contentHash": content_hash,
            "controllerJson": json.dumps(payload.controller, ensure_ascii=False),
            "effectiveFrom": payload.effective_from,
            "status": payload.status,
            "actorId": _principal_id(request),
        },
    )
    if not rows:
        return error_response(404, "PURPOSE_NOT_CONFIGURED", "The processing purpose is not configured.", request_id=_request_id(request))
    _audit(request, "notice_configured", "NoticeVersion", notice_id, purpose_id=payload.purpose_id)
    return {"contractVersion": CONTRACT_VERSION, "noticeVersionId": notice_id, "contentHash": content_hash}


@router.post("/admin/field-policies", status_code=201)
def create_field_policy(request: Request, payload: FieldPolicyCreate):
    policy_id = f"{payload.purpose_id}:v{payload.purpose_version}:{payload.field}"
    _write(
        """
        MATCH (purpose:ProcessingPurpose {purposeVersionId: $purposeVersionId})
        MERGE (policy:DataFieldPolicy {fieldPolicyId: $fieldPolicyId})
        ON CREATE SET policy.createdAt = datetime(), policy.createdBy = $actorId
        SET policy.purposeId = $purposeId, policy.purposeVersion = $purposeVersion,
            policy.field = $field, policy.classification = $classification,
            policy.collection = $collection, policy.allowedRoles = $allowedRoles,
            policy.masked = $masked, policy.exportAllowed = $exportAllowed,
            policy.retentionCategory = $retentionCategory,
            policy.counselDecision = $counselDecision, policy.updatedAt = datetime()
        MERGE (purpose)-[:HAS_FIELD_POLICY]->(policy)
        """,
        {
            **payload.model_dump(by_alias=True),
            "purposeVersionId": f"{payload.purpose_id}:v{payload.purpose_version}",
            "fieldPolicyId": policy_id,
            "actorId": _principal_id(request),
        },
    )
    _audit(request, "field_policy_configured", "DataFieldPolicy", policy_id, purpose_id=payload.purpose_id)
    return {"contractVersion": CONTRACT_VERSION, "fieldPolicyId": policy_id}


@router.get("/notices/current")
def current_notice(
    request: Request,
    workflow: str = Query(...),
    locale: str = Query(...),
    purpose_id: str = Query(..., alias="purposeId"),
):
    rows = _read(
        """
        MATCH (purpose:ProcessingPurpose {purposeId: $purposeId, workflow: $workflow, status: 'active'})
        WITH purpose ORDER BY purpose.version DESC LIMIT 1
        MATCH (purpose)-[:HAS_NOTICE_VERSION]->(notice:NoticeVersion {locale: $locale, status: 'active'})
        WHERE notice.effectiveFrom <= datetime()
        WITH purpose, notice ORDER BY notice.version DESC LIMIT 1
        OPTIONAL MATCH (purpose)-[:HAS_FIELD_POLICY]->(policy:DataFieldPolicy)
        RETURN purpose{.purposeId, .version, .name, .lawfulBasisArticle5,
                       .specialCategoryBasisArticle6, .status} AS purpose,
               notice.noticeVersionId AS noticeVersionId,
               notice.version AS noticeVersion, notice.locale AS locale,
               notice.contentHash AS contentHash,
               toString(notice.effectiveFrom) AS effectiveFrom,
               notice.controllerJson AS controllerJson,
               notice.summary AS summary, notice.content AS content,
               collect(policy{.field, .classification, .collection, .masked,
                              .exportAllowed, .counselDecision}) AS fields
        """,
        {"purposeId": purpose_id, "workflow": workflow, "locale": locale},
    )
    if not rows:
        return error_response(404, "NOTICE_NOT_CONFIGURED", "The requested privacy notice is not configured.", request_id=_request_id(request))
    row = rows[0]
    try:
        controller = json.loads(row.pop("controllerJson") or "{}")
    except ValueError:
        controller = {}
    return {
        "contractVersion": CONTRACT_VERSION,
        "purpose": row["purpose"],
        "notice": {
            "noticeVersionId": row["noticeVersionId"],
            "version": row["noticeVersion"],
            "locale": row["locale"],
            "contentHash": row["contentHash"],
            "effectiveFrom": row["effectiveFrom"],
            "controller": controller,
            "summary": row["summary"],
            "content": row["content"],
        },
        "fields": [field for field in row["fields"] if field.get("field")],
    }


class ConsentChannel(BaseModel):
    channel: Literal["email", "sms", "phone", "whatsapp"]
    status: Literal["granted"]


class ConsentCreate(BaseModel):
    subject: SubjectReference
    purpose_id: str = Field(alias="purposeId")
    notice_version_id: str = Field(alias="noticeVersionId")
    channels: list[ConsentChannel] = Field(min_length=1, max_length=4)
    field_categories: list[str] = Field(default_factory=list, alias="fieldCategories")
    affirmative_action: str = Field(alias="affirmativeAction", min_length=3, max_length=200)
    source: str = Field(min_length=2, max_length=100)
    idempotency_key: str = Field(alias="idempotencyKey", min_length=8, max_length=100)


def _consent_prerequisites(purpose_id: str, notice_version_id: str) -> bool:
    return bool(
        _read(
            """
            MATCH (purpose:ProcessingPurpose {purposeId: $purposeId, status: 'active'})
                  -[:HAS_NOTICE_VERSION]->(notice:NoticeVersion {noticeVersionId: $noticeVersionId, status: 'active'})
            WHERE notice.effectiveFrom <= datetime()
            RETURN purpose.purposeId AS purposeId LIMIT 1
            """,
            {"purposeId": purpose_id, "noticeVersionId": notice_version_id},
        )
    )


def collection_fields_allowed(purpose_id: str, fields: list[str]) -> tuple[bool, list[str]]:
    requested = sorted({str(field).strip() for field in fields if str(field).strip()})
    if not requested:
        return True, []
    rows = _read(
        """
        MATCH (purpose:ProcessingPurpose {purposeId: $purposeId, status: 'active'})
        WHERE purpose.counselDecision = 'approved'
        WITH purpose ORDER BY purpose.version DESC LIMIT 1
        OPTIONAL MATCH (purpose)-[:HAS_FIELD_POLICY]->(policy:DataFieldPolicy)
        WHERE policy.field IN $fields
        RETURN collect(policy{.field, .collection, .counselDecision}) AS policies
        """,
        {"purposeId": purpose_id, "fields": requested},
    )
    policies = {
        str(item.get("field")): item
        for item in ((rows[0].get("policies") if rows else []) or [])
        if item.get("field")
    }
    denied = [
        field
        for field in requested
        if field not in policies
        or policies[field].get("counselDecision") != "approved"
        or policies[field].get("collection") == "prohibited"
    ]
    return not denied, denied


@router.post("/consents", status_code=201)
def record_consent(request: Request, payload: ConsentCreate):
    if not _consent_prerequisites(payload.purpose_id, payload.notice_version_id):
        return error_response(409, "NOTICE_OR_PURPOSE_INACTIVE", "Consent cannot be recorded for an inactive purpose or notice.", request_id=_request_id(request))
    try:
        subject_key = _subject_key(payload.subject)
    except ValueError:
        return error_response(400, "SUBJECT_REFERENCE_INVALID", "The subject reference is invalid.", request_id=_request_id(request))
    settings = get_settings()
    events = []
    for channel in payload.channels:
        idempotency_hash = keyed_hash(settings, "consent-idempotency", f"{payload.idempotency_key}:{channel.channel}")
        payload_hash = keyed_hash(settings, "consent-payload", json.dumps({"subjectKey": subject_key, "purposeId": payload.purpose_id, "noticeVersionId": payload.notice_version_id, "channel": channel.channel, "fieldCategories": sorted(set(payload.field_categories)), "affirmativeAction": payload.affirmative_action, "source": payload.source}, sort_keys=True, separators=(",", ":")))
        event_id = str(uuid4())
        rows = _write(
            """
            MERGE (event:ConsentEvent {idempotencyHash: $idempotencyHash})
            ON CREATE SET event.consentEventId = $consentEventId,
                          event.payloadHash = $payloadHash,
                          event.subjectKey = $subjectKey,
                          event.purposeId = $purposeId,
                          event.noticeVersionId = $noticeVersionId,
                          event.channel = $channel, event.status = 'granted',
                          event.fieldCategories = $fieldCategories,
                          event.affirmativeAction = $affirmativeAction,
                          event.source = $source, event.actorId = $actorId,
                          event.recordedAt = datetime()
            WITH event WHERE event.payloadHash = $payloadHash
            RETURN event.consentEventId AS consentEventId,
                   event.channel AS channel, event.status AS status,
                   toString(event.recordedAt) AS recordedAt
            """,
            {
                "idempotencyHash": idempotency_hash,
                "consentEventId": event_id,
                "payloadHash": payload_hash,
                "subjectKey": subject_key,
                "purposeId": payload.purpose_id,
                "noticeVersionId": payload.notice_version_id,
                "channel": channel.channel,
                "fieldCategories": sorted(set(payload.field_categories)),
                "affirmativeAction": payload.affirmative_action,
                "source": payload.source,
                "actorId": _principal_id(request),
            },
        )
        if not rows:
            return error_response(409, "IDEMPOTENCY_KEY_REUSED", "The idempotency key was already used for different consent data.", request_id=_request_id(request))
        events.append(rows[0])
    _audit(request, "consent_granted", "ConsentEvent", events[0]["consentEventId"], purpose_id=payload.purpose_id, fields=payload.field_categories)
    return {
        "contractVersion": CONTRACT_VERSION,
        "events": events,
        "current": {event["channel"]: event["status"] for event in events},
    }


class WithdrawalCreate(BaseModel):
    subject: SubjectReference
    purpose_id: str = Field(alias="purposeId")
    channels: list[Literal["email", "sms", "phone", "whatsapp"]] = Field(min_length=1)
    reason: str = Field(default="", max_length=500)
    source: str = Field(min_length=2, max_length=100)
    idempotency_key: str = Field(alias="idempotencyKey", min_length=8, max_length=100)


def _record_withdrawal(
    request: Request,
    *,
    subject_key: str,
    purpose_id: str,
    channels: list[str],
    reason: str,
    source: str,
    idempotency_key: str,
) -> dict:
    settings = get_settings()
    events = []
    for channel in sorted(set(channels)):
        idem = keyed_hash(settings, "withdrawal-idempotency", f"{idempotency_key}:{channel}")
        payload_hash = keyed_hash(settings, "withdrawal-payload", json.dumps({"subjectKey": subject_key, "purposeId": purpose_id, "channel": channel, "reason": reason, "source": source}, sort_keys=True, separators=(",", ":")))
        suppression_event_id = keyed_hash(settings, "suppression-event", idem)
        rows = _write(
            """
            MERGE (withdrawal:WithdrawalEvent {idempotencyHash: $idempotencyHash})
            ON CREATE SET withdrawal.withdrawalEventId = $withdrawalEventId,
                          withdrawal.payloadHash = $payloadHash,
                          withdrawal.subjectKey = $subjectKey,
                          withdrawal.purposeId = $purposeId,
                          withdrawal.channel = $channel,
                          withdrawal.reason = $reason,
                          withdrawal.source = $source,
                          withdrawal.actorId = $actorId,
                          withdrawal.recordedAt = datetime()
            WITH withdrawal WHERE withdrawal.payloadHash = $payloadHash
            MERGE (projection:ChannelSuppression {
              subjectKey: $subjectKey, purposeId: $purposeId, channel: $channel
            })
            ON CREATE SET projection.suppressionId = randomUUID(), projection.createdAt = datetime()
            SET projection.status = 'active', projection.updatedAt = datetime(),
                projection.latestWithdrawalEventId = withdrawal.withdrawalEventId
            MERGE (suppressionEvent:SuppressionEvent {suppressionEventId: $suppressionEventId})
            ON CREATE SET suppressionEvent.subjectKey = $subjectKey,
                          suppressionEvent.purposeId = $purposeId,
                          suppressionEvent.channel = $channel,
                          suppressionEvent.status = 'active',
                          suppressionEvent.source = $source,
                          suppressionEvent.withdrawalEventId = withdrawal.withdrawalEventId,
                          suppressionEvent.createdAt = datetime()
            RETURN withdrawal.withdrawalEventId AS withdrawalEventId,
                   withdrawal.channel AS channel,
                   toString(withdrawal.recordedAt) AS recordedAt
            """,
            {
                "idempotencyHash": idem,
                "withdrawalEventId": str(uuid4()),
                "payloadHash": payload_hash,
                "suppressionEventId": suppression_event_id,
                "subjectKey": subject_key,
                "purposeId": purpose_id,
                "channel": channel,
                "reason": reason,
                "source": source,
                "actorId": _principal_id(request),
            },
        )
        if not rows:
            raise ValueError("IDEMPOTENCY_KEY_REUSED")
        events.append(rows[0])
    return {
        "contractVersion": CONTRACT_VERSION,
        "events": events,
        "current": {event["channel"]: "withdrawn" for event in events},
        "suppression": {event["channel"]: "active" for event in events},
    }


@router.post("/withdrawals")
def record_withdrawal(request: Request, payload: WithdrawalCreate):
    try:
        subject_key = _subject_key(payload.subject)
    except ValueError:
        return error_response(400, "SUBJECT_REFERENCE_INVALID", "The subject reference is invalid.", request_id=_request_id(request))
    try:
        result = _record_withdrawal(
            request,
            subject_key=subject_key,
            purpose_id=payload.purpose_id,
            channels=list(payload.channels),
            reason=payload.reason,
            source=payload.source,
            idempotency_key=payload.idempotency_key,
        )
    except ValueError:
        return error_response(409, "IDEMPOTENCY_KEY_REUSED", "The idempotency key was already used for different withdrawal data.", request_id=_request_id(request))
    _audit(request, "consent_withdrawn", "WithdrawalEvent", result["events"][0]["withdrawalEventId"], purpose_id=payload.purpose_id)
    return result


def make_unsubscribe_token(subject_key: str, purpose_id: str, channel: str) -> str:
    return encrypt_short_secret(
        get_settings(),
        json.dumps(
            {"subjectKey": subject_key, "purposeId": purpose_id, "channel": channel},
            separators=(",", ":"),
        ),
    )


class UnsubscribeCreate(BaseModel):
    token: str = Field(min_length=20, max_length=4000)
    idempotency_key: str = Field(alias="idempotencyKey", min_length=8, max_length=100)


@router.post("/unsubscribe")
def unsubscribe(request: Request, payload: UnsubscribeCreate):
    ip = str(request.client.host if request.client else "")
    allowed, retry_after = rate_limiter.allow(f"unsubscribe:{ip}", limit=30, window_seconds=600)
    if not allowed:
        return error_response(429, "RATE_LIMITED", "Too many requests. Try again later.", request_id=_request_id(request), retryable=True, headers={"Retry-After": str(retry_after)})
    try:
        decoded = json.loads(decrypt_short_secret(get_settings(), payload.token))
        subject_key = str(decoded["subjectKey"])
        purpose_id = str(decoded["purposeId"])
        channel = str(decoded["channel"])
        if channel not in {"email", "sms", "phone", "whatsapp"}:
            raise ValueError
        _record_withdrawal(
            request,
            subject_key=subject_key,
            purpose_id=purpose_id,
            channels=[channel],
            reason="unsubscribe",
            source="unsubscribe",
            idempotency_key=payload.idempotency_key,
        )
    except Exception:
        # The public response deliberately does not disclose token validity.
        pass
    return {"contractVersion": CONTRACT_VERSION, "accepted": True}


def is_channel_suppressed(address_type: str, address: str, purpose_id: str, channel: str) -> bool:
    try:
        reference = SubjectReference(address=SubjectAddress(type=address_type, value=address))
        subject_key = _subject_key(reference)
    except (ValueError, TypeError):
        return True
    return bool(
        _read(
            """
            MATCH (projection:ChannelSuppression {
              subjectKey: $subjectKey, purposeId: $purposeId,
              channel: $channel, status: 'active'
            }) RETURN projection.suppressionId AS suppressionId LIMIT 1
            """,
            {"subjectKey": subject_key, "purposeId": purpose_id, "channel": channel},
        )
    )


def has_active_channel_consent(address_type: str, address: str, purpose_id: str, channel: str) -> bool:
    """Return true only for explicit consent recorded after the latest withdrawal."""
    try:
        subject_key = _subject_key(SubjectReference(address=SubjectAddress(type=address_type, value=address)))
    except (ValueError, TypeError):
        return False
    rows = _read(
        """
        OPTIONAL MATCH (consent:ConsentEvent {
          subjectKey: $subjectKey, purposeId: $purposeId,
          channel: $channel, status: 'granted'
        })
        WITH max(consent.recordedAt) AS consentAt
        OPTIONAL MATCH (withdrawal:WithdrawalEvent {
          subjectKey: $subjectKey, purposeId: $purposeId, channel: $channel
        })
        RETURN consentAt, max(withdrawal.recordedAt) AS withdrawalAt
        """,
        {"subjectKey": subject_key, "purposeId": purpose_id, "channel": channel},
    )
    if not rows or rows[0].get("consentAt") is None:
        return False
    withdrawal_at = rows[0].get("withdrawalAt")
    return withdrawal_at is None or rows[0]["consentAt"] > withdrawal_at


@router.get("/subjects/{subject_id}/preferences")
def subject_preferences(subject_id: str):
    subject_key = _subject_key(SubjectReference(subjectId=subject_id))
    rows = _read(
        """
        MATCH (projection:ChannelSuppression {subjectKey: $subjectKey})
        RETURN projection.purposeId AS purposeId, projection.channel AS channel,
               projection.status AS status, toString(projection.updatedAt) AS updatedAt
        """,
        {"subjectKey": subject_key},
    )
    purposes: dict[str, dict] = {}
    for row in rows:
        purpose = purposes.setdefault(row["purposeId"], {"purposeId": row["purposeId"], "channels": {}})
        purpose["channels"][row["channel"]] = {
            "consent": "withdrawn",
            "suppressed": row["status"] == "active",
            "updatedAt": row["updatedAt"],
        }
    return {"contractVersion": CONTRACT_VERSION, "purposes": list(purposes.values())}


RIGHTS_TYPES = {"access", "copy", "correction", "deletion", "blocking", "portability", "withdrawal", "appeal"}


def _add_working_days(value: datetime, days: int) -> datetime:
    current = value
    remaining = int(days)
    while remaining:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


class RightsRequestCreate(BaseModel):
    request_type: str = Field(alias="requestType")
    subject: SubjectReference
    details: str = Field(default="", max_length=4000)
    locale: Literal["ka", "en"] = "ka"
    idempotency_key: str = Field(alias="idempotencyKey", min_length=8, max_length=100)


@router.post("/rights-requests", status_code=202)
def create_rights_request(request: Request, payload: RightsRequestCreate):
    request_type = payload.request_type.strip().lower()
    if request_type not in RIGHTS_TYPES:
        return error_response(400, "RIGHTS_REQUEST_TYPE_INVALID", "The rights request type is invalid.", request_id=_request_id(request))
    ip = str(request.client.host if request.client else "")
    allowed, retry_after = rate_limiter.allow(f"rights:{ip}", limit=8, window_seconds=3600)
    if not allowed:
        return error_response(429, "RATE_LIMITED", "Too many requests. Try again later.", request_id=_request_id(request), retryable=True, headers={"Retry-After": str(retry_after)})
    try:
        subject_key = _subject_key(payload.subject)
    except ValueError:
        return error_response(400, "SUBJECT_REFERENCE_INVALID", "The subject reference is invalid.", request_id=_request_id(request))
    settings = get_settings()
    receipt_token = secrets.token_urlsafe(36)
    received = _now()
    due = _add_working_days(received, 10)
    idempotency_hash = keyed_hash(settings, "rights-idempotency", payload.idempotency_key)
    payload_hash = keyed_hash(settings, "rights-payload", json.dumps({"requestType": request_type, "subjectKey": subject_key, "details": payload.details, "locale": payload.locale}, sort_keys=True, separators=(",", ":")))
    request_id = str(uuid4())
    rows = _write(
        """
        MERGE (dsr:DataSubjectRequest {idempotencyHash: $idempotencyHash})
        ON CREATE SET dsr.requestId = $requestId, dsr.requestType = $requestType,
                      dsr.payloadHash = $payloadHash,
                      dsr.subjectKey = $subjectKey,
                      dsr.detailsCiphertext = $detailsCiphertext,
                      dsr.locale = $locale,
                      dsr.status = 'pending-verification',
                      dsr.identityVerificationState = 'pending',
                      dsr.receivedAt = datetime($receivedAt),
                      dsr.dueAt = datetime($dueAt),
                      dsr.receiptTokenHash = $receiptTokenHash,
                      dsr.receiptTokenCiphertext = $receiptTokenCiphertext,
                      dsr.createdAt = datetime()
        WITH dsr WHERE dsr.payloadHash = $payloadHash
        RETURN dsr.requestId AS requestId, dsr.status AS status,
               toString(dsr.receivedAt) AS receivedAt,
               toString(dsr.dueAt) AS dueAt,
               dsr.receiptTokenCiphertext AS receiptTokenCiphertext
        """,
        {
            "idempotencyHash": idempotency_hash,
            "requestId": request_id,
            "payloadHash": payload_hash,
            "requestType": request_type,
            "subjectKey": subject_key,
            "detailsCiphertext": encrypt_short_secret(settings, payload.details) if payload.details else "",
            "locale": payload.locale,
            "receivedAt": _iso(received),
            "dueAt": _iso(due),
            "receiptTokenHash": keyed_hash(settings, "rights-receipt", receipt_token),
            "receiptTokenCiphertext": encrypt_short_secret(settings, receipt_token),
        },
    )
    if not rows:
        return error_response(409, "IDEMPOTENCY_KEY_REUSED", "The idempotency key was already used for a different rights request.", request_id=_request_id(request))
    row = rows[0]
    stored_receipt_token = decrypt_short_secret(settings, str(row.pop("receiptTokenCiphertext") or ""))
    _audit(request, "rights_request_created", "DataSubjectRequest", row["requestId"])
    return {"contractVersion": CONTRACT_VERSION, "accepted": True, **row, "receiptToken": stored_receipt_token}


@router.get("/rights-requests/{request_id}")
def get_rights_request(request: Request, request_id: str, receipt_token: str = Query(..., alias="receiptToken")):
    receipt_hash = keyed_hash(get_settings(), "rights-receipt", receipt_token)
    rows = _read(
        """
        MATCH (dsr:DataSubjectRequest {requestId: $requestId, receiptTokenHash: $receiptTokenHash})
        RETURN dsr.requestId AS requestId, dsr.requestType AS requestType,
               dsr.status AS status, toString(dsr.receivedAt) AS receivedAt,
               toString(dsr.dueAt) AS dueAt, toString(dsr.completedAt) AS completedAt,
               coalesce(dsr.outcomeCode, '') AS outcomeCode,
               coalesce(dsr.outcomeSummary, '') AS outcomeSummary,
               coalesce(dsr.partialDenials, []) AS partialDenials
        """,
        {"requestId": request_id, "receiptTokenHash": receipt_hash},
    )
    if not rows:
        return error_response(404, "RIGHTS_REQUEST_NOT_FOUND", "The request could not be found.", request_id=_request_id(request))
    row = rows[0]
    return {
        "contractVersion": CONTRACT_VERSION,
        **{key: value for key, value in row.items() if key not in {"outcomeCode", "outcomeSummary"}},
        "outcome": {"code": row["outcomeCode"] or None, "summary": row["outcomeSummary"] or None},
    }


class RightsReviewCreate(BaseModel):
    status: Literal["open", "blocked", "in-progress", "partially-completed", "completed", "denied", "appealed"]
    outcome_code: str = Field(default="", alias="outcomeCode", max_length=100)
    outcome_summary: str = Field(default="", alias="outcomeSummary", max_length=1000)
    partial_denials: list[dict] = Field(default_factory=list, alias="partialDenials")
    rationale: str = Field(min_length=3, max_length=2000)


@router.post("/rights-requests/{request_id}/reviews", status_code=201)
def review_rights_request(request: Request, request_id: str, payload: RightsReviewCreate):
    review_id = str(uuid4())
    rows = _write(
        """
        MATCH (dsr:DataSubjectRequest {requestId: $requestId})
        CREATE (review:DataSubjectRequestReview {
          reviewId: $reviewId, status: $status,
          outcomeCode: $outcomeCode, outcomeSummary: $outcomeSummary,
          partialDenialsJson: $partialDenialsJson,
          rationale: $rationale, reviewedBy: $reviewedBy, createdAt: datetime()
        })
        MERGE (dsr)-[:HAS_DSR_REVIEW]->(review)
        SET dsr.status = $status, dsr.outcomeCode = $outcomeCode,
            dsr.outcomeSummary = $outcomeSummary,
            dsr.partialDenials = $partialDenials,
            dsr.updatedAt = datetime()
        FOREACH (_ IN CASE WHEN $status IN ['completed', 'denied'] THEN [1] ELSE [] END |
          SET dsr.completedAt = datetime()
        )
        RETURN review.reviewId AS reviewId, review.status AS status,
               toString(review.createdAt) AS createdAt
        """,
        {
            "requestId": request_id,
            "reviewId": review_id,
            "status": payload.status,
            "outcomeCode": payload.outcome_code,
            "outcomeSummary": payload.outcome_summary,
            "partialDenials": payload.partial_denials,
            "partialDenialsJson": json.dumps(payload.partial_denials),
            "rationale": payload.rationale,
            "reviewedBy": _principal_id(request),
        },
    )
    if not rows:
        return error_response(404, "RIGHTS_REQUEST_NOT_FOUND", "The request could not be found.", request_id=_request_id(request))
    _audit(request, "rights_request_reviewed", "DataSubjectRequest", request_id)
    return {"contractVersion": CONTRACT_VERSION, **rows[0]}


RETENTION_LABELS = {
    "crm-person": "Person",
    "dd-evidence": "InvestigationEvidence",
    "social-evidence": "InvestigationEvidence",
    "dd-statement": "InvestigationStatement",
}


class RetentionJobCreate(BaseModel):
    purpose_id: str = Field(alias="purposeId")
    category: str
    dry_run: bool = Field(default=True, alias="dryRun")
    as_of: str | None = Field(default=None, alias="asOf")


@router.get("/retention/status")
def retention_status(subject_id: str = Query(..., alias="subjectId")):
    subject_key = _subject_key(SubjectReference(subjectId=subject_id))
    policies = _read("MATCH (p:RetentionPolicy {status: 'active'}) RETURN p{.*} AS policy ORDER BY p.purposeId, p.category")
    holds = _read(
        """
        MATCH (hold:LegalHold {subjectKey: $subjectKey})
        WHERE hold.releasedAt IS NULL
        RETURN hold.holdId AS holdId, hold.purposeId AS purposeId,
               hold.category AS category, toString(hold.createdAt) AS createdAt
        """,
        {"subjectKey": subject_key},
    )
    return {"contractVersion": CONTRACT_VERSION, "policies": [row["policy"] for row in policies], "holds": holds, "pendingJobs": []}


@router.post("/retention/jobs", status_code=202)
def create_retention_job(request: Request, payload: RetentionJobCreate):
    label = RETENTION_LABELS.get(payload.category)
    if not label:
        return error_response(400, "RETENTION_CATEGORY_INVALID", "The retention category is not supported.", request_id=_request_id(request))
    as_of = payload.as_of or _iso()
    holds = _read(
        """
        MATCH (hold:LegalHold)
        WHERE hold.releasedAt IS NULL
          AND ($purposeId = '' OR hold.purposeId = $purposeId)
          AND ($category = '' OR hold.category = $category)
        RETURN count(hold) AS count
        """,
        {"purposeId": payload.purpose_id, "category": payload.category},
    )
    count_rows = _read(
        f"""
        MATCH (record:{label})
        WHERE record.retentionExpiresAt IS NOT NULL
          AND datetime(record.retentionExpiresAt) <= datetime($asOf)
          AND ($purposeId = '' OR record.purposeId = $purposeId)
        RETURN count(record) AS count
        """,
        {"asOf": as_of, "purposeId": payload.purpose_id},
    )
    planned = int(count_rows[0]["count"] if count_rows else 0)
    hold_count = int(holds[0]["count"] if holds else 0)
    if not payload.dry_run and not get_settings().retention_execution_enabled:
        return error_response(403, "RETENTION_EXECUTION_DISABLED", "Destructive retention execution is disabled pending approved policy.", request_id=_request_id(request))
    if not payload.dry_run and hold_count:
        return error_response(409, "LEGAL_HOLD_ACTIVE", "A legal hold prevents retention execution.", request_id=_request_id(request))
    job_id = str(uuid4())
    status = "dry-run-completed" if payload.dry_run else "completed"
    affected = 0
    if not payload.dry_run and payload.category == "crm-person":
        rows = _write(
            """
            MATCH (record:Person)
            WHERE record.retentionExpiresAt IS NOT NULL
              AND datetime(record.retentionExpiresAt) <= datetime($asOf)
              AND ($purposeId = '' OR record.purposeId = $purposeId)
            SET record.email = null, record.phone = null, record.address = null,
                record.personalId = null, record.dateOfBirth = null,
                record.socialMedia = null, record.partyDetails = null,
                record.wasPartyMember = null, record.topicsOfInterest = [],
                record.tombstonedAt = datetime(),
                record.retentionJobId = $jobId
            RETURN count(record) AS count
            """,
            {"asOf": as_of, "purposeId": payload.purpose_id, "jobId": job_id},
        )
        affected = int(rows[0]["count"] if rows else 0)
    elif not payload.dry_run:
        return error_response(409, "RETENTION_EXECUTION_UNSUPPORTED", "Only dependency-safe CRM anonymization is currently executable; use dryRun for this category.", request_id=_request_id(request))
    _write(
        """
        CREATE (job:RetentionJob {
          jobId: $jobId, purposeId: $purposeId, category: $category,
          dryRun: $dryRun, asOf: datetime($asOf), status: $status,
          plannedCount: $plannedCount, affectedCount: $affectedCount,
          holdsExcluded: $holdsExcluded, requestedBy: $requestedBy,
          createdAt: datetime(), completedAt: datetime()
        })
        """,
        {"jobId": job_id, "purposeId": payload.purpose_id, "category": payload.category, "dryRun": payload.dry_run, "asOf": as_of, "status": status, "plannedCount": planned, "affectedCount": affected, "holdsExcluded": hold_count, "requestedBy": _principal_id(request)},
    )
    _audit(request, "retention_job", "RetentionJob", job_id, purpose_id=payload.purpose_id)
    return {"contractVersion": CONTRACT_VERSION, "jobId": job_id, "status": status, "dryRun": payload.dry_run, "plannedCount": planned, "affectedCount": affected, "holdsExcluded": hold_count, "destructiveExecutionEnabled": get_settings().retention_execution_enabled}


class LegalHoldCreate(BaseModel):
    subject_id: str | None = Field(default=None, alias="subjectId")
    purpose_id: str = Field(default="", alias="purposeId")
    category: str = ""
    reason: str = Field(min_length=3, max_length=1000)
    valid_until: str | None = Field(default=None, alias="validUntil")


@router.post("/legal-holds", status_code=201)
def create_legal_hold(request: Request, payload: LegalHoldCreate):
    hold_id = str(uuid4())
    subject_key = _subject_key(SubjectReference(subjectId=payload.subject_id)) if payload.subject_id else ""
    _write(
        """
        CREATE (hold:LegalHold {
          holdId: $holdId, subjectKey: $subjectKey,
          purposeId: $purposeId, category: $category,
          reason: $reason, validUntil: CASE WHEN $validUntil IS NULL THEN null ELSE datetime($validUntil) END,
          createdBy: $createdBy, createdAt: datetime(), releasedAt: null
        })
        CREATE (event:LegalHoldEvent {
          eventId: randomUUID(), holdId: $holdId, action: 'created',
          actorId: $createdBy, createdAt: datetime()
        })
        """,
        {"holdId": hold_id, "subjectKey": subject_key, "purposeId": payload.purpose_id, "category": payload.category, "reason": payload.reason, "validUntil": payload.valid_until, "createdBy": _principal_id(request)},
    )
    _audit(request, "legal_hold_created", "LegalHold", hold_id, purpose_id=payload.purpose_id)
    return {"contractVersion": CONTRACT_VERSION, "holdId": hold_id, "status": "active"}


@router.post("/legal-holds/{hold_id}/release")
def release_legal_hold(request: Request, hold_id: str):
    rows = _write(
        """
        MATCH (hold:LegalHold {holdId: $holdId})
        WHERE hold.releasedAt IS NULL
        SET hold.releasedAt = datetime(), hold.releasedBy = $actorId
        CREATE (event:LegalHoldEvent {
          eventId: randomUUID(), holdId: $holdId, action: 'released',
          actorId: $actorId, createdAt: datetime()
        })
        RETURN toString(hold.releasedAt) AS releasedAt
        """,
        {"holdId": hold_id, "actorId": _principal_id(request)},
    )
    if not rows:
        return error_response(404, "LEGAL_HOLD_NOT_FOUND", "The legal hold could not be found.", request_id=_request_id(request))
    _audit(request, "legal_hold_released", "LegalHold", hold_id)
    return {"contractVersion": CONTRACT_VERSION, "holdId": hold_id, "status": "released", **rows[0]}
