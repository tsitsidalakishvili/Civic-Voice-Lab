from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from .core.errors import CONTRACT_VERSION, error_response
from .db import get_active_database, get_driver


router = APIRouter()


def _read(query: str, params: dict | None = None) -> list[dict]:
    with get_driver().session(database=get_active_database()) as session:
        return [record.data() for record in session.run(query, params or {})]


def _write(query: str, params: dict | None = None) -> list[dict]:
    with get_driver().session(database=get_active_database()) as session:
        if hasattr(session, "execute_write"):
            return session.execute_write(
                lambda tx: [record.data() for record in tx.run(query, params or {})]
            )
        return session.write_transaction(
            lambda tx: [record.data() for record in tx.run(query, params or {})]
        )


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or uuid4())


def _reviewer(request: Request) -> str:
    principal = getattr(request.state, "principal", None) or {}
    return str(principal.get("principalId") or "local-development")


TARGET_QUERIES = {
    "case": "MATCH (caseNode:DueDiligenceCase {caseId: $caseId}) WHERE $targetId = $caseId RETURN caseNode.caseId AS id",
    "resolution": "MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_RESOLUTION_REVIEW]->(target:EntityResolutionReview {candidateId: $targetId}) RETURN target.candidateId AS id",
    "finding": "MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_FINDING]->(target:InvestigationFinding {findingId: $targetId}) RETURN target.findingId AS id",
    "statement": "MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_STATEMENT]->(target:InvestigationStatement {statementId: $targetId}) RETURN target.statementId AS id",
    "publication": "MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_PUBLICATION]->(target:InvestigationPublication {publicationId: $targetId}) RETURN target.publicationId AS id",
}


def _target_exists(case_id: str, target_type: str, target_id: str) -> bool:
    query = TARGET_QUERIES.get(target_type)
    return bool(query and _read(query, {"caseId": case_id, "targetId": target_id}))


class CasePurposeCreate(BaseModel):
    purpose_id: str = Field(alias="purposeId", min_length=2, max_length=100)
    legal_basis: str = Field(alias="legalBasis", min_length=2, max_length=300)
    retention_category: str = Field(alias="retentionCategory", min_length=2, max_length=100)
    due_at: str | None = Field(default=None, alias="dueAt")


@router.post("/cases/{case_id}/governance/purpose")
def configure_case_purpose(request: Request, case_id: str, payload: CasePurposeCreate):
    rows = _write(
        """
        MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
        MATCH (purpose:ProcessingPurpose {purposeId: $purposeId, status: 'active'})
        WITH caseNode, purpose ORDER BY purpose.version DESC LIMIT 1
        CREATE (event:InvestigationPurposeEvent {
          eventId: randomUUID(), caseId: $caseId, purposeId: $purposeId,
          purposeVersion: purpose.version, legalBasis: $legalBasis,
          retentionCategory: $retentionCategory,
          dueAt: CASE WHEN $dueAt IS NULL THEN null ELSE datetime($dueAt) END,
          actorId: $actorId, createdAt: datetime()
        })
        MERGE (caseNode)-[:HAS_PURPOSE_EVENT]->(event)
        SET caseNode.purposeId = $purposeId,
            caseNode.purposeVersion = purpose.version,
            caseNode.legalBasis = $legalBasis,
            caseNode.retentionCategory = $retentionCategory,
            caseNode.purposeDueAt = CASE WHEN $dueAt IS NULL THEN null ELSE datetime($dueAt) END,
            caseNode.governanceUpdatedAt = datetime()
        RETURN event.eventId AS eventId, purpose.version AS purposeVersion
        """,
        {
            "caseId": case_id,
            "purposeId": payload.purpose_id,
            "legalBasis": payload.legal_basis,
            "retentionCategory": payload.retention_category,
            "dueAt": payload.due_at,
            "actorId": _reviewer(request),
        },
    )
    if not rows:
        return error_response(409, "PURPOSE_NOT_ACTIVE", "The case and an active processing purpose are required.", request_id=_request_id(request))
    return {"contractVersion": CONTRACT_VERSION, "caseId": case_id, "purposeId": payload.purpose_id, **rows[0]}


class ReviewCreate(BaseModel):
    target_type: Literal["case", "resolution", "finding", "statement", "publication"] = Field(alias="targetType")
    target_id: str = Field(alias="targetId", min_length=1)
    decision: Literal[
        "accepted", "rejected", "deferred", "verified", "false-positive",
        "needs-research", "legal-approved", "editorial-approved",
    ]
    rationale: str = Field(min_length=3, max_length=5000)
    evidence_ids: list[str] = Field(default_factory=list, alias="evidenceIds")


def append_review_event(
    case_id: str,
    *,
    target_type: str,
    target_id: str,
    decision: str,
    rationale: str,
    reviewer_id: str,
    evidence_ids: list[str] | None = None,
    metadata: dict | None = None,
) -> str:
    review_event_id = str(uuid4())
    _write(
        """
        MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
        CREATE (event:InvestigationReviewEvent {
          reviewEventId: $reviewEventId, caseId: $caseId,
          targetType: $targetType, targetId: $targetId,
          decision: $decision, rationale: $rationale,
          evidenceIds: $evidenceIds, reviewerId: $reviewerId,
          metadataJson: $metadataJson, createdAt: datetime()
        })
        MERGE (caseNode)-[:HAS_INVESTIGATION_REVIEW_EVENT]->(event)
        """,
        {
            "caseId": case_id,
            "reviewEventId": review_event_id,
            "targetType": target_type,
            "targetId": target_id,
            "decision": decision,
            "rationale": rationale,
            "evidenceIds": sorted(set(evidence_ids or [])),
            "reviewerId": reviewer_id,
            "metadataJson": json.dumps(metadata or {}, separators=(",", ":")),
        },
    )
    return review_event_id


@router.post("/cases/{case_id}/reviews", status_code=201)
def create_review(request: Request, case_id: str, payload: ReviewCreate):
    if not _target_exists(case_id, payload.target_type, payload.target_id):
        return error_response(404, "REVIEW_TARGET_NOT_FOUND", "The review target is not attached to this case.", request_id=_request_id(request))
    review_id = append_review_event(
        case_id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        decision=payload.decision,
        rationale=payload.rationale,
        reviewer_id=_reviewer(request),
        evidence_ids=payload.evidence_ids,
    )
    return {"contractVersion": CONTRACT_VERSION, "reviewEventId": review_id, "caseId": case_id, **payload.model_dump(by_alias=True), "createdAt": datetime.now(timezone.utc).isoformat()}


@router.get("/cases/{case_id}/reviews")
def list_reviews(case_id: str):
    rows = _read(
        """
        MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_REVIEW_EVENT]->(event:InvestigationReviewEvent)
        RETURN event.reviewEventId AS reviewEventId, event.targetType AS targetType,
               event.targetId AS targetId, event.decision AS decision,
               event.rationale AS rationale, coalesce(event.evidenceIds, []) AS evidenceIds,
               event.reviewerId AS reviewerId, event.metadataJson AS metadataJson,
               toString(event.createdAt) AS createdAt
        ORDER BY event.createdAt DESC
        """,
        {"caseId": case_id},
    )
    for row in rows:
        try:
            row["metadata"] = json.loads(row.pop("metadataJson") or "{}")
        except ValueError:
            row["metadata"] = {}
    return {"contractVersion": CONTRACT_VERSION, "caseId": case_id, "reviews": rows}


class DisputeCreate(BaseModel):
    target_type: Literal["resolution", "finding", "statement"] = Field(alias="targetType")
    target_id: str = Field(alias="targetId", min_length=1)
    claim: str = Field(min_length=3, max_length=5000)
    requested_action: Literal["correct", "remove", "annotate", "re-review"] = Field(alias="requestedAction")
    evidence_ids: list[str] = Field(default_factory=list, alias="evidenceIds")


@router.post("/cases/{case_id}/disputes", status_code=201)
def create_dispute(request: Request, case_id: str, payload: DisputeCreate):
    if not _target_exists(case_id, payload.target_type, payload.target_id):
        return error_response(404, "DISPUTE_TARGET_NOT_FOUND", "The disputed record is not attached to this case.", request_id=_request_id(request))
    dispute_id = str(uuid4())
    _write(
        """
        MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
        CREATE (dispute:InvestigationDispute {
          disputeId: $disputeId, caseId: $caseId, targetType: $targetType,
          targetId: $targetId, claim: $claim, requestedAction: $requestedAction,
          evidenceIds: $evidenceIds, status: 'open', openedBy: $actorId,
          createdAt: datetime(), updatedAt: datetime()
        })
        CREATE (event:InvestigationDisputeEvent {
          eventId: randomUUID(), disputeId: $disputeId, action: 'opened',
          actorId: $actorId, rationale: $claim, createdAt: datetime()
        })
        MERGE (caseNode)-[:HAS_INVESTIGATION_DISPUTE]->(dispute)
        MERGE (dispute)-[:HAS_DISPUTE_EVENT]->(event)
        """,
        {"caseId": case_id, "disputeId": dispute_id, "targetType": payload.target_type, "targetId": payload.target_id, "claim": payload.claim, "requestedAction": payload.requested_action, "evidenceIds": sorted(set(payload.evidence_ids)), "actorId": _reviewer(request)},
    )
    return {"contractVersion": CONTRACT_VERSION, "disputeId": dispute_id, "caseId": case_id, "status": "open", **payload.model_dump(by_alias=True)}


class CorrectionCreate(BaseModel):
    dispute_id: str | None = Field(default=None, alias="disputeId")
    target_type: Literal["finding", "statement", "resolution"] = Field(alias="targetType")
    target_id: str = Field(alias="targetId", min_length=1)
    action: Literal["annotate", "supersede", "tombstone"]
    corrected_fields: dict = Field(default_factory=dict, alias="correctedFields")
    rationale: str = Field(min_length=3, max_length=5000)
    evidence_ids: list[str] = Field(default_factory=list, alias="evidenceIds")


@router.post("/cases/{case_id}/corrections", status_code=201)
def create_correction(request: Request, case_id: str, payload: CorrectionCreate):
    if not _target_exists(case_id, payload.target_type, payload.target_id):
        return error_response(404, "CORRECTION_TARGET_NOT_FOUND", "The correction target is not attached to this case.", request_id=_request_id(request))
    correction_id = str(uuid4())
    rows = _write(
        """
        MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
        OPTIONAL MATCH (caseNode)-[:HAS_INVESTIGATION_DISPUTE]->(dispute:InvestigationDispute {disputeId: $disputeId})
        CREATE (correction:InvestigationCorrection {
          correctionId: $correctionId, caseId: $caseId, disputeId: $disputeId,
          targetType: $targetType, targetId: $targetId, action: $action,
          correctedFieldsJson: $correctedFieldsJson, rationale: $rationale,
          evidenceIds: $evidenceIds, actorId: $actorId, createdAt: datetime()
        })
        MERGE (caseNode)-[:HAS_INVESTIGATION_CORRECTION]->(correction)
        FOREACH (_ IN CASE WHEN dispute IS NULL THEN [] ELSE [1] END |
          SET dispute.status = 'resolved', dispute.resolvedBy = $actorId,
              dispute.resolvedAt = datetime(), dispute.updatedAt = datetime()
          CREATE (event:InvestigationDisputeEvent {
            eventId: randomUUID(), disputeId: $disputeId, action: 'resolved',
            actorId: $actorId, correctionId: $correctionId,
            rationale: $rationale, createdAt: datetime()
          })
          MERGE (dispute)-[:HAS_DISPUTE_EVENT]->(event)
        )
        RETURN correction.correctionId AS correctionId
        """,
        {"caseId": case_id, "correctionId": correction_id, "disputeId": payload.dispute_id, "targetType": payload.target_type, "targetId": payload.target_id, "action": payload.action, "correctedFieldsJson": json.dumps(payload.corrected_fields, ensure_ascii=False), "rationale": payload.rationale, "evidenceIds": sorted(set(payload.evidence_ids)), "actorId": _reviewer(request)},
    )
    if payload.action == "tombstone" and payload.target_type == "statement":
        _write(
            """
            MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_STATEMENT]->(statement:InvestigationStatement {statementId: $targetId})
            SET statement.tombstonedAt = datetime(), statement.tombstoneCorrectionId = $correctionId
            """,
            {"caseId": case_id, "targetId": payload.target_id, "correctionId": correction_id},
        )
    return {"contractVersion": CONTRACT_VERSION, "correctionId": correction_id, "caseId": case_id, "status": "recorded", **payload.model_dump(by_alias=True)}


class AppealCreate(BaseModel):
    dispute_id: str = Field(alias="disputeId", min_length=1)
    grounds: str = Field(min_length=3, max_length=5000)
    requested_outcome: str = Field(alias="requestedOutcome", min_length=2, max_length=500)


@router.post("/cases/{case_id}/appeals", status_code=201)
def create_appeal(request: Request, case_id: str, payload: AppealCreate):
    appeal_id = str(uuid4())
    rows = _write(
        """
        MATCH (caseNode:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_DISPUTE]->(dispute:InvestigationDispute {disputeId: $disputeId})
        CREATE (appeal:InvestigationAppeal {
          appealId: $appealId, caseId: $caseId, disputeId: $disputeId,
          grounds: $grounds, requestedOutcome: $requestedOutcome,
          status: 'open', openedBy: $actorId, createdAt: datetime()
        })
        CREATE (event:InvestigationAppealEvent {
          eventId: randomUUID(), appealId: $appealId, action: 'opened',
          actorId: $actorId, rationale: $grounds, createdAt: datetime()
        })
        MERGE (caseNode)-[:HAS_INVESTIGATION_APPEAL]->(appeal)
        MERGE (appeal)-[:HAS_APPEAL_EVENT]->(event)
        RETURN appeal.appealId AS appealId
        """,
        {"caseId": case_id, "disputeId": payload.dispute_id, "appealId": appeal_id, "grounds": payload.grounds, "requestedOutcome": payload.requested_outcome, "actorId": _reviewer(request)},
    )
    if not rows:
        return error_response(404, "DISPUTE_NOT_FOUND", "The dispute is not attached to this case.", request_id=_request_id(request))
    return {"contractVersion": CONTRACT_VERSION, "appealId": appeal_id, "caseId": case_id, "status": "open", **payload.model_dump(by_alias=True)}


def publication_governance_blockers(case_id: str) -> list[dict]:
    rows = _read(
        """
        MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
        OPTIONAL MATCH (caseNode)-[:HAS_INVESTIGATION_DISPUTE]->(dispute:InvestigationDispute {status: 'open'})
        WITH caseNode, count(DISTINCT dispute) AS openDisputes
        OPTIONAL MATCH (caseNode)-[:HAS_INVESTIGATION_APPEAL]->(appeal:InvestigationAppeal {status: 'open'})
        WITH caseNode, openDisputes, count(DISTINCT appeal) AS openAppeals
        OPTIONAL MATCH (caseNode)-[:HAS_INVESTIGATION_REVIEW_EVENT]->(review:InvestigationReviewEvent {targetType: 'case', targetId: $caseId})
        RETURN caseNode.purposeId AS purposeId, openDisputes, openAppeals,
               collect(DISTINCT review.decision) AS decisions
        """,
        {"caseId": case_id},
    )
    if not rows:
        return [{"code": "CASE_NOT_FOUND", "message": "The case does not exist."}]
    row = rows[0]
    blockers: list[dict] = []
    if not row.get("purposeId"):
        blockers.append({"code": "CASE_PURPOSE_REQUIRED", "message": "Record an active processing purpose before publication."})
    if int(row.get("openDisputes") or 0):
        blockers.append({"code": "OPEN_DISPUTES", "message": "Resolve or explicitly deny all open disputes before publication.", "count": int(row["openDisputes"])})
    if int(row.get("openAppeals") or 0):
        blockers.append({"code": "OPEN_APPEALS", "message": "Resolve all open appeals before publication.", "count": int(row["openAppeals"])})
    decisions = set(row.get("decisions") or [])
    if "legal-approved" not in decisions:
        blockers.append({"code": "LEGAL_APPROVAL_REQUIRED", "message": "A recorded legal release approval is required."})
    if "editorial-approved" not in decisions:
        blockers.append({"code": "EDITORIAL_APPROVAL_REQUIRED", "message": "A recorded editorial release approval is required."})
    return blockers


@router.get("/cases/{case_id}/governance")
def get_case_governance(case_id: str):
    rows = _read(
        """
        MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
        OPTIONAL MATCH (caseNode)-[:HAS_INVESTIGATION_DISPUTE]->(dispute:InvestigationDispute)
        WITH caseNode, collect(dispute{.disputeId, .targetType, .targetId, .claim, .requestedAction, .status, .evidenceIds, createdAt: toString(dispute.createdAt), updatedAt: toString(dispute.updatedAt)}) AS disputes
        OPTIONAL MATCH (caseNode)-[:HAS_INVESTIGATION_CORRECTION]->(correction:InvestigationCorrection)
        WITH caseNode, disputes, collect(correction{.correctionId, .disputeId, .targetType, .targetId, .action, .rationale, .evidenceIds, createdAt: toString(correction.createdAt)}) AS corrections
        OPTIONAL MATCH (caseNode)-[:HAS_INVESTIGATION_APPEAL]->(appeal:InvestigationAppeal)
        RETURN caseNode{.caseId, .purposeId, .purposeVersion, .legalBasis, .retentionCategory, purposeDueAt: toString(caseNode.purposeDueAt)} AS casePurpose,
               disputes, corrections,
               collect(appeal{.appealId, .disputeId, .grounds, .requestedOutcome, .status, createdAt: toString(appeal.createdAt)}) AS appeals
        """,
        {"caseId": case_id},
    )
    if not rows:
        return error_response(404, "CASE_NOT_FOUND", "The case could not be found.")
    row = rows[0]
    return {"contractVersion": CONTRACT_VERSION, "caseId": case_id, "casePurpose": row["casePurpose"], "disputes": [item for item in row["disputes"] if item.get("disputeId")], "corrections": [item for item in row["corrections"] if item.get("correctionId")], "appeals": [item for item in row["appeals"] if item.get("appealId")], "publicationBlockers": publication_governance_blockers(case_id)}
