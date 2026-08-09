from __future__ import annotations

import copy
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, root_validator, validator

from .compliance import collection_fields_allowed
from .core.auth_store import keyed_hash
from .core.config import get_settings
from .core.errors import error_response
from .db import get_active_database, get_driver


WORKFLOW_CONTRACT_VERSION = "dd-workflow.v2"
MUTATION_CONTRACT_VERSION = "dd-workflow.v2-be1.0"
FEATURE_FLAG = "FS_DD_WORKFLOW_V2_ENABLED"
DEFAULT_PURPOSE_ID = "dd-investigation"
STAGES = (
    "intake",
    "identity",
    "sources",
    "investigation",
    "findings",
    "review",
    "decision",
    "monitoring",
    "closed",
)
NEXT_STAGE = dict(zip(STAGES, STAGES[1:]))
TRUTHY = {"1", "true", "yes", "on"}
PERSON_IDENTIFIER_MARKERS = (
    "personal",
    "national",
    "passport",
    "identity_card",
    "birth",
    "social_security",
)
DEFAULT_IDENTIFIER_TYPES = {
    "company_registration_number",
    "lei",
    "imo",
    "aircraft_registration",
    "tender_id",
    "contract_id",
}
TRANSITION_CODES = {
    "intake": "complete_intake",
    "identity": "complete_identity",
    "sources": "complete_sources",
    "investigation": "complete_investigation",
    "findings": "submit_findings_for_review",
    "review": "complete_review",
    "decision": "start_monitoring",
    "monitoring": "close_monitoring",
}


def workflow_v2_enabled() -> bool:
    return str(os.getenv(FEATURE_FLAG, "")).strip().casefold() in TRUTHY


class StrictModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class AttestationRequest(StrictModel):
    attested: bool

    @validator("attested")
    def must_be_affirmative(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("attested must be true")
        return value


class AssignmentInput(StrictModel):
    actor_id: Optional[str] = Field(default=None, alias="actorId", max_length=120)
    display_name: Optional[str] = Field(default=None, alias="displayName", max_length=200)
    team_id: Optional[str] = Field(default=None, alias="teamId", max_length=120)

    @root_validator(skip_on_failure=True)
    def at_least_one_assignment_value(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if not any(str(values.get(key) or "").strip() for key in ("actor_id", "display_name", "team_id")):
            raise ValueError("At least one assignment field is required.")
        return values


class IdentifierInput(StrictModel):
    type: str = Field(min_length=2, max_length=80)
    value: str = Field(min_length=1, max_length=160)
    issuer: str = Field(min_length=1, max_length=120)
    country: Optional[str] = Field(min_length=2, max_length=3)

    @validator("type", "issuer")
    def normalize_controlled_text(cls, value: str) -> str:
        return str(value).strip()

    @validator("country")
    def normalize_country(cls, value: Optional[str]) -> Optional[str]:
        text = str(value or "").strip().upper()
        return text or None

    @validator("value")
    def reject_controls(cls, value: str) -> str:
        text = str(value).strip()
        if not text or any(ord(char) < 32 for char in text):
            raise ValueError("Identifier value is invalid.")
        return text


class AliasInput(StrictModel):
    value: str = Field(min_length=1, max_length=300)
    script: str = Field(pattern="^(Geor|Latn|Cyrl|other)$")
    language: Optional[str] = Field(max_length=35)
    type: str = Field(pattern="^(official|former|transliteration|social_display|nickname|also_known_as|other)$")

    @validator("value")
    def preserve_trimmed_alias(cls, value: str) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError("Alias is required.")
        return text


class DateRangeInput(StrictModel):
    from_date: Optional[date] = Field(alias="from")
    to_date: Optional[date] = Field(alias="to")

    @root_validator(skip_on_failure=True)
    def ordered_dates(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        start = values.get("from_date")
        end = values.get("to_date")
        if start and end and start > end:
            raise ValueError("dateRange.from must not be after dateRange.to")
        return values


class ConflictDeclarationInput(StrictModel):
    status: str = Field(pattern="^(unknown|declared_none|declared_conflict)$")
    details: Optional[str] = Field(max_length=2000)
    attestation: Optional[AttestationRequest]

    @root_validator(skip_on_failure=True)
    def attestation_matches_status(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        status = values.get("status")
        attestation = values.get("attestation")
        details = str(values.get("details") or "").strip()
        if status == "unknown" and attestation is not None:
            raise ValueError("Unknown conflict status cannot be attested.")
        if status in {"declared_none", "declared_conflict"} and attestation is None:
            raise ValueError("A conflict declaration attestation is required.")
        if status == "declared_conflict" and not details:
            raise ValueError("Conflict details are required when a conflict is declared.")
        return values


class PriorScreeningInput(StrictModel):
    status: str = Field(pattern="^(unknown|none|available)$")
    refs: List[str] = Field(max_items=100)


class IntakeInput(StrictModel):
    purpose: str = Field(pattern="^(vendor_onboarding|partner_review|counterparty_review|appointment_review|grant_review|conflict_check|investigative_research|other)$")
    purpose_details: Optional[str] = Field(alias="purposeDetails", max_length=4000)
    intended_decision: str = Field(alias="intendedDecision", pattern="^(approve|approve_with_conditions|decline|escalate|monitor|inform_only|other)$")
    requestor: AssignmentInput
    owner: Optional[AssignmentInput]
    subject_category: str = Field(alias="subjectCategory", pattern="^(person|organization|public_body|asset|vessel|other)$")
    jurisdictions: List[str] = Field(max_items=50)
    date_range: DateRangeInput = Field(alias="dateRange")
    identifiers: List[IdentifierInput] = Field(max_items=100)
    aliases: List[AliasInput] = Field(min_items=1, max_items=200)
    diligence_depth: str = Field(alias="diligenceDepth", pattern="^(basic|standard|enhanced)$")
    processing_purpose_id: str = Field(alias="processingPurposeId", min_length=2, max_length=100)
    lawful_basis_ref: str = Field(alias="lawfulBasisRef", min_length=2, max_length=300)
    deadline: Optional[datetime]
    retention_class: str = Field(alias="retentionClass", min_length=2, max_length=120)
    conflict_declaration: ConflictDeclarationInput = Field(alias="conflictDeclaration")
    prior_screening: PriorScreeningInput = Field(alias="priorScreening")

    @validator("jurisdictions")
    def normalize_jurisdictions(cls, value: List[str]) -> List[str]:
        normalized = [str(item).strip().upper() for item in value]
        if any(not re.fullmatch(r"[A-Z]{2,3}", item) for item in normalized):
            raise ValueError("Jurisdictions must be ISO-like two or three letter codes.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Jurisdictions must be unique.")
        return normalized


class CreateCaseRequest(StrictModel):
    intake: IntakeInput
    preparation_attestation: AttestationRequest = Field(alias="preparationAttestation")


class IntakeReplaceRequest(StrictModel):
    expected_workflow_version: int = Field(alias="expectedWorkflowVersion", ge=1)
    intake: IntakeInput
    preparation_attestation: AttestationRequest = Field(alias="preparationAttestation")


class DuplicateScanRequest(StrictModel):
    expected_workflow_version: int = Field(alias="expectedWorkflowVersion", ge=1)


class DuplicateDecisionRequest(StrictModel):
    expected_workflow_version: int = Field(alias="expectedWorkflowVersion", ge=1)
    decision: str = Field(pattern="^(continue_new|link_existing|dismiss_duplicate)$")
    rationale: str = Field(min_length=1, max_length=4000)
    attestation: AttestationRequest

    @validator("rationale")
    def trim_rationale(cls, value: str) -> str:
        return str(value).strip()


class WaiverInput(StrictModel):
    blocker_code: str = Field(alias="blockerCode", pattern=r"^DD_[A-Z0-9_]+$")
    reason: str = Field(min_length=5, max_length=2000)
    attestation: AttestationRequest
    expires_at: Optional[datetime] = Field(alias="expiresAt")

    @validator("reason")
    def trim_reason(cls, value: str) -> str:
        return str(value).strip()


class TransitionAttestations(StrictModel):
    prepared_by: Optional[AttestationRequest] = Field(default=None, alias="preparedBy")
    reviewed_by: Optional[AttestationRequest] = Field(default=None, alias="reviewedBy")


class TransitionRequest(StrictModel):
    expected_workflow_version: int = Field(alias="expectedWorkflowVersion", ge=1)
    transition_code: str = Field(alias="transitionCode", min_length=3, max_length=80)
    to_stage: str = Field(alias="toStage", pattern="^(intake|identity|sources|investigation|findings|review|decision|monitoring|closed)$")
    waivers: List[WaiverInput] = Field(max_items=30)
    attestations: TransitionAttestations

    @root_validator(skip_on_failure=True)
    def unique_waiver_codes(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        codes = [waiver.blocker_code for waiver in values.get("waivers") or []]
        if len(codes) != len(set(codes)):
            raise ValueError("Waiver blocker codes must be unique.")
        return values


@dataclass(frozen=True)
class WorkflowPolicy:
    retention_classes: Dict[str, str]
    allowed_identifier_types: frozenset[str]
    coverage_threshold: float
    policy_version: int

    @classmethod
    def from_environment(cls) -> "WorkflowPolicy":
        retention_classes: Dict[str, str] = {"dd-standard-provisional": "provisional"}
        raw_retention = str(os.getenv("FS_DD_WORKFLOW_V2_RETENTION_CLASSES_JSON", "")).strip()
        if raw_retention:
            parsed = json.loads(raw_retention)
            retention_classes = {
                str(item["id"]): str(item.get("status") or "provisional")
                for item in parsed
                if isinstance(item, dict) and item.get("id")
            }
        raw_types = str(os.getenv("FS_DD_WORKFLOW_V2_ALLOWED_IDENTIFIER_TYPES", "")).strip()
        identifier_types = {
            item.strip() for item in raw_types.split(",") if item.strip()
        } or set(DEFAULT_IDENTIFIER_TYPES)
        threshold = float(os.getenv("FS_DD_WORKFLOW_V2_MINIMUM_COVERAGE", "0.75"))
        return cls(
            retention_classes=retention_classes,
            allowed_identifier_types=frozenset(identifier_types),
            coverage_threshold=max(0.0, min(1.0, threshold)),
            policy_version=max(1, int(os.getenv("FS_DD_WORKFLOW_V2_POLICY_VERSION", "1"))),
        )


class WorkflowDomainError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def _now_iso(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _normalized_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _masked_name(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "Restricted synthetic subject"
    if len(text) <= 2:
        return "•" * len(text)
    return f"{text[0]}{'•' * min(8, max(3, len(text) - 2))}{text[-1]}"


def _masked_identifier(value: str) -> str:
    text = str(value or "").strip()
    suffix = text[-4:] if text else ""
    return f"••••{suffix}" if suffix else "Restricted"


def _access(purpose_id: Optional[str], *, masked: Optional[List[str]] = None, omitted: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "purposeId": purpose_id or None,
        "policy": "deny-by-default",
        "omittedFields": omitted or [],
        "maskedFields": masked or [],
    }


def _actor_attestation(actor: Dict[str, Any], statement_code: str, now: str) -> Dict[str, Any]:
    return {
        "actor": {
            "actorId": actor["actorId"],
            "displayName": actor.get("displayName"),
        },
        "method": actor["method"],
        "statementCode": statement_code,
        "attestedAt": now,
    }


def _subject_aliases_from_legacy(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    aliases: List[Dict[str, Any]] = []
    seen = set()
    for value, script, language, alias_type in (
        (row.get("subjectGeorgian"), "Geor", "ka", "official"),
        (row.get("subjectEnglish"), "Latn", "en", "transliteration"),
        (row.get("subject"), "other", None, "also_known_as"),
    ):
        text = str(value or "").strip()
        key = _normalized_name(text)
        if not text or not key or key in seen:
            continue
        seen.add(key)
        aliases.append({"value": text, "script": script, "language": language, "type": alias_type})
    return aliases or [{"value": "Legacy subject unavailable", "script": "other", "language": None, "type": "other"}]


def initial_projection(row: Dict[str, Any], *, now: Optional[str] = None) -> Dict[str, Any]:
    timestamp = now or _now_iso()
    legacy_status = str(row.get("status") or "").casefold()
    if legacy_status == "draft":
        stage, lifecycle = "intake", "active"
    elif legacy_status == "review":
        stage, lifecycle = "review", "active"
    elif legacy_status == "decided":
        stage, lifecycle = "decision", "active"
    elif legacy_status == "closed":
        stage, lifecycle = "closed", "closed"
    elif legacy_status == "archived":
        stage, lifecycle = "closed", "archived"
    else:
        stage, lifecycle = "sources", "active"
    subject_type = str(row.get("subjectType") or "").casefold()
    category = "organization" if subject_type in {"company", "organization"} else "person" if subject_type == "person" else "other"
    owner_text = str(row.get("owner") or "").strip()
    intake = {
        "purpose": "other",
        "purposeDetails": "Legacy purpose was not recorded; analyst review is required.",
        "intendedDecision": "other",
        "requestor": {"actorId": None, "displayName": "Legacy assignment unavailable", "teamId": None},
        "owner": {"actorId": None, "displayName": owner_text, "teamId": None} if owner_text else None,
        "subjectCategory": category,
        "jurisdictions": [],
        "dateRange": {"from": None, "to": None},
        "identifiers": [],
        "aliases": _subject_aliases_from_legacy(row),
        "diligenceDepth": "basic",
        "processingPurposeId": "legacy-unknown",
        "lawfulBasisRef": "legacy-unknown",
        "deadline": None,
        "retentionClass": "legacy-unknown",
        "conflictDeclaration": {"status": "unknown", "details": None, "attestedBy": None, "attestedAt": None},
        "priorScreening": {"status": "unknown", "refs": []},
    }
    completion = {
        current_stage: {
            "stage": current_stage,
            "state": "unknown",
            "completedAt": None,
            "actorAttestation": None,
        }
        for current_stage in STAGES
    }
    return {
        "caseId": str(row.get("caseId") or ""),
        "workflowVersion": int(row.get("ddWorkflowVersion") or 1),
        "stage": stage,
        "lifecycleStatus": lifecycle,
        "migrationNeedsReview": True,
        "archivedFromStage": None,
        "intake": intake,
        "duplicateCandidates": [],
        "completion": completion,
        "waivers": [],
        "createdAt": str(row.get("createdAt") or timestamp),
        "updatedAt": str(row.get("updatedAt") or timestamp),
        "legacyUnknownFields": [
            "purpose",
            "intendedDecision",
            "requestor",
            "jurisdictions",
            "processingPurposeId",
            "lawfulBasisRef",
            "retentionClass",
            "conflictDeclaration",
        ],
    }


def _projection_digest(state: Dict[str, Any]) -> str:
    visible = {
        key: state.get(key)
        for key in (
            "stage",
            "lifecycleStatus",
            "migrationNeedsReview",
            "archivedFromStage",
            "intake",
            "duplicateCandidates",
            "completion",
            "waivers",
        )
    }
    import hashlib

    return hashlib.sha256(_canonical_json(visible).encode("utf-8")).hexdigest()


def _completion_list(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    stored = state.get("completion") or {}
    return [
        copy.deepcopy(stored.get(stage))
        if stored.get(stage)
        else {"stage": stage, "state": "unknown", "completedAt": None, "actorAttestation": None}
        for stage in STAGES
    ]


def compute_blockers(state: Dict[str, Any], policy: WorkflowPolicy) -> List[Dict[str, Any]]:
    intake = state.get("intake") or {}
    blockers: List[Dict[str, Any]] = []

    def add(code: str, stage: str, message_key: str, *, waiver_policy: str = "forbidden", severity: str = "error", params: Optional[Dict[str, Any]] = None) -> None:
        blockers.append(
            {
                "code": code,
                "stage": stage,
                "severity": severity,
                "blocking": True,
                "messageKey": message_key,
                "params": params or {},
                "remediation": None,
                "waiverPolicy": waiver_policy,
            }
        )

    if intake.get("processingPurposeId") in {None, "", "legacy-unknown"} or intake.get("lawfulBasisRef") in {None, "", "legacy-unknown"}:
        add("DD_PURPOSE_AUTHORIZATION_REQUIRED", "intake", "dd.blocker.purpose_authorization_required")
    retention_class = str(intake.get("retentionClass") or "")
    retention_status = policy.retention_classes.get(retention_class)
    if retention_status != "active":
        add(
            "DD_RETENTION_POLICY_DECISION_REQUIRED",
            "intake",
            "dd.blocker.retention_policy_decision_required",
            params={"retentionClass": retention_class or None, "policyStatus": retention_status or "unknown"},
        )
    if (intake.get("conflictDeclaration") or {}).get("status") == "unknown":
        add("DD_CONFLICT_DECLARATION_REQUIRED", "intake", "dd.blocker.conflict_declaration_required")
    pending_candidates = [candidate for candidate in state.get("duplicateCandidates") or [] if candidate.get("state") == "pending"]
    if state.get("stage") == "identity" and pending_candidates:
        add(
            "DD_DUPLICATE_REVIEW_PENDING",
            "identity",
            "dd.blocker.duplicate_review_pending",
            waiver_policy="allowed",
            severity="warning",
            params={"candidateCount": len(pending_candidates)},
        )
    if state.get("stage") == "identity" and (intake.get("priorScreening") or {}).get("status") == "unknown":
        add(
            "DD_PRIOR_SCREENING_REVIEW_PENDING",
            "identity",
            "dd.blocker.prior_screening_review_pending",
            waiver_policy="allowed",
            severity="warning",
        )
    if state.get("stage") == "sources":
        add("DD_BE2_COVERAGE_NOT_AVAILABLE", "sources", "dd.blocker.be2_coverage_not_available")
    return blockers


def allowed_transitions(state: Dict[str, Any], blockers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    stage = str(state.get("stage") or "intake")
    target = NEXT_STAGE.get(stage)
    transition_code = TRANSITION_CODES.get(stage)
    if not target or not transition_code:
        return []
    relevant = [blocker for blocker in blockers if blocker["stage"] == stage and blocker["blocking"]]
    if any(blocker["waiverPolicy"] == "forbidden" for blocker in relevant):
        return []
    waiver_codes = [blocker["code"] for blocker in relevant if blocker["waiverPolicy"] == "allowed"]
    attestations = ["preparedBy"]
    if target in {"decision", "closed"}:
        attestations.append("reviewedBy")
    return [
        {
            "transitionCode": transition_code,
            "messageKey": f"dd.transition.{transition_code}",
            "params": {},
            "toStage": target,
            "availability": "requires_waivers" if waiver_codes else "allowed",
            "requiredWaiverCodes": waiver_codes,
            "requiredAttestations": attestations,
        }
    ]


class WorkflowStore:
    def load_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def list_cases(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def candidate_cases(self, case_id: str) -> List[Dict[str, Any]]:
        return [state for state in self.list_cases() if state.get("caseId") != case_id]

    def lookup_idempotency(self, operation_key: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def create_case(
        self,
        *,
        operation_key: str,
        body_hash: str,
        state: Dict[str, Any],
        events: List[Dict[str, Any]],
        response: Dict[str, Any],
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def commit(
        self,
        *,
        case_id: str,
        expected_version: int,
        operation_key: str,
        body_hash: str,
        state: Dict[str, Any],
        events: List[Dict[str, Any]],
        response: Dict[str, Any],
    ) -> Dict[str, Any]:
        raise NotImplementedError


class InMemoryWorkflowStore(WorkflowStore):
    """Synthetic test store; runtime uses Neo4jWorkflowStore."""

    def __init__(self, cases: Optional[Iterable[Dict[str, Any]]] = None):
        self.cases = {str(case["caseId"]): copy.deepcopy(case) for case in (cases or [])}
        self.idempotency: Dict[str, Dict[str, Any]] = {}
        self.events: List[Dict[str, Any]] = []

    def load_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        state = self.cases.get(case_id)
        return copy.deepcopy(state) if state else None

    def list_cases(self) -> List[Dict[str, Any]]:
        return [copy.deepcopy(state) for state in self.cases.values()]

    def lookup_idempotency(self, operation_key: str) -> Optional[Dict[str, Any]]:
        value = self.idempotency.get(operation_key)
        return copy.deepcopy(value) if value else None

    def _check_idempotency(self, operation_key: str, body_hash: str) -> Optional[Dict[str, Any]]:
        existing = self.idempotency.get(operation_key)
        if not existing:
            return None
        if existing["bodyHash"] != body_hash:
            raise WorkflowDomainError(
                409,
                "DD_IDEMPOTENCY_KEY_REUSED",
                "The idempotency key was already used with a different request.",
            )
        replay = copy.deepcopy(existing["response"])
        replay["idempotentReplay"] = True
        return replay

    def create_case(self, *, operation_key: str, body_hash: str, state: Dict[str, Any], events: List[Dict[str, Any]], response: Dict[str, Any]) -> Dict[str, Any]:
        replay = self._check_idempotency(operation_key, body_hash)
        if replay:
            return replay
        if state["caseId"] in self.cases:
            raise WorkflowDomainError(409, "DD_CASE_ALREADY_EXISTS", "The case already exists.")
        self.cases[state["caseId"]] = copy.deepcopy(state)
        self.events.extend(copy.deepcopy(events))
        self.idempotency[operation_key] = {"bodyHash": body_hash, "response": copy.deepcopy(response)}
        return copy.deepcopy(response)

    def commit(self, *, case_id: str, expected_version: int, operation_key: str, body_hash: str, state: Dict[str, Any], events: List[Dict[str, Any]], response: Dict[str, Any]) -> Dict[str, Any]:
        replay = self._check_idempotency(operation_key, body_hash)
        if replay:
            return replay
        current = self.cases.get(case_id)
        if not current:
            raise WorkflowDomainError(404, "DD_CASE_NOT_FOUND", "The case was not found.")
        actual_version = int(current.get("workflowVersion") or 1)
        if actual_version != expected_version:
            raise WorkflowDomainError(
                409,
                "DD_WORKFLOW_VERSION_CONFLICT",
                "The workflow changed. Reload the current workflow and try again.",
                {"expectedWorkflowVersion": expected_version, "actualWorkflowVersion": actual_version},
            )
        self.cases[case_id] = copy.deepcopy(state)
        self.events.extend(copy.deepcopy(events))
        self.idempotency[operation_key] = {"bodyHash": body_hash, "response": copy.deepcopy(response)}
        return copy.deepcopy(response)


def _execute_read(query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    with get_driver().session(database=get_active_database()) as session:
        if hasattr(session, "execute_read"):
            records = session.execute_read(lambda tx: list(tx.run(query, params or {})))
        else:
            records = session.read_transaction(lambda tx: list(tx.run(query, params or {})))
    return [record.data() if hasattr(record, "data") else dict(record) for record in records]


class Neo4jWorkflowStore(WorkflowStore):
    def _deserialize_case(self, row: Dict[str, Any]) -> Dict[str, Any]:
        raw_projection = str(row.get("projectionJson") or "").strip()
        if raw_projection:
            state = json.loads(raw_projection)
            state["workflowVersion"] = int(row.get("workflowVersion") or state.get("workflowVersion") or 1)
            return state
        return initial_projection(row)

    def load_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        rows = _execute_read(
            """
            MATCH (c:DueDiligenceCase {caseId: $caseId})
            RETURN c.caseId AS caseId, c.subject AS subject,
                   c.subjectGeorgian AS subjectGeorgian,
                   c.subjectEnglish AS subjectEnglish,
                   c.subjectType AS subjectType, c.status AS status,
                   c.owner AS owner, toString(c.createdAt) AS createdAt,
                   toString(c.updatedAt) AS updatedAt,
                   c.ddWorkflowProjectionJson AS projectionJson,
                   coalesce(c.ddWorkflowVersion, 1) AS workflowVersion
            """,
            {"caseId": case_id},
        )
        return self._deserialize_case(rows[0]) if rows else None

    def list_cases(self) -> List[Dict[str, Any]]:
        rows = _execute_read(
            """
            MATCH (c:DueDiligenceCase)
            RETURN c.caseId AS caseId, c.subject AS subject,
                   c.subjectGeorgian AS subjectGeorgian,
                   c.subjectEnglish AS subjectEnglish,
                   c.subjectType AS subjectType, c.status AS status,
                   c.owner AS owner, toString(c.createdAt) AS createdAt,
                   toString(c.updatedAt) AS updatedAt,
                   c.ddWorkflowProjectionJson AS projectionJson,
                   coalesce(c.ddWorkflowVersion, 1) AS workflowVersion
            """
        )
        return [self._deserialize_case(row) for row in rows]

    def lookup_idempotency(self, operation_key: str) -> Optional[Dict[str, Any]]:
        rows = _execute_read(
            """
            MATCH (i:DDWorkflowIdempotency {operationKey: $operationKey})
            RETURN i.bodyHash AS bodyHash, i.responseJson AS responseJson
            """,
            {"operationKey": operation_key},
        )
        if not rows:
            return None
        return {"bodyHash": rows[0].get("bodyHash"), "response": json.loads(rows[0].get("responseJson") or "{}")}

    @staticmethod
    def _event_params(event: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "eventId": event["eventId"],
            "eventType": event["eventType"],
            "caseId": event["caseId"],
            "workflowVersion": int(event["workflowVersion"]),
            "actorId": event["actor"]["actor"]["actorId"],
            "actorMethod": event["actor"]["method"],
            "statementCode": event["actor"]["statementCode"],
            "purposeId": event.get("purposeId") or "",
            "createdAt": event["createdAt"],
            "payloadJson": _canonical_json(event.get("payload") or {}),
        }

    def _transaction_commit(
        self,
        *,
        case_id: str,
        expected_version: Optional[int],
        operation_key: str,
        body_hash: str,
        state: Dict[str, Any],
        events: List[Dict[str, Any]],
        response: Dict[str, Any],
        create: bool,
    ) -> Dict[str, Any]:
        claim_token = str(uuid4())

        def work(tx):
            idem = tx.run(
                """
                MERGE (i:DDWorkflowIdempotency {operationKey: $operationKey})
                ON CREATE SET i.claimToken = $claimToken, i.bodyHash = $bodyHash,
                              i.createdAt = datetime(), i.caseId = $caseId
                RETURN i.claimToken AS claimToken, i.bodyHash AS bodyHash,
                       i.responseJson AS responseJson
                """,
                {"operationKey": operation_key, "claimToken": claim_token, "bodyHash": body_hash, "caseId": case_id},
            ).single()
            if not idem:
                raise WorkflowDomainError(500, "DD_IDEMPOTENCY_STORE_FAILED", "The mutation could not be recorded.")
            if str(idem.get("claimToken") or "") != claim_token:
                if str(idem.get("bodyHash") or "") != body_hash:
                    raise WorkflowDomainError(409, "DD_IDEMPOTENCY_KEY_REUSED", "The idempotency key was already used with a different request.")
                stored = json.loads(idem.get("responseJson") or "{}")
                stored["idempotentReplay"] = True
                return stored

            if create:
                created = tx.run(
                    """
                    CREATE (c:DueDiligenceCase {caseId: $caseId})
                    SET c.subject = $subject, c.subjectGeorgian = $subjectGeorgian,
                        c.subjectEnglish = $subjectEnglish, c.subjectType = $subjectType,
                        c.status = 'Draft', c.owner = $owner,
                        c.createdAt = datetime($createdAt), c.updatedAt = datetime($updatedAt),
                        c.ddWorkflowVersion = $workflowVersion,
                        c.ddWorkflowSchemaVersion = $schemaVersion,
                        c.ddWorkflowProjectionJson = $projectionJson
                    RETURN c.caseId AS caseId
                    """,
                    {
                        "caseId": case_id,
                        "subject": state["intake"]["aliases"][0]["value"],
                        "subjectGeorgian": next((alias["value"] for alias in state["intake"]["aliases"] if alias["script"] == "Geor"), ""),
                        "subjectEnglish": next((alias["value"] for alias in state["intake"]["aliases"] if alias["script"] == "Latn"), ""),
                        "subjectType": state["intake"]["subjectCategory"],
                        "owner": str(((state["intake"].get("owner") or {}).get("displayName")) or ""),
                        "createdAt": state["createdAt"],
                        "updatedAt": state["updatedAt"],
                        "workflowVersion": state["workflowVersion"],
                        "schemaVersion": MUTATION_CONTRACT_VERSION,
                        "projectionJson": _canonical_json(state),
                    },
                ).single()
                if not created:
                    raise WorkflowDomainError(409, "DD_CASE_ALREADY_EXISTS", "The case already exists.")
            else:
                updated = tx.run(
                    """
                    MATCH (c:DueDiligenceCase {caseId: $caseId})
                    WHERE coalesce(c.ddWorkflowVersion, 1) = $expectedVersion
                    SET c.ddWorkflowVersion = $workflowVersion,
                        c.ddWorkflowSchemaVersion = $schemaVersion,
                        c.ddWorkflowProjectionJson = $projectionJson,
                        c.updatedAt = datetime($updatedAt)
                    RETURN c.caseId AS caseId
                    """,
                    {
                        "caseId": case_id,
                        "expectedVersion": expected_version,
                        "workflowVersion": state["workflowVersion"],
                        "schemaVersion": MUTATION_CONTRACT_VERSION,
                        "projectionJson": _canonical_json(state),
                        "updatedAt": state["updatedAt"],
                    },
                ).single()
                if not updated:
                    current = tx.run(
                        "MATCH (c:DueDiligenceCase {caseId: $caseId}) RETURN coalesce(c.ddWorkflowVersion, 1) AS version",
                        {"caseId": case_id},
                    ).single()
                    if not current:
                        raise WorkflowDomainError(404, "DD_CASE_NOT_FOUND", "The case was not found.")
                    raise WorkflowDomainError(
                        409,
                        "DD_WORKFLOW_VERSION_CONFLICT",
                        "The workflow changed. Reload the current workflow and try again.",
                        {"expectedWorkflowVersion": expected_version, "actualWorkflowVersion": int(current["version"])},
                    )
            for event in events:
                tx.run(
                    """
                    MATCH (c:DueDiligenceCase {caseId: $caseId})
                    CREATE (e:DDWorkflowEvent {eventId: $eventId, eventType: $eventType,
                      caseId: $caseId, workflowVersion: $workflowVersion,
                      actorId: $actorId, actorMethod: $actorMethod,
                      statementCode: $statementCode, purposeId: $purposeId,
                      createdAt: datetime($createdAt), payloadJson: $payloadJson})
                    MERGE (c)-[:HAS_DD_WORKFLOW_EVENT]->(e)
                    """,
                    self._event_params(event),
                ).consume()
            tx.run(
                """
                MATCH (i:DDWorkflowIdempotency {operationKey: $operationKey, claimToken: $claimToken})
                SET i.responseJson = $responseJson, i.completedAt = datetime(), i.status = 'complete'
                """,
                {"operationKey": operation_key, "claimToken": claim_token, "responseJson": _canonical_json(response)},
            ).consume()
            return response

        driver = get_driver()
        with driver.session(database=get_active_database()) as session:
            if hasattr(session, "execute_write"):
                return session.execute_write(work)
            return session.write_transaction(work)

    def create_case(self, *, operation_key: str, body_hash: str, state: Dict[str, Any], events: List[Dict[str, Any]], response: Dict[str, Any]) -> Dict[str, Any]:
        return self._transaction_commit(
            case_id=state["caseId"], expected_version=None, operation_key=operation_key,
            body_hash=body_hash, state=state, events=events, response=response, create=True,
        )

    def commit(self, *, case_id: str, expected_version: int, operation_key: str, body_hash: str, state: Dict[str, Any], events: List[Dict[str, Any]], response: Dict[str, Any]) -> Dict[str, Any]:
        return self._transaction_commit(
            case_id=case_id, expected_version=expected_version, operation_key=operation_key,
            body_hash=body_hash, state=state, events=events, response=response, create=False,
        )


class WorkflowService:
    def __init__(
        self,
        store: WorkflowStore,
        *,
        policy: Optional[WorkflowPolicy] = None,
        now: Optional[Callable[[], datetime]] = None,
        identifier_hasher: Optional[Callable[[str], str]] = None,
        request_hasher: Optional[Callable[[str, str], str]] = None,
        field_policy_checker: Optional[Callable[[str, List[str]], tuple[bool, List[str]]]] = None,
    ):
        self.store = store
        self.policy = policy or WorkflowPolicy.from_environment()
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.identifier_hasher = identifier_hasher or self._default_identifier_hash
        self.request_hasher = request_hasher or self._default_request_hash
        self.field_policy_checker = field_policy_checker or collection_fields_allowed

    @staticmethod
    def _default_identifier_hash(value: str) -> str:
        return keyed_hash(get_settings(), "dd-workflow-identifier", value)

    @staticmethod
    def _default_request_hash(value: str, purpose: str) -> str:
        return keyed_hash(get_settings(), purpose, value)

    def _idempotency(self, *, operation: str, path: str, key: str, payload: Dict[str, Any]) -> tuple[str, str]:
        clean_key = str(key or "").strip()
        if len(clean_key) < 12 or len(clean_key) > 200 or any(ord(char) < 33 for char in clean_key):
            raise WorkflowDomainError(422, "DD_IDEMPOTENCY_KEY_INVALID", "A valid Idempotency-Key is required.")
        operation_key = self.request_hasher(f"{operation}:{path}:{clean_key}", "dd-workflow-idempotency-key")
        canonical_payload = _canonical_json(payload)
        body_hash = self.request_hasher(f"{operation}:{path}:{canonical_payload}", "dd-workflow-idempotency-body")
        return operation_key, body_hash

    def _replay(self, operation_key: str, body_hash: str) -> Optional[Dict[str, Any]]:
        existing = self.store.lookup_idempotency(operation_key)
        if not existing:
            return None
        if str(existing.get("bodyHash") or "") != body_hash:
            raise WorkflowDomainError(409, "DD_IDEMPOTENCY_KEY_REUSED", "The idempotency key was already used with a different request.")
        response = copy.deepcopy(existing.get("response") or {})
        response["idempotentReplay"] = True
        return response

    def _load(self, case_id: str) -> Dict[str, Any]:
        state = self.store.load_case(case_id)
        if not state:
            raise WorkflowDomainError(404, "DD_CASE_NOT_FOUND", "The case was not found.")
        return state

    def _assert_workflow_version(self, state: Dict[str, Any], expected: int, purpose_id: str) -> None:
        actual = int(state.get("workflowVersion") or 1)
        if actual == expected:
            return
        blockers = compute_blockers(state, self.policy)
        raise WorkflowDomainError(
            409,
            "DD_WORKFLOW_VERSION_CONFLICT",
            "The workflow changed. Reload the current workflow and try again.",
            {
                "workflowContractVersion": WORKFLOW_CONTRACT_VERSION,
                "expectedWorkflowVersion": expected,
                "actualWorkflowVersion": actual,
                "blockers": blockers,
                "allowedTransitions": allowed_transitions(state, blockers),
                "_access": _access(purpose_id),
            },
        )

    def _prepare_intake(self, intake_model: IntakeInput, actor: Dict[str, Any], *, purpose_id: str) -> Dict[str, Any]:
        intake = json.loads(_canonical_json(intake_model.model_dump(by_alias=True)))
        proposed_purpose = str(intake["processingPurposeId"])
        if proposed_purpose != purpose_id:
            raise WorkflowDomainError(
                403,
                "DD_PURPOSE_MISMATCH",
                "The proposed processing purpose does not match the authorized request purpose.",
            )
        retention_status = self.policy.retention_classes.get(str(intake["retentionClass"]))
        if retention_status not in {"active", "provisional"}:
            raise WorkflowDomainError(
                422,
                "DD_RETENTION_POLICY_NOT_AVAILABLE",
                "The retention policy is unavailable or disabled.",
                {"retentionClass": str(intake["retentionClass"]), "policyStatus": retention_status or "unknown"},
            )
        field_names: List[str] = []
        prepared_identifiers: List[Dict[str, Any]] = []
        for identifier in intake["identifiers"]:
            identifier_type = str(identifier["type"]).strip()
            if any(marker in identifier_type.casefold() for marker in PERSON_IDENTIFIER_MARKERS):
                raise WorkflowDomainError(422, "DD_IDENTIFIER_TYPE_PROHIBITED", "The identifier type is prohibited for this workflow.")
            if identifier_type not in self.policy.allowed_identifier_types:
                raise WorkflowDomainError(422, "DD_IDENTIFIER_TYPE_NOT_ALLOWED", "The identifier type is not allowed by the active workflow policy.")
            field_names.append(f"dd.identifier.{identifier_type}")
            raw_value = str(identifier["value"])
            match_material = _canonical_json(
                {
                    "type": identifier_type,
                    "issuer": str(identifier["issuer"]).casefold(),
                    "country": str(identifier.get("country") or "").upper(),
                    "value": unicodedata.normalize("NFKC", raw_value).strip().casefold(),
                }
            )
            prepared_identifiers.append(
                {
                    "type": identifier_type,
                    "valueHash": self.identifier_hasher(match_material),
                    "displayValue": _masked_identifier(raw_value),
                    "issuer": identifier["issuer"],
                    "country": identifier.get("country"),
                    "classification": "restricted_identifier",
                }
            )
        if field_names:
            allowed, denied = self.field_policy_checker(purpose_id, sorted(set(field_names)))
            if not allowed:
                raise WorkflowDomainError(
                    403,
                    "DD_IDENTIFIER_FIELD_POLICY_DENIED",
                    "One or more identifier fields are not approved for this purpose.",
                    {"deniedFields": sorted(set(denied))},
                )
        intake["identifiers"] = prepared_identifiers
        timestamp = _now_iso(self.now())
        conflict = intake["conflictDeclaration"]
        conflict.pop("attestation", None)
        if conflict["status"] == "unknown":
            conflict.update({"attestedBy": None, "attestedAt": None})
        else:
            conflict.update(
                {
                    "attestedBy": _actor_attestation(actor, "case_prepared", timestamp),
                    "attestedAt": timestamp,
                }
            )
        return intake

    @staticmethod
    def _identifier_display(identifier: Dict[str, Any]) -> Dict[str, Any]:
        display = str(identifier.get("displayValue") or "Restricted")
        return {
            "type": str(identifier.get("type") or "identifier"),
            "value": None,
            "displayValue": display,
            "masked": True,
            "omitted": False,
            "issuer": identifier.get("issuer"),
            "country": identifier.get("country"),
        }

    def _public_intake(self, state: Dict[str, Any]) -> Dict[str, Any]:
        intake = copy.deepcopy(state.get("intake") or {})
        intake["identifiers"] = [self._identifier_display(item) for item in intake.get("identifiers") or []]
        return intake

    def _candidate_actions(self, case_id: str, candidate: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidate_case_id = str(candidate["caseId"])
        actions = [
            {
                "actionCode": "open_existing",
                "messageKey": "dd.action.open_existing",
                "params": {"caseId": candidate_case_id},
                "stage": "identity",
                "method": "GET",
                "route": f"/due-diligence/cases/{candidate_case_id}",
                "blocking": False,
                "requiresCsrf": False,
                "requiresIdempotency": False,
            }
        ]
        if candidate.get("state") == "pending":
            actions.extend(
                {
                    "actionCode": code,
                    "messageKey": f"dd.action.{code}",
                    "params": {"candidateCaseId": candidate_case_id},
                    "stage": "identity",
                    "method": "POST",
                    "route": f"/due-diligence/cases/{case_id}/duplicate-candidates/{candidate_case_id}/decisions",
                    "blocking": False,
                    "requiresCsrf": True,
                    "requiresIdempotency": True,
                }
                for code in ("continue_new", "link_existing", "dismiss_duplicate")
            )
        return actions

    def public_candidates(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidates = []
        for stored in state.get("duplicateCandidates") or []:
            candidate = copy.deepcopy(stored)
            candidate["actions"] = self._candidate_actions(state["caseId"], candidate)
            candidates.append(candidate)
        return candidates

    @staticmethod
    def _sla(intake: Dict[str, Any], now: datetime) -> Dict[str, Any]:
        raw_deadline = intake.get("deadline")
        if not raw_deadline:
            return {"deadline": None, "state": "none", "remainingHours": None}
        deadline = datetime.fromisoformat(str(raw_deadline).replace("Z", "+00:00"))
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        hours = (deadline.astimezone(timezone.utc) - now.astimezone(timezone.utc)).total_seconds() / 3600
        state = "overdue" if hours < 0 else "due_soon" if hours <= 72 else "on_track"
        return {"deadline": deadline.isoformat(), "state": state, "remainingHours": round(hours, 2)}

    def workflow_response(self, state: Dict[str, Any], purpose_id: Optional[str]) -> Dict[str, Any]:
        blockers = compute_blockers(state, self.policy)
        pending = len([candidate for candidate in state.get("duplicateCandidates") or [] if candidate.get("state") == "pending"])
        total = len(state.get("duplicateCandidates") or [])
        return {
            "contractVersion": WORKFLOW_CONTRACT_VERSION,
            "caseId": state["caseId"],
            "workflowVersion": int(state["workflowVersion"]),
            "stage": state["stage"],
            "lifecycleStatus": state["lifecycleStatus"],
            "migrationNeedsReview": bool(state.get("migrationNeedsReview")),
            "completion": _completion_list(state),
            "blockers": blockers,
            "allowedTransitions": allowed_transitions(state, blockers),
            "waivers": copy.deepcopy(state.get("waivers") or []),
            "coverage": {
                "overall": None,
                "connectors": {"complete": 0, "partial": 0, "zeroResults": 0, "unavailable": 0, "permissionRequired": 0, "error": 0},
                "identity": {
                    "state": "not_applicable" if total == 0 else "incomplete" if pending else "complete",
                    "resolved": total - pending,
                    "total": total,
                },
                "findings": {"state": "unknown", "resolved": 0, "total": 0},
                "contradictionsOpen": 0,
            },
            "_access": _access(purpose_id),
        }

    def case_record(self, state: Dict[str, Any]) -> Dict[str, Any]:
        blockers = compute_blockers(state, self.policy)
        transitions = allowed_transitions(state, blockers)
        next_action = None
        if transitions:
            next_action = {
                "actionCode": "review_transition",
                "messageKey": "dd.action.review_transition",
                "params": {"transitionCode": transitions[0]["transitionCode"]},
                "stage": state["stage"],
                "method": "GET",
                "route": f"/due-diligence/cases/{state['caseId']}/workflow",
                "blocking": bool(blockers),
                "requiresCsrf": False,
                "requiresIdempotency": False,
            }
        return {
            "caseId": state["caseId"],
            "workflowVersion": int(state["workflowVersion"]),
            "stage": state["stage"],
            "lifecycleStatus": state["lifecycleStatus"],
            "migrationNeedsReview": bool(state.get("migrationNeedsReview")),
            "archivedFromStage": state.get("archivedFromStage"),
            "intake": self._public_intake(state),
            "duplicateCandidates": self.public_candidates(state),
            "nextAction": next_action,
            "sla": self._sla(state.get("intake") or {}, self.now()),
            "blockerSummary": {
                "total": len(blockers),
                "blocking": len([item for item in blockers if item["blocking"]]),
                "nonWaivable": len([item for item in blockers if item["waiverPolicy"] == "forbidden"]),
            },
        }

    def case_detail_response(self, state: Dict[str, Any], purpose_id: Optional[str]) -> Dict[str, Any]:
        masked = [f"case.intake.identifiers[{index}].value" for index, _ in enumerate((state.get("intake") or {}).get("identifiers") or [])]
        return {
            "contractVersion": WORKFLOW_CONTRACT_VERSION,
            "caseId": state["caseId"],
            "case": self.case_record(state),
            "_access": _access(purpose_id, masked=masked),
        }

    def _event(self, state: Dict[str, Any], event_type: str, actor: Dict[str, Any], purpose_id: str, statement_code: str, payload: Dict[str, Any], timestamp: str) -> Dict[str, Any]:
        return {
            "eventId": str(uuid4()),
            "eventType": event_type,
            "caseId": state["caseId"],
            "workflowVersion": int(state["workflowVersion"]),
            "actor": _actor_attestation(actor, statement_code, timestamp),
            "purposeId": purpose_id,
            "createdAt": timestamp,
            "payload": payload,
        }

    def _mutation_response(self, state: Dict[str, Any], purpose_id: str, *, event_name: str, event: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "contractVersion": WORKFLOW_CONTRACT_VERSION,
            "mutationContractVersion": MUTATION_CONTRACT_VERSION,
            "caseId": state["caseId"],
            "workflowVersion": int(state["workflowVersion"]),
            "idempotentReplay": False,
            "case": self.case_record(state),
            "workflow": self.workflow_response(state, purpose_id),
            event_name: copy.deepcopy(event),
            "_access": _access(purpose_id),
        }

    def create_case(self, payload: CreateCaseRequest, *, idempotency_key: str, actor: Dict[str, Any], purpose_id: str, path: str) -> Dict[str, Any]:
        payload_dict = payload.model_dump(by_alias=True)
        operation_key, body_hash = self._idempotency(operation="create_case", path=path, key=idempotency_key, payload=payload_dict)
        replay = self._replay(operation_key, body_hash)
        if replay:
            return replay
        timestamp = _now_iso(self.now())
        intake = self._prepare_intake(payload.intake, actor, purpose_id=purpose_id)
        state = {
            "caseId": str(uuid4()),
            "workflowVersion": 1,
            "stage": "intake",
            "lifecycleStatus": "active",
            "migrationNeedsReview": False,
            "archivedFromStage": None,
            "intake": intake,
            "duplicateCandidates": [],
            "completion": {stage: {"stage": stage, "state": "incomplete" if stage == "intake" else "unknown", "completedAt": None, "actorAttestation": None} for stage in STAGES},
            "waivers": [],
            "createdAt": timestamp,
            "updatedAt": timestamp,
            "legacyUnknownFields": [],
        }
        event = self._event(state, "case_created", actor, purpose_id, "case_prepared", {"subjectCategory": intake["subjectCategory"]}, timestamp)
        response = self._mutation_response(state, purpose_id, event_name="caseCreatedEvent", event=event)
        return self.store.create_case(operation_key=operation_key, body_hash=body_hash, state=state, events=[event], response=response)

    def replace_intake(self, case_id: str, payload: IntakeReplaceRequest, *, idempotency_key: str, actor: Dict[str, Any], purpose_id: str, principal_purpose_scopes: Iterable[str], path: str) -> Dict[str, Any]:
        payload_dict = payload.model_dump(by_alias=True)
        operation_key, body_hash = self._idempotency(operation="replace_intake", path=path, key=idempotency_key, payload=payload_dict)
        replay = self._replay(operation_key, body_hash)
        if replay:
            return replay
        current = self._load(case_id)
        self._assert_workflow_version(current, payload.expected_workflow_version, purpose_id)
        current_purpose = str((current.get("intake") or {}).get("processingPurposeId") or "")
        proposed_purpose = payload.intake.processing_purpose_id
        scopes = set(principal_purpose_scopes)
        if "*" not in scopes and proposed_purpose not in scopes:
            raise WorkflowDomainError(403, "DD_PURPOSE_FORBIDDEN", "The proposed processing purpose is not authorized.")
        if current_purpose not in {"", "legacy-unknown", proposed_purpose}:
            if "*" not in scopes and current_purpose not in scopes:
                raise WorkflowDomainError(403, "DD_PURPOSE_FORBIDDEN", "The current processing purpose is not authorized.")
            raise WorkflowDomainError(409, "DD_PURPOSE_CHANGE_NOT_SUPPORTED", "Changing an established processing purpose requires a separate reviewed reclassification workflow.")
        new_state = copy.deepcopy(current)
        new_state["intake"] = self._prepare_intake(payload.intake, actor, purpose_id=purpose_id)
        new_state["migrationNeedsReview"] = False
        new_state["legacyUnknownFields"] = []
        changed = _projection_digest(new_state) != _projection_digest(current)
        new_state["workflowVersion"] = int(current["workflowVersion"]) + (1 if changed else 0)
        timestamp = _now_iso(self.now())
        new_state["updatedAt"] = timestamp
        event = self._event(new_state, "intake_replaced" if changed else "intake_replacement_noop", actor, purpose_id, "case_prepared", {"changed": changed}, timestamp)
        response = self._mutation_response(new_state, purpose_id, event_name="intakeEvent", event=event)
        return self.store.commit(case_id=case_id, expected_version=payload.expected_workflow_version, operation_key=operation_key, body_hash=body_hash, state=new_state, events=[event], response=response)

    @staticmethod
    def _identifier_keys(state: Dict[str, Any]) -> set[tuple[str, str, str, str]]:
        return {
            (
                str(identifier.get("type") or ""),
                str(identifier.get("issuer") or "").casefold(),
                str(identifier.get("country") or "").upper(),
                str(identifier.get("valueHash") or ""),
            )
            for identifier in (state.get("intake") or {}).get("identifiers") or []
            if identifier.get("valueHash")
        }

    @staticmethod
    def _alias_keys(state: Dict[str, Any]) -> set[str]:
        return {
            _normalized_name(alias.get("value") or "")
            for alias in (state.get("intake") or {}).get("aliases") or []
            if _normalized_name(alias.get("value") or "")
        }

    def _detect_candidates(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        identifiers = self._identifier_keys(state)
        aliases = self._alias_keys(state)
        previous = {candidate["caseId"]: candidate for candidate in state.get("duplicateCandidates") or []}
        detected: List[Dict[str, Any]] = []
        for other in self.store.candidate_cases(state["caseId"]):
            shared_identifiers = identifiers.intersection(self._identifier_keys(other))
            shared_aliases = aliases.intersection(self._alias_keys(other))
            if not shared_identifiers and not shared_aliases:
                continue
            reasons: List[Dict[str, str]] = []
            confidence: Optional[float] = None
            if shared_identifiers:
                reasons.append(
                    {
                        "code": "EXACT_ISSUER_SCOPED_IDENTIFIER",
                        "field": "identifiers",
                        "summary": "An issuer-scoped non-personal identifier hash matches.",
                    }
                )
                confidence = 0.98
            if shared_aliases:
                reasons.append(
                    {
                        "code": "NORMALIZED_ALIAS_MATCH",
                        "field": "aliases",
                        "summary": "A normalized display alias matches; this never confirms identity by itself.",
                    }
                )
                confidence = 0.99 if shared_identifiers else 0.65
            prior = previous.get(other["caseId"]) or {}
            display_alias = str((((other.get("intake") or {}).get("aliases") or [{}])[0]).get("value") or "")
            candidate = {
                "caseId": other["caseId"],
                "subjectDisplay": _masked_name(display_alias),
                "subjectMasked": True,
                "confidence": confidence,
                "reasons": reasons,
                "conflicts": [],
                "state": prior.get("state") or "pending",
                "analystDecision": copy.deepcopy(prior.get("analystDecision")),
                "actions": [],
            }
            detected.append(candidate)
        detected.sort(key=lambda candidate: (-float(candidate["confidence"] or 0), candidate["caseId"]))
        return detected

    def scan_duplicates(self, case_id: str, payload: DuplicateScanRequest, *, idempotency_key: str, actor: Dict[str, Any], purpose_id: str, path: str) -> Dict[str, Any]:
        payload_dict = payload.model_dump(by_alias=True)
        operation_key, body_hash = self._idempotency(operation="scan_duplicates", path=path, key=idempotency_key, payload=payload_dict)
        replay = self._replay(operation_key, body_hash)
        if replay:
            return replay
        current = self._load(case_id)
        self._assert_workflow_version(current, payload.expected_workflow_version, purpose_id)
        detected = self._detect_candidates(current)
        new_state = copy.deepcopy(current)
        new_state["duplicateCandidates"] = detected
        changed = _projection_digest(new_state) != _projection_digest(current)
        new_state["workflowVersion"] = int(current["workflowVersion"]) + (1 if changed else 0)
        timestamp = _now_iso(self.now())
        new_state["updatedAt"] = timestamp
        scan_event = self._event(
            new_state,
            "duplicate_scan_completed",
            actor,
            purpose_id,
            "identity_reviewed",
            {"candidateCount": len(detected), "changed": changed, "leadOnly": True},
            timestamp,
        )
        scan_event.update({"scanId": scan_event["eventId"], "scannedAt": timestamp, "candidateCount": len(detected), "changed": changed, "leadOnly": True})
        response = self._mutation_response(new_state, purpose_id, event_name="scanEvent", event=scan_event)
        response["duplicateCandidates"] = self.public_candidates(new_state)
        return self.store.commit(case_id=case_id, expected_version=payload.expected_workflow_version, operation_key=operation_key, body_hash=body_hash, state=new_state, events=[scan_event], response=response)

    def decide_duplicate(self, case_id: str, candidate_case_id: str, payload: DuplicateDecisionRequest, *, idempotency_key: str, actor: Dict[str, Any], purpose_id: str, candidate_authorized: bool, path: str) -> Dict[str, Any]:
        payload_dict = payload.model_dump(by_alias=True)
        operation_key, body_hash = self._idempotency(operation="decide_duplicate", path=path, key=idempotency_key, payload=payload_dict)
        replay = self._replay(operation_key, body_hash)
        if replay:
            return replay
        current = self._load(case_id)
        self._assert_workflow_version(current, payload.expected_workflow_version, purpose_id)
        candidate_index = next((index for index, candidate in enumerate(current.get("duplicateCandidates") or []) if candidate.get("caseId") == candidate_case_id), None)
        if candidate_index is None or (payload.decision == "link_existing" and not candidate_authorized):
            raise WorkflowDomainError(404, "DD_DUPLICATE_CANDIDATE_NOT_FOUND", "The duplicate candidate is unavailable.")
        new_state = copy.deepcopy(current)
        timestamp = _now_iso(self.now())
        state_by_decision = {"continue_new": "continued_new", "link_existing": "linked_existing", "dismiss_duplicate": "dismissed"}
        candidate = new_state["duplicateCandidates"][candidate_index]
        candidate["state"] = state_by_decision[payload.decision]
        candidate["analystDecision"] = {
            "decision": payload.decision,
            "actor": _actor_attestation(actor, "identity_reviewed", timestamp),
            "decidedAt": timestamp,
        }
        new_state["workflowVersion"] = int(current["workflowVersion"]) + 1
        new_state["updatedAt"] = timestamp
        decision_event = self._event(
            new_state,
            "duplicate_candidate_decided",
            actor,
            purpose_id,
            "identity_reviewed",
            {"candidateCaseId": candidate_case_id, "decision": payload.decision, "rationale": payload.rationale, "mergePerformed": False},
            timestamp,
        )
        decision_event.update({"decisionId": decision_event["eventId"], "candidateCaseId": candidate_case_id, "decision": payload.decision, "rationale": payload.rationale, "mergePerformed": False})
        response = self._mutation_response(new_state, purpose_id, event_name="decisionEvent", event=decision_event)
        response["duplicateCandidates"] = self.public_candidates(new_state)
        return self.store.commit(case_id=case_id, expected_version=payload.expected_workflow_version, operation_key=operation_key, body_hash=body_hash, state=new_state, events=[decision_event], response=response)

    def transition(self, case_id: str, payload: TransitionRequest, *, idempotency_key: str, actor: Dict[str, Any], purpose_id: str, path: str) -> Dict[str, Any]:
        payload_dict = payload.model_dump(by_alias=True)
        operation_key, body_hash = self._idempotency(operation="transition", path=path, key=idempotency_key, payload=payload_dict)
        replay = self._replay(operation_key, body_hash)
        if replay:
            return replay
        current = self._load(case_id)
        self._assert_workflow_version(current, payload.expected_workflow_version, purpose_id)
        blockers = compute_blockers(current, self.policy)
        offers = allowed_transitions(current, blockers)
        provided_codes = {waiver.blocker_code for waiver in payload.waivers}
        blocker_by_code = {blocker["code"]: blocker for blocker in blockers}
        forbidden = [code for code in provided_codes if blocker_by_code.get(code, {}).get("waiverPolicy") == "forbidden"]
        exact_offer = next(
            (
                offer
                for offer in offers
                if offer["transitionCode"] == payload.transition_code and offer["toStage"] == payload.to_stage
            ),
            None,
        )
        error_details = {
            "workflowContractVersion": WORKFLOW_CONTRACT_VERSION,
            "expectedWorkflowVersion": payload.expected_workflow_version,
            "actualWorkflowVersion": int(current["workflowVersion"]),
            "blockers": blockers,
            "allowedTransitions": offers,
        }
        if forbidden:
            raise WorkflowDomainError(409, "DD_BLOCKER_NON_WAIVABLE", "A non-waivable blocker cannot be waived.", {**error_details, "blockerCodes": sorted(forbidden)})
        if not exact_offer:
            raise WorkflowDomainError(409, "DD_TRANSITION_OUT_OF_ORDER", "The requested transition is not currently offered.", error_details)
        required_codes = set(exact_offer["requiredWaiverCodes"])
        extra = provided_codes - required_codes
        if extra:
            raise WorkflowDomainError(409, "DD_WAIVER_NOT_REQUIRED", "A waiver was supplied for a blocker that is not required by this transition.", {**error_details, "blockerCodes": sorted(extra)})
        missing = required_codes - provided_codes
        if missing:
            raise WorkflowDomainError(409, "DD_TRANSITION_BLOCKED", "All required waivers must be supplied atomically.", {**error_details, "missingWaiverCodes": sorted(missing)})
        if payload.attestations.prepared_by is None:
            raise WorkflowDomainError(422, "DD_ATTESTATION_REQUIRED", "The preparedBy attestation is required.")
        if "reviewedBy" in exact_offer["requiredAttestations"] and payload.attestations.reviewed_by is None:
            raise WorkflowDomainError(422, "DD_ATTESTATION_REQUIRED", "The reviewedBy attestation is required.")
        now_dt = self.now().astimezone(timezone.utc)
        timestamp = _now_iso(now_dt)
        for waiver in payload.waivers:
            if waiver.expires_at:
                expires = waiver.expires_at
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if expires.astimezone(timezone.utc) <= now_dt:
                    raise WorkflowDomainError(422, "DD_WAIVER_EXPIRY_INVALID", "A waiver cannot be expired when it is created.")
        new_state = copy.deepcopy(current)
        waiver_events: List[Dict[str, Any]] = []
        for waiver in payload.waivers:
            waiver_id = str(uuid4())
            canonical = {
                "waiverId": waiver_id,
                "blockerCode": waiver.blocker_code,
                "reason": waiver.reason,
                "actor": _actor_attestation(actor, "blocker_waived", timestamp),
                "createdAt": timestamp,
                "expiresAt": waiver.expires_at.isoformat() if waiver.expires_at else None,
                "active": True,
            }
            new_state.setdefault("waivers", []).append(canonical)
            event = self._event(
                new_state,
                "blocker_waived",
                actor,
                purpose_id,
                "blocker_waived",
                {"waiverId": waiver_id, "blockerCode": waiver.blocker_code, "reason": waiver.reason, "expiresAt": canonical["expiresAt"]},
                timestamp,
            )
            event["waiver"] = canonical
            waiver_events.append(event)
        statement_code = "case_reviewed" if payload.attestations.reviewed_by else "case_prepared"
        new_state.setdefault("completion", {})[current["stage"]] = {
            "stage": current["stage"],
            "state": "complete",
            "completedAt": timestamp,
            "actorAttestation": _actor_attestation(actor, statement_code, timestamp),
        }
        new_state["stage"] = payload.to_stage
        new_state.setdefault("completion", {})[payload.to_stage] = {
            "stage": payload.to_stage,
            "state": "incomplete",
            "completedAt": None,
            "actorAttestation": None,
        }
        if payload.to_stage == "monitoring":
            new_state["lifecycleStatus"] = "monitoring"
        elif payload.to_stage == "closed":
            new_state["lifecycleStatus"] = "closed"
        else:
            new_state["lifecycleStatus"] = "active"
        new_state["workflowVersion"] = int(current["workflowVersion"]) + 1
        new_state["updatedAt"] = timestamp
        transition_event = self._event(
            new_state,
            "workflow_transitioned",
            actor,
            purpose_id,
            statement_code,
            {
                "transitionCode": payload.transition_code,
                "fromStage": current["stage"],
                "toStage": payload.to_stage,
                "waiverIds": [event["waiver"]["waiverId"] for event in waiver_events],
            },
            timestamp,
        )
        transition_event.update(
            {
                "transitionId": transition_event["eventId"],
                "transitionCode": payload.transition_code,
                "fromStage": current["stage"],
                "toStage": payload.to_stage,
                "waivers": [event["waiver"] for event in waiver_events],
            }
        )
        response = self._mutation_response(new_state, purpose_id, event_name="transitionEvent", event=transition_event)
        return self.store.commit(
            case_id=case_id,
            expected_version=payload.expected_workflow_version,
            operation_key=operation_key,
            body_hash=body_hash,
            state=new_state,
            events=[*waiver_events, transition_event],
            response=response,
        )

    def list_case_response(self, *, purpose_id: str, limit: int, cursor: Optional[str] = None, stage: Optional[str] = None) -> Dict[str, Any]:
        states = [state for state in self.store.list_cases() if not stage or state.get("stage") == stage]
        states.sort(key=lambda state: (str(state.get("updatedAt") or ""), state["caseId"]), reverse=True)
        if cursor:
            cursor_index = next((index for index, state in enumerate(states) if state["caseId"] == cursor), None)
            states = states[cursor_index + 1 :] if cursor_index is not None else []
        selected = states[:limit]
        items = []
        for state in selected:
            intake = state.get("intake") or {}
            aliases = intake.get("aliases") or []
            display_name = str((aliases[0] if aliases else {}).get("value") or "Restricted subject")
            record = self.case_record(state)
            items.append(
                {
                    "caseId": state["caseId"],
                    "workflowVersion": int(state["workflowVersion"]),
                    "stage": state["stage"],
                    "lifecycleStatus": state["lifecycleStatus"],
                    "subject": {"displayName": display_name, "masked": False, "omitted": False, "category": intake.get("subjectCategory") or "other"},
                    "owner": copy.deepcopy(intake.get("owner")),
                    "lastActivityAt": state.get("updatedAt") or state.get("createdAt") or _now_iso(self.now()),
                    "nextAction": record["nextAction"],
                    "sla": record["sla"],
                    "blockerSummary": record["blockerSummary"],
                }
            )
        has_more = len(states) > limit
        return {
            "contractVersion": WORKFLOW_CONTRACT_VERSION,
            "items": items,
            "page": {"nextCursor": items[-1]["caseId"] if has_more and items else None, "hasMore": has_more, "limit": limit},
            "_access": _access(purpose_id),
        }

    def queue_response(self, *, purpose_id: str, limit: int, cursor: Optional[str] = None, stage: Optional[str] = None) -> Dict[str, Any]:
        states = [
            state
            for state in self.store.list_cases()
            if (not stage or state.get("stage") == stage)
            and state.get("lifecycleStatus") not in {"closed", "archived"}
        ]

        def queue_sort_key(state: Dict[str, Any]) -> tuple[Any, ...]:
            record = self.case_record(state)
            last_activity = state.get("updatedAt") or state.get("createdAt") or ""
            return (
                STAGES.index(str(state.get("stage") or "intake")),
                0 if record["sla"]["state"] == "overdue" else 1,
                -int(record["blockerSummary"]["blocking"]),
                str(last_activity),
                state["caseId"],
            )

        states.sort(key=queue_sort_key)
        if cursor:
            cursor_index = next((index for index, state in enumerate(states) if state["caseId"] == cursor), None)
            states = states[cursor_index + 1 :] if cursor_index is not None else []
        selected = states[:limit]
        queue_items = []
        for state in selected:
            intake = state.get("intake") or {}
            aliases = intake.get("aliases") or []
            display_name = str((aliases[0] if aliases else {}).get("value") or "Restricted subject")
            record = self.case_record(state)
            queue_items.append(
                {
                    "caseId": state["caseId"],
                    "stage": state["stage"],
                    "lifecycleStatus": state["lifecycleStatus"],
                    "subject": {
                        "displayName": display_name,
                        "masked": False,
                        "omitted": False,
                        "category": intake.get("subjectCategory") or "other",
                    },
                    "owner": copy.deepcopy(intake.get("owner")),
                    "sla": record["sla"],
                    "blockingCount": record["blockerSummary"]["blocking"],
                    "unresolvedCandidateCount": len(
                        [candidate for candidate in state.get("duplicateCandidates") or [] if candidate.get("state") == "pending"]
                    ),
                    "openFindingCount": 0,
                    "lastActivityAt": state.get("updatedAt") or state.get("createdAt") or _now_iso(self.now()),
                    "nextAction": record["nextAction"],
                }
            )
        has_more = len(states) > limit
        return {
            "contractVersion": WORKFLOW_CONTRACT_VERSION,
            "items": queue_items,
            "page": {"nextCursor": queue_items[-1]["caseId"] if has_more and queue_items else None, "hasMore": has_more, "limit": limit},
            "_access": _access(purpose_id),
        }


router = APIRouter()


def _response_headers(*, replay: Optional[bool] = None) -> Dict[str, str]:
    headers = {
        "Cache-Control": "no-store",
        "X-FS-DD-Contract-Version": WORKFLOW_CONTRACT_VERSION,
    }
    if replay is not None:
        headers["Idempotent-Replay"] = "true" if replay else "false"
    return headers


def _json_response(content: Dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=content,
        headers=_response_headers(replay=content.get("idempotentReplay") if "idempotentReplay" in content else None),
    )


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or uuid4())


def _error(request: Request, error: WorkflowDomainError) -> JSONResponse:
    details = {"workflowContractVersion": WORKFLOW_CONTRACT_VERSION, **error.details}
    response = error_response(
        error.status_code,
        error.code,
        error.message,
        request_id=_request_id(request),
        retryable=error.code == "DD_WORKFLOW_VERSION_CONFLICT",
        details=details,
        headers=_response_headers(),
    )
    return response


def _disabled(request: Request) -> JSONResponse:
    return _error(
        request,
        WorkflowDomainError(404, "DD_WORKFLOW_V2_DISABLED", "The v2 due-diligence workflow is not enabled."),
    )


def _be2_unavailable(request: Request, capability: str) -> JSONResponse:
    return _error(
        request,
        WorkflowDomainError(
            501,
            "DD_BE2_READ_NOT_AVAILABLE",
            "This read model is not available in the BE1 runtime.",
            {"capability": capability, "contractStatus": "draft-be2+"},
        ),
    )


def _parse_payload(request: Request, model: type[StrictModel], raw: Dict[str, Any]) -> StrictModel | JSONResponse:
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        safe_errors = [
            {"location": [str(part) for part in item.get("loc") or ()], "type": str(item.get("type") or "value_error")}
            for item in exc.errors()
        ]
        return _error(
            request,
            WorkflowDomainError(422, "DD_REQUEST_VALIDATION_FAILED", "The request does not match the BE1 mutation contract.", {"errors": safe_errors}),
        )


def _context(request: Request, *, case_id: Optional[str] = None, mutation: bool = False) -> Dict[str, Any]:
    principal = getattr(request.state, "principal", None) or {}
    principal_id = str(principal.get("principalId") or "").strip()
    roles = set(principal.get("roles") or [])
    if not principal_id:
        raise WorkflowDomainError(401, "AUTH_SESSION_INVALID", "Authentication is required.")
    if not roles.intersection({"admin", "compliance", "investigator"}):
        raise WorkflowDomainError(403, "ROLE_FORBIDDEN", "You do not have permission to access this workflow.")
    case_scopes = set(principal.get("caseScopes") or [])
    if case_id and not roles.intersection({"admin", "compliance"}) and "*" not in case_scopes and case_id not in case_scopes:
        raise WorkflowDomainError(404, "DD_CASE_NOT_FOUND", "The case was not found.")
    purpose_id = str(getattr(request.state, "purpose_id", "") or request.headers.get("X-FS-Purpose-Id") or "").strip()
    if not purpose_id:
        raise WorkflowDomainError(403, "PURPOSE_REQUIRED", "An approved processing purpose is required.")
    purpose_scopes = set(principal.get("purposeScopes") or [])
    if "*" not in purpose_scopes and purpose_id not in purpose_scopes:
        raise WorkflowDomainError(403, "PURPOSE_FORBIDDEN", "This processing purpose is not authorized.")
    provider = str(principal.get("provider") or "").casefold()
    if mutation:
        if provider == "password":
            method = "local_file_session"
        elif provider in {"google", "entra", "oidc"} or principal.get("issuer"):
            method = "oidc_session"
        else:
            raise WorkflowDomainError(403, "DD_ATTESTATION_METHOD_UNAVAILABLE", "A local-file or OIDC session is required for an attested mutation.")
    else:
        method = "oidc_session" if provider != "password" else "local_file_session"
    return {
        "principal": principal,
        "purposeId": purpose_id,
        "purposeScopes": purpose_scopes,
        "caseScopes": case_scopes,
        "roles": roles,
        "actor": {
            "actorId": principal_id,
            "displayName": principal.get("displayName"),
            "method": method,
        },
    }


def _service() -> WorkflowService:
    return WorkflowService(Neo4jWorkflowStore())


def _handle(request: Request, callback: Callable[[], Dict[str, Any]], *, status_code: int = 200) -> JSONResponse:
    try:
        return _json_response(callback(), status_code=status_code)
    except WorkflowDomainError as exc:
        return _error(request, exc)


def list_cases_v2_for_legacy_route(request: Request, *, limit: int = 50) -> JSONResponse:
    if not workflow_v2_enabled():
        raise RuntimeError("list_cases_v2_for_legacy_route called while feature flag is off")
    return _handle(
        request,
        lambda: _service().list_case_response(
            purpose_id=_context(request)["purposeId"], limit=limit
        ),
    )


def get_case_v2_for_legacy_route(request: Request, case_id: str) -> JSONResponse:
    if not workflow_v2_enabled():
        raise RuntimeError("get_case_v2_for_legacy_route called while feature flag is off")

    def callback() -> Dict[str, Any]:
        context = _context(request, case_id=case_id)
        return _service().case_detail_response(_service()._load(case_id), context["purposeId"])

    return _handle(request, callback)


def legacy_mutation_disabled_response(request: Request, replacement_action: str) -> Optional[JSONResponse]:
    if not workflow_v2_enabled():
        return None
    return _error(
        request,
        WorkflowDomainError(
            409,
            "DD_LEGACY_MUTATION_DISABLED",
            "This legacy mutation is disabled while the v2 workflow is active.",
            {"replacementAction": replacement_action},
        ),
    )


@router.get("/workflow/schema")
def get_workflow_schema_v2(request: Request):
    if not workflow_v2_enabled():
        return _disabled(request)

    def callback() -> Dict[str, Any]:
        _context(request)
        path = Path(__file__).resolve().parents[3] / "contracts" / "dd-workflow" / "v2" / "be0.4" / "fixtures" / "workflow-schema.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        policy = WorkflowPolicy.from_environment()
        data["retentionClasses"] = [
            {
                "id": policy_id,
                "status": status,
                "labelKey": f"dd.policy.retention.{policy_id}.label",
                "descriptionKey": f"dd.policy.retention.{policy_id}.description",
                "action": None,
            }
            for policy_id, status in sorted(policy.retention_classes.items())
        ]
        data["_access"] = _access(_context(request)["purposeId"])
        return data

    return _handle(request, callback)


@router.get("/cases/queue")
def get_queue_v2(
    request: Request,
    cursor: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    stage: Optional[str] = Query(default=None),
):
    if not workflow_v2_enabled():
        return _disabled(request)
    return _handle(
        request,
        lambda: _service().queue_response(
            purpose_id=_context(request)["purposeId"], limit=limit, cursor=cursor, stage=stage
        ),
    )


@router.post("/cases/v2")
def create_case_v2(
    request: Request,
    raw_payload: Dict[str, Any],
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    if not workflow_v2_enabled():
        return _disabled(request)
    payload = _parse_payload(request, CreateCaseRequest, raw_payload)
    if isinstance(payload, JSONResponse):
        return payload

    def callback() -> Dict[str, Any]:
        context = _context(request, mutation=True)
        return _service().create_case(
            payload,
            idempotency_key=idempotency_key or "",
            actor=context["actor"],
            purpose_id=context["purposeId"],
            path=str(request.url.path),
        )

    return _handle(request, callback, status_code=201)


@router.get("/cases/{case_id}/workflow")
def get_case_workflow_v2(request: Request, case_id: str):
    if not workflow_v2_enabled():
        return _disabled(request)

    def callback() -> Dict[str, Any]:
        context = _context(request, case_id=case_id)
        service = _service()
        return service.workflow_response(service._load(case_id), context["purposeId"])

    return _handle(request, callback)


@router.put("/cases/{case_id}/intake")
def replace_case_intake_v2(
    request: Request,
    case_id: str,
    raw_payload: Dict[str, Any],
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    if not workflow_v2_enabled():
        return _disabled(request)
    payload = _parse_payload(request, IntakeReplaceRequest, raw_payload)
    if isinstance(payload, JSONResponse):
        return payload

    def callback() -> Dict[str, Any]:
        context = _context(request, case_id=case_id, mutation=True)
        return _service().replace_intake(
            case_id,
            payload,
            idempotency_key=idempotency_key or "",
            actor=context["actor"],
            purpose_id=context["purposeId"],
            principal_purpose_scopes=context["purposeScopes"],
            path=str(request.url.path),
        )

    return _handle(request, callback)


@router.post("/cases/{case_id}/duplicate-candidates/scan")
def scan_case_duplicates_v2(
    request: Request,
    case_id: str,
    raw_payload: Dict[str, Any],
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    if not workflow_v2_enabled():
        return _disabled(request)
    payload = _parse_payload(request, DuplicateScanRequest, raw_payload)
    if isinstance(payload, JSONResponse):
        return payload

    def callback() -> Dict[str, Any]:
        context = _context(request, case_id=case_id, mutation=True)
        return _service().scan_duplicates(
            case_id,
            payload,
            idempotency_key=idempotency_key or "",
            actor=context["actor"],
            purpose_id=context["purposeId"],
            path=str(request.url.path),
        )

    return _handle(request, callback)


@router.post("/cases/{case_id}/duplicate-candidates/{candidate_case_id}/decisions")
def decide_case_duplicate_v2(
    request: Request,
    case_id: str,
    candidate_case_id: str,
    raw_payload: Dict[str, Any],
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    if not workflow_v2_enabled():
        return _disabled(request)
    payload = _parse_payload(request, DuplicateDecisionRequest, raw_payload)
    if isinstance(payload, JSONResponse):
        return payload

    def callback() -> Dict[str, Any]:
        context = _context(request, case_id=case_id, mutation=True)
        candidate_authorized = bool(
            context["roles"].intersection({"admin", "compliance"})
            or "*" in context["caseScopes"]
            or candidate_case_id in context["caseScopes"]
        )
        return _service().decide_duplicate(
            case_id,
            candidate_case_id,
            payload,
            idempotency_key=idempotency_key or "",
            actor=context["actor"],
            purpose_id=context["purposeId"],
            candidate_authorized=candidate_authorized,
            path=str(request.url.path),
        )

    return _handle(request, callback)


@router.post("/cases/{case_id}/transitions")
def transition_case_v2(
    request: Request,
    case_id: str,
    raw_payload: Dict[str, Any],
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    if not workflow_v2_enabled():
        return _disabled(request)
    payload = _parse_payload(request, TransitionRequest, raw_payload)
    if isinstance(payload, JSONResponse):
        return payload

    def callback() -> Dict[str, Any]:
        context = _context(request, case_id=case_id, mutation=True)
        return _service().transition(
            case_id,
            payload,
            idempotency_key=idempotency_key or "",
            actor=context["actor"],
            purpose_id=context["purposeId"],
            path=str(request.url.path),
        )

    return _handle(request, callback)


@router.get("/cases/{case_id}/connectors")
@router.get("/cases/{case_id}/connectors/{connector_id}")
@router.get("/cases/{case_id}/connector-runs")
@router.get("/cases/{case_id}/connector-runs/{connector_run_id}")
def be2_connector_reads_not_available(request: Request, case_id: str, connector_id: Optional[str] = None, connector_run_id: Optional[str] = None):
    if not workflow_v2_enabled():
        return _disabled(request)
    try:
        _context(request, case_id=case_id)
    except WorkflowDomainError as exc:
        return _error(request, exc)
    return _be2_unavailable(request, "connectors")


@router.get("/cases/{case_id}/assessment")
def be3_assessment_read_not_available(request: Request, case_id: str):
    if not workflow_v2_enabled():
        return _disabled(request)
    try:
        _context(request, case_id=case_id)
    except WorkflowDomainError as exc:
        return _error(request, exc)
    return _be2_unavailable(request, "assessment")


@router.get("/cases/{case_id}/reports")
@router.get("/cases/{case_id}/reports/{snapshot_id}")
def be4_report_reads_not_available(request: Request, case_id: str, snapshot_id: Optional[str] = None):
    if not workflow_v2_enabled():
        return _disabled(request)
    try:
        _context(request, case_id=case_id)
    except WorkflowDomainError as exc:
        return _error(request, exc)
    return _be2_unavailable(request, "report_snapshots")
