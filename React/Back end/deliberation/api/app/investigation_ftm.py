import hashlib
import json
import re
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .db import get_active_database, get_driver
from .investigation_reuse import (
    ftm_schema_metadata,
    infer_ftm_property_type,
    name_blocking_keys,
    normalize_investigation_name,
    normalize_match_value,
    official_ftm_model,
    official_logic_v2,
    toolkit_capabilities,
)
from .investigation_governance import append_review_event, publication_governance_blockers
from .core.errors import error_response


router = APIRouter()


VERIFICATION_STATUSES = {
    "source-stated",
    "candidate-match",
    "analyst-added",
    "verified",
    "unverified",
    "rejected",
}
ASSERTION_KINDS = {"sourced", "inferred", "hypothesis", "analyst"}
RESOLUTION_DECISIONS = {"accepted", "rejected", "deferred"}
FINDING_STATUSES = {"open", "accepted", "rejected", "needs-research"}


class EntityResolutionReviewRequest(BaseModel):
    left_entity_id: str = Field(min_length=1, alias="leftEntityId")
    right_entity_id: str = Field(min_length=1, alias="rightEntityId")
    decision: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    reviewed_by: Optional[str] = Field(default="", alias="reviewedBy")


class InvestigationPathQueryRequest(BaseModel):
    start_entity_id: Optional[str] = Field(default=None, alias="startEntityId")
    target_entity_id: Optional[str] = Field(default=None, alias="targetEntityId")
    max_depth: int = Field(default=4, alias="maxDepth", ge=1, le=6)
    limit: int = Field(default=25, ge=1, le=100)
    include_candidate_matches: bool = Field(default=False, alias="includeCandidateMatches")


class InvestigationFindingCreate(BaseModel):
    title: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    finding_type: str = Field(default="Investigative finding", alias="findingType")
    status: str = "open"
    priority: int = Field(default=2, ge=1, le=3)
    confidence: float = Field(default=0.7, ge=0, le=1)
    supporting_statement_ids: List[str] = Field(default_factory=list, alias="supportingStatementIds")
    contradicting_statement_ids: List[str] = Field(default_factory=list, alias="contradictingStatementIds")
    path_run_ids: List[str] = Field(default_factory=list, alias="pathRunIds")
    evidence_ids: List[str] = Field(default_factory=list, alias="evidenceIds")
    node_ids: List[str] = Field(default_factory=list, alias="nodeIds")
    relationship_ids: List[str] = Field(default_factory=list, alias="relationshipIds")
    analyst_rationale: str = Field(default="", alias="analystRationale")
    recommended_next_steps: List[str] = Field(default_factory=list, alias="recommendedNextSteps")
    created_by: Optional[str] = Field(default="", alias="createdBy")


class InvestigationFindingUpdate(BaseModel):
    title: Optional[str] = None
    claim: Optional[str] = None
    finding_type: Optional[str] = Field(default=None, alias="findingType")
    status: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=1, le=3)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    supporting_statement_ids: Optional[List[str]] = Field(default=None, alias="supportingStatementIds")
    contradicting_statement_ids: Optional[List[str]] = Field(default=None, alias="contradictingStatementIds")
    path_run_ids: Optional[List[str]] = Field(default=None, alias="pathRunIds")
    evidence_ids: Optional[List[str]] = Field(default=None, alias="evidenceIds")
    node_ids: Optional[List[str]] = Field(default=None, alias="nodeIds")
    relationship_ids: Optional[List[str]] = Field(default=None, alias="relationshipIds")
    analyst_rationale: Optional[str] = Field(default=None, alias="analystRationale")
    recommended_next_steps: Optional[List[str]] = Field(default=None, alias="recommendedNextSteps")
    reviewed_by: Optional[str] = Field(default=None, alias="reviewedBy")


class InvestigationPublicationCreate(BaseModel):
    title: Optional[str] = ""
    executive_summary: Optional[str] = Field(default="", alias="executiveSummary")
    prepared_by: Optional[str] = Field(default="", alias="preparedBy")


@router.get("/toolkit/capabilities")
def get_investigation_toolkit_capabilities():
    """Report which maintained OpenSanctions components power this runtime."""
    return toolkit_capabilities()


def _execute_read(session, query: str, params: Optional[dict] = None):
    if hasattr(session, "execute_read"):
        return session.execute_read(lambda tx: list(tx.run(query, params or {})))
    return session.read_transaction(lambda tx: list(tx.run(query, params or {})))


def _execute_write(session, query: str, params: Optional[dict] = None):
    def _run(tx):
        return list(tx.run(query, params or {}))

    if hasattr(session, "execute_write"):
        return session.execute_write(_run)
    return session.write_transaction(_run)


def _db_session(driver):
    return driver.session(database=get_active_database())


def _stable_id(prefix: str, *parts: object) -> str:
    material = "|".join(str(part or "").strip().casefold() for part in parts)
    return f"{prefix}-{hashlib.sha256(material.encode('utf-8')).hexdigest()[:24]}"


def _normalize_name(value: object) -> str:
    return normalize_investigation_name(value)


def _ordered_unique(values: List[object]) -> List[str]:
    output: List[str] = []
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in output:
            output.append(clean)
    return output


def _relationship_schema(label: object) -> str:
    value = str(label or "").casefold()
    if value.startswith("family:"):
        return "Family"
    if "ownership" in value or "business interest" in value:
        return "Ownership"
    if "position" in value or "director" in value or "officer" in value:
        return "Directorship"
    if "contract" in value:
        return "ContractAward"
    if "payment" in value or "transaction" in value:
        return "Payment"
    if "article" in value or "document" in value:
        return "Documentation"
    if "address" in value or "located at" in value:
        return "AddressLink"
    if "screening" in value or "same" in value or "identity" in value:
        return "IdentityHypothesis"
    return "Associate"


def _property_descriptor(key: str) -> Tuple[str, str]:
    mapping = {
        "name": ("Thing:name", "name"),
        "aliases": ("Thing:alias", "name"),
        "birthYear": ("Person:birthDate", "date"),
        "address": ("Thing:address", "address"),
        "acquiredAt": ("Asset:acquiredAt", "date"),
        "entityRole": ("Thing:role", "string"),
        "sourceExternalId": ("Thing:sourceId", "identifier"),
        "jurisdiction": ("LegalEntity:jurisdiction", "country"),
        "identifiers": ("Thing:idNumber", "identifier"),
    }
    return mapping.get(key, (f"Thing:{key}", "string"))


def _statement_row(
    *,
    case_id: str,
    subject_id: str,
    canonical_subject_id: str,
    schema: str,
    predicate: str,
    value: str = "",
    value_type: str = "string",
    object_entity_id: str = "",
    relationship_id: str = "",
    assertion_kind: str = "sourced",
    verification_status: str = "source-stated",
    confidence: float = 1.0,
    source_id: str = "",
    evidence_id: str = "",
    source_locator: str = "",
    source_excerpt: str = "",
    published_at: str = "",
    original_value: str = "",
    extraction_method: str = "projection",
) -> Dict[str, object]:
    statement_id = _stable_id(
        "statement",
        case_id,
        subject_id,
        predicate,
        object_entity_id or value,
        source_id,
        evidence_id,
    )
    return {
        "statementId": statement_id,
        "caseId": case_id,
        "subjectId": subject_id,
        "canonicalSubjectId": canonical_subject_id or subject_id,
        "schema": schema,
        "predicate": predicate,
        "value": value,
        "valueType": value_type,
        "objectEntityId": object_entity_id,
        "relationshipId": relationship_id,
        "assertionKind": assertion_kind,
        "verificationStatus": verification_status,
        "confidence": max(0.0, min(float(confidence), 1.0)),
        "sourceId": source_id,
        "evidenceId": evidence_id,
        "sourceLocator": source_locator,
        "sourceExcerpt": source_excerpt,
        "sourceRecordKey": evidence_id,
        "publishedAt": published_at,
        "originalValue": original_value or value,
        "extractionMethod": extraction_method,
        "supersedesStatementIds": [],
        "contradictsStatementIds": [],
    }


def _projection_rows(bundle: Dict[str, object]) -> Tuple[List[Dict[str, object]], List[Dict[str, str]]]:
    case_id = str(bundle.get("caseId") or "")
    entities = bundle.get("entities") or []
    relationships = bundle.get("relationships") or []
    evidence = bundle.get("evidence") or []
    evidence_by_id = {str(row.get("evidenceId")): row for row in evidence}
    evidence_by_entity: Dict[str, Set[str]] = defaultdict(set)
    names: Dict[Tuple[str, str], Dict[str, str]] = {}

    for relationship in relationships:
        for evidence_id in relationship.get("evidenceIds") or []:
            evidence_by_entity[str(relationship.get("fromEntityId"))].add(str(evidence_id))
            evidence_by_entity[str(relationship.get("toEntityId"))].add(str(evidence_id))

    statements: Dict[str, Dict[str, object]] = {}
    for entity in entities:
        entity_id = str(entity.get("entityId") or "")
        if not entity_id:
            continue
        evidence_ids = sorted(
            set(evidence_by_entity.get(entity_id) or [])
            | {str(value) for value in entity.get("evidenceIds") or [] if value}
        )
        if not evidence_ids and entity.get("sourceId"):
            evidence_ids = [""]
        display_names = _ordered_unique(
            [entity.get("name")] + list(entity.get("aliases") or [])
        )
        for display_index, display_name in enumerate(display_names):
            if str(entity.get("entityType") or "") == "Social profile":
                alias_type = "social-display"
            elif display_index == 0:
                alias_type = "official-name"
            else:
                alias_type = "source-alias"
            for normalized in name_blocking_keys(display_name):
                names[(entity_id, normalized)] = {
                    "entityId": entity_id,
                    "normalizedName": normalized,
                    "displayName": display_name,
                    "aliasType": alias_type,
                    "platform": str(entity.get("platform") or ""),
                    "sourceIds": _ordered_unique([entity.get("sourceId")]),
                    "evidenceIds": evidence_ids,
                    "assertionKind": "sourced",
                    "verificationStatus": "source-stated",
                }
        property_values: List[Tuple[str, object, str, str]] = []
        for key, value in [("name", entity.get("name"))] + [
            ("aliases", value) for value in entity.get("aliases") or []
        ]:
            predicate, value_type = _property_descriptor(key)
            property_values.append((key, value, predicate, value_type))
        for key in ["birthYear", "address", "acquiredAt", "entityRole", "sourceExternalId", "jurisdiction", "identifiers"]:
            value = entity.get(key)
            predicate, value_type = _property_descriptor(key)
            if isinstance(value, list):
                property_values.extend((key, item, predicate, value_type) for item in value)
            elif value not in (None, ""):
                property_values.append((key, value, predicate, value_type))

        ftm_schema = str(entity.get("ftmSchema") or entity.get("entityType") or "Thing")
        ftm_properties = entity.get("ftmProperties")
        if not isinstance(ftm_properties, dict):
            try:
                ftm_properties = json.loads(str(entity.get("ftmPropertiesJson") or "{}"))
            except (TypeError, ValueError):
                ftm_properties = {}
        schema_meta = ftm_schema_metadata(ftm_schema) or {}
        property_types = schema_meta.get("propertyTypes") or {}
        for prop_name, values in ftm_properties.items():
            prop_values = values if isinstance(values, list) else [values]
            value_type = str(property_types.get(prop_name) or infer_ftm_property_type(str(prop_name)))
            predicate = f"{ftm_schema}:{prop_name}"
            for value in prop_values:
                property_values.append((str(prop_name), value, predicate, value_type))

        for key, raw_value, predicate, value_type in property_values:
            if raw_value in (None, ""):
                continue
            for evidence_id in evidence_ids:
                evidence_row = evidence_by_id.get(evidence_id, {})
                source_id = str(evidence_row.get("sourceId") or entity.get("sourceId") or "")
                statement = _statement_row(
                    case_id=case_id,
                    subject_id=entity_id,
                    canonical_subject_id=str(entity.get("canonicalEntityId") or entity_id),
                    schema=str(entity.get("entityType") or "Thing"),
                    predicate=predicate,
                    value=str(raw_value),
                    value_type=value_type,
                    assertion_kind="sourced",
                    verification_status="source-stated",
                    confidence=1.0,
                    source_id=source_id,
                    evidence_id=evidence_id,
                    source_locator=str(evidence_row.get("sourceUrl") or ""),
                    source_excerpt=str(evidence_row.get("note") or ""),
                    published_at=str(evidence_row.get("publishedAt") or ""),
                    original_value=str(raw_value),
                    extraction_method=(
                        "followthemoney import" if entity.get("ftmSchema") else "source projection"
                    ),
                )
                statements[statement["statementId"]] = statement

    for relationship in relationships:
        relationship_id = str(relationship.get("relationshipId") or "")
        source_entity_id = str(relationship.get("fromEntityId") or "")
        target_entity_id = str(relationship.get("toEntityId") or "")
        schema = str(relationship.get("schema") or _relationship_schema(relationship.get("relationshipType")))
        verification_status = str(relationship.get("verificationStatus") or "unverified")
        assertion_kind = (
            "hypothesis"
            if verification_status == "candidate-match"
            else "analyst"
            if verification_status == "analyst-added"
            else "sourced"
        )
        for evidence_id in relationship.get("evidenceIds") or [""]:
            evidence_row = evidence_by_id.get(str(evidence_id), {})
            source_id = str(evidence_row.get("sourceId") or "")
            source_locator = str(evidence_row.get("sourceUrl") or "")
            endpoint_properties = [
                (f"{schema}:source", source_entity_id),
                (f"{schema}:target", target_entity_id),
            ]
            for predicate, object_entity_id in endpoint_properties:
                statement = _statement_row(
                    case_id=case_id,
                    subject_id=relationship_id,
                    canonical_subject_id=relationship_id,
                    schema=schema,
                    predicate=predicate,
                    value_type="entity",
                    object_entity_id=object_entity_id,
                    relationship_id=relationship_id,
                    assertion_kind=assertion_kind,
                    verification_status=verification_status,
                    confidence=float(relationship.get("confidence") or 0),
                    source_id=source_id,
                    evidence_id=str(evidence_id),
                    source_locator=source_locator,
                    source_excerpt=str(evidence_row.get("note") or ""),
                    published_at=str(evidence_row.get("publishedAt") or ""),
                    extraction_method="relationship projection",
                )
                statements[statement["statementId"]] = statement
            details = str(relationship.get("details") or "").strip()
            if details:
                statement = _statement_row(
                    case_id=case_id,
                    subject_id=relationship_id,
                    canonical_subject_id=relationship_id,
                    schema=schema,
                    predicate=f"{schema}:summary",
                    value=details,
                    value_type="text",
                    relationship_id=relationship_id,
                    assertion_kind=assertion_kind,
                    verification_status=verification_status,
                    confidence=float(relationship.get("confidence") or 0),
                    source_id=source_id,
                    evidence_id=str(evidence_id),
                    source_locator=source_locator,
                    source_excerpt=str(evidence_row.get("note") or ""),
                    published_at=str(evidence_row.get("publishedAt") or ""),
                    extraction_method="relationship projection",
                )
                statements[statement["statementId"]] = statement
            relationship_properties = relationship.get("properties") or {}
            if isinstance(relationship_properties, dict):
                schema_meta = ftm_schema_metadata(schema) or {}
                property_types = schema_meta.get("propertyTypes") or {}
                for prop_name, values in relationship_properties.items():
                    prop_values = values if isinstance(values, list) else [values]
                    value_type = str(
                        property_types.get(prop_name)
                        or infer_ftm_property_type(str(prop_name))
                    )
                    for raw_value in prop_values:
                        if raw_value in (None, ""):
                            continue
                        statement = _statement_row(
                            case_id=case_id,
                            subject_id=relationship_id,
                            canonical_subject_id=relationship_id,
                            schema=schema,
                            predicate=f"{schema}:{prop_name}",
                            value=str(raw_value),
                            value_type=value_type,
                            relationship_id=relationship_id,
                            assertion_kind=assertion_kind,
                            verification_status=verification_status,
                            confidence=float(relationship.get("confidence") or 0),
                            source_id=source_id,
                            evidence_id=str(evidence_id),
                            source_locator=source_locator,
                            source_excerpt=str(evidence_row.get("note") or ""),
                            published_at=str(evidence_row.get("publishedAt") or ""),
                            original_value=str(raw_value),
                            extraction_method=(
                                "followthemoney import"
                                if relationship.get("ftmSchema")
                                else "relationship projection"
                            ),
                        )
                        statements[statement["statementId"]] = statement
    return list(statements.values()), list(names.values())


def _projection_match_values(bundle: Dict[str, object]) -> List[Dict[str, object]]:
    case_id = str(bundle.get("caseId") or "")
    entities = bundle.get("entities") or []
    relationships = bundle.get("relationships") or []
    evidence = bundle.get("evidence") or []
    evidence_by_id = {str(row.get("evidenceId")): row for row in evidence}
    evidence_by_entity: Dict[str, Set[str]] = defaultdict(set)
    for relationship in relationships:
        for evidence_id in relationship.get("evidenceIds") or []:
            evidence_by_entity[str(relationship.get("fromEntityId"))].add(str(evidence_id))
            evidence_by_entity[str(relationship.get("toEntityId"))].add(str(evidence_id))

    rows: Dict[Tuple[str, str, str, str], Dict[str, object]] = {}
    for entity in entities:
        entity_id = str(entity.get("entityId") or "")
        if not entity_id:
            continue
        candidates: List[Tuple[str, str, object, str, str, str]] = []
        default_issuer = str(
            entity.get("identifierIssuer") or entity.get("sourceId") or ""
        )
        identifier_jurisdiction = str(
            entity.get("identifierJurisdiction")
            or (
                (entity.get("jurisdiction") or [""])[0]
                if isinstance(entity.get("jurisdiction"), list)
                else entity.get("jurisdiction") or ""
            )
        )
        for value in entity.get("identifiers") or []:
            candidates.append(
                (
                    "identifier",
                    "Thing:idNumber",
                    value,
                    default_issuer,
                    identifier_jurisdiction,
                    str(entity.get("identifierType") or "generic-identifier"),
                )
            )
        if entity.get("address"):
            candidates.append(("address", "Thing:address", entity.get("address"), "", "", ""))
        for key, value_type in [("email", "email"), ("phone", "phone"), ("url", "url")]:
            value = entity.get(key)
            values = value if isinstance(value, list) else [value]
            for item in values:
                if item:
                    candidates.append((value_type, f"Thing:{key}", item, "", "", ""))

        ftm_schema = str(entity.get("ftmSchema") or entity.get("entityType") or "Thing")
        ftm_properties = entity.get("ftmProperties")
        if not isinstance(ftm_properties, dict):
            try:
                ftm_properties = json.loads(str(entity.get("ftmPropertiesJson") or "{}"))
            except (TypeError, ValueError):
                ftm_properties = {}
        schema_meta = ftm_schema_metadata(ftm_schema) or {}
        property_types = schema_meta.get("propertyTypes") or {}
        for prop_name, values in ftm_properties.items():
            value_type = str(
                property_types.get(prop_name) or infer_ftm_property_type(str(prop_name))
            )
            if value_type not in {"identifier", "address", "email", "phone", "url"}:
                continue
            prop_values = values if isinstance(values, list) else [values]
            for value in prop_values:
                normalized_prop = str(prop_name).casefold()
                issuer = ""
                identifier_type = ""
                if value_type == "identifier":
                    if normalized_prop in {"leicode", "lei"}:
                        issuer, identifier_type = "GLEIF", "lei"
                    elif normalized_prop in {"imonumber", "imo"}:
                        issuer, identifier_type = "IMO", "imo-number"
                    elif "aircraft" in normalized_prop or "icao" in normalized_prop:
                        issuer, identifier_type = "ICAO", "aircraft-identifier"
                    else:
                        issuer = default_issuer
                        identifier_type = str(
                            entity.get("identifierType") or normalized_prop or "generic-identifier"
                        )
                candidates.append(
                    (
                        value_type,
                        f"{ftm_schema}:{prop_name}",
                        value,
                        issuer,
                        identifier_jurisdiction,
                        identifier_type,
                    )
                )

        evidence_ids = sorted(
            set(evidence_by_entity.get(entity_id) or [])
            | {str(value) for value in entity.get("evidenceIds") or [] if value}
        )
        source_ids = _ordered_unique(
            [entity.get("sourceId")]
            + [evidence_by_id.get(evidence_id, {}).get("sourceId") for evidence_id in evidence_ids]
        )
        for (
            value_type,
            predicate,
            display_value,
            issuer,
            jurisdiction,
            identifier_type,
        ) in candidates:
            normalized_unscoped = normalize_match_value(value_type, display_value)
            normalized = normalized_unscoped
            if value_type == "identifier" and normalized_unscoped:
                if not issuer:
                    # A bare numeric value without an issuer/source scope is not a
                    # safe identity pivot across jurisdictions.
                    continue
                normalized = f"{normalize_investigation_name(issuer)}::{normalized_unscoped}"
            if not normalized:
                continue
            key = (entity_id, value_type, normalized, predicate)
            row = rows.setdefault(
                key,
                {
                    "caseId": case_id,
                    "entityId": entity_id,
                    "valueId": _stable_id("match-value", value_type, normalized),
                    "valueType": value_type,
                    "normalizedValue": normalized,
                    "displayValue": str(display_value),
                    "predicate": predicate,
                    "issuer": issuer,
                    "jurisdiction": jurisdiction,
                    "identifierType": identifier_type,
                    "unscopedNormalizedValue": normalized_unscoped,
                    "sourceIds": [],
                    "evidenceIds": [],
                },
            )
            row["sourceIds"] = _ordered_unique(list(row["sourceIds"]) + source_ids)
            row["evidenceIds"] = _ordered_unique(
                list(row["evidenceIds"]) + evidence_ids
            )
    return list(rows.values())


def persist_investigation_projection(bundle: Dict[str, object]) -> None:
    statements, names = _projection_rows(bundle)
    match_values = _projection_match_values(bundle)
    if not statements and not names and not match_values:
        return
    driver = get_driver()
    params = {
        "caseId": bundle.get("caseId"),
        "statements": statements,
        "names": names,
        "matchValues": match_values,
    }
    name_query = """
    UNWIND $names AS item
    MATCH (entity:InvestigationEntity {entityId: item.entityId})
    MERGE (name:InvestigationName {normalizedName: item.normalizedName})
    ON CREATE SET name.createdAt = datetime()
    SET name.displayName = item.displayName, name.updatedAt = datetime()
    MERGE (entity)-[link:HAS_INVESTIGATION_NAME {caseId: $caseId}]->(name)
    SET link.displayName = item.displayName,
        link.aliasType = item.aliasType,
        link.platform = item.platform,
        link.assertionKind = item.assertionKind,
        link.verificationStatus = item.verificationStatus,
        link.sourceIds = reduce(
          collected = [], sourceId IN coalesce(link.sourceIds, []) + item.sourceIds |
          CASE WHEN sourceId IN collected THEN collected ELSE collected + [sourceId] END
        ),
        link.evidenceIds = reduce(
          collected = [], evidenceId IN coalesce(link.evidenceIds, []) + item.evidenceIds |
          CASE WHEN evidenceId IN collected THEN collected ELSE collected + [evidenceId] END
        ),
        link.updatedAt = datetime()
    """
    statement_query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
    UNWIND $statements AS item
    MERGE (statement:InvestigationStatement {statementId: item.statementId})
    ON CREATE SET statement.createdAt = datetime(), statement.firstSeen = datetime()
    SET statement += item, statement.updatedAt = datetime(), statement.lastSeen = datetime()
    MERGE (caseNode)-[:HAS_INVESTIGATION_STATEMENT]->(statement)
    WITH statement, item
    OPTIONAL MATCH (subject:InvestigationEntity {entityId: item.subjectId})
    FOREACH (_ IN CASE WHEN subject IS NULL THEN [] ELSE [1] END |
      MERGE (subject)-[:HAS_STATEMENT]->(statement)
    )
    WITH statement, item
    OPTIONAL MATCH (evidence:InvestigationEvidence {evidenceId: item.evidenceId})
    FOREACH (_ IN CASE WHEN evidence IS NULL THEN [] ELSE [1] END |
      MERGE (statement)-[:SUPPORTED_BY]->(evidence)
    )
    """
    match_value_query = """
    UNWIND $matchValues AS item
    MATCH (entity:InvestigationEntity {entityId: item.entityId})
    MERGE (value:InvestigationMatchValue {valueId: item.valueId})
    ON CREATE SET value.createdAt = datetime()
    SET value.valueType = item.valueType,
        value.normalizedValue = item.normalizedValue,
        value.displayValue = coalesce(value.displayValue, item.displayValue),
        value.issuer = item.issuer,
        value.jurisdiction = item.jurisdiction,
        value.identifierType = item.identifierType,
        value.unscopedNormalizedValue = item.unscopedNormalizedValue,
        value.updatedAt = datetime()
    MERGE (entity)-[link:HAS_MATCH_VALUE {caseId: item.caseId, predicate: item.predicate}]->(value)
    ON CREATE SET link.createdAt = datetime()
    SET link.sourceIds = reduce(
          collected = [], sourceId IN coalesce(link.sourceIds, []) + item.sourceIds |
          CASE WHEN sourceId IN collected THEN collected ELSE collected + [sourceId] END
        ),
        link.evidenceIds = reduce(
          collected = [], evidenceId IN coalesce(link.evidenceIds, []) + item.evidenceIds |
          CASE WHEN evidenceId IN collected THEN collected ELSE collected + [evidenceId] END
        ),
        link.updatedAt = datetime()
    """
    with _db_session(driver) as session:
        if names:
            _execute_write(session, name_query, params)
        if statements:
            _execute_write(session, statement_query, params)
        if match_values:
            _execute_write(session, match_value_query, params)
    _refresh_statement_contradictions(str(bundle.get("caseId") or ""))


def _refresh_statement_contradictions(case_id: str) -> None:
    if not case_id:
        return
    driver = get_driver()
    clear_query = """
    MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_STATEMENT]->(statement:InvestigationStatement)
    WHERE statement.predicate IN $predicates
    SET statement.contradictsStatementIds = []
    """
    contradiction_query = """
    MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_STATEMENT]->(statement:InvestigationStatement)
    WHERE statement.predicate IN $predicates AND coalesce(statement.value, '') <> ''
    WITH statement.canonicalSubjectId AS canonicalSubjectId,
         statement.predicate AS predicate,
         collect(statement) AS statements,
         collect(DISTINCT statement.value) AS values
    WHERE size(values) > 1
    UNWIND statements AS current
    SET current.contradictsStatementIds = [
      other IN statements WHERE other.value <> current.value | other.statementId
    ]
    """
    params = {
        "caseId": case_id,
        "predicates": [
            "Person:birthDate",
            "Company:name",
            "Company:registrationNumber",
            "Company:incorporationDate",
            "Company:address",
            "Company:legalForm",
            "Company:status",
        ],
    }
    with _db_session(driver) as session:
        _execute_write(session, clear_query, params)
        _execute_write(session, contradiction_query, params)


def _ensure_case(case_id: str) -> Dict[str, object]:
    driver = get_driver()
    query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
    RETURN caseNode.caseId AS caseId, caseNode.subject AS subject,
           caseNode.subjectType AS subjectType, toString(caseNode.updatedAt) AS updatedAt
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query, {"caseId": case_id})
    if not records:
        raise HTTPException(status_code=404, detail="Case not found")
    return records[0].data()


def _graph_snapshot(case_id: str) -> Dict[str, object]:
    _ensure_case(case_id)
    driver = get_driver()
    node_query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_ENTITY]->(entity:InvestigationEntity)
    RETURN entity.entityId AS id, entity.name AS label, entity.entityType AS type,
           coalesce(entity.description, '') AS description,
           coalesce(entity.isRoot, false) AS isRoot,
           properties(entity) AS properties
    """
    link_query = """
    MATCH (source:InvestigationEntity)-[link:INVESTIGATION_LINK {caseId: $caseId}]->(target:InvestigationEntity)
    RETURN link.relationshipId AS id, source.entityId AS source, target.entityId AS target,
           link.relationshipType AS label, coalesce(link.schema, '') AS schema,
           coalesce(link.confidence, 0.0) AS confidence,
           coalesce(link.verificationStatus, 'unverified') AS verificationStatus,
           coalesce(link.details, '') AS details, coalesce(link.evidenceIds, []) AS evidenceIds,
           properties(link) AS properties
    """
    with _db_session(driver) as session:
        nodes = [row.data() for row in _execute_read(session, node_query, {"caseId": case_id})]
        links = [row.data() for row in _execute_read(session, link_query, {"caseId": case_id})]
    return {"caseId": case_id, "nodes": nodes, "relationships": links}


PATH_QUERY_CATALOG = [
    {
        "queryId": "official-relative-contract",
        "title": "Official → relative → contract",
        "question": "Which declared relatives connect the subject to contracts or contracting agencies?",
        "description": "Find family paths that continue through declared contracts or business interests.",
        "parameterSchema": {"maxDepth": {"type": "integer", "default": 4, "minimum": 2, "maximum": 6}},
        "supportedEntityTypes": ["Person", "Contract", "Organization"],
        "semanticIntent": "conflict-of-interest lead generation",
    },
    {
        "queryId": "sanctioned-ownership",
        "title": "Screening candidate → ownership network",
        "question": "Which owned assets or entities sit behind a sanctions or PEP screening candidate?",
        "description": "Traverse candidate identity and ownership links while preserving the unresolved-match warning.",
        "parameterSchema": {"includeCandidateMatches": {"type": "boolean", "default": False}, "maxDepth": {"type": "integer", "default": 4}},
        "supportedEntityTypes": ["Person", "Organization", "Asset", "Screening record"],
        "semanticIntent": "sanctions ownership lead generation",
    },
    {
        "queryId": "shared-address",
        "title": "Shared address network",
        "question": "Which assets or entities resolve to the same address?",
        "description": "Use normalized address nodes as pivots without assuming common ownership.",
        "parameterSchema": {"maxDepth": {"type": "integer", "default": 3}},
        "supportedEntityTypes": ["Address", "Asset", "Organization"],
        "semanticIntent": "shared-identifier lead generation",
    },
    {
        "queryId": "follow-money",
        "title": "Follow the money",
        "question": "What evidence-backed ownership, business, contract, and payment paths leave this entity?",
        "description": "Traverse money-relevant relationships from the case subject or a selected entity.",
        "parameterSchema": {"startEntityId": {"type": "string"}, "maxDepth": {"type": "integer", "default": 4}},
        "supportedEntityTypes": ["Person", "Organization", "Asset", "Contract", "Payment", "BankAccount"],
        "semanticIntent": "financial-network exploration",
    },
    {
        "queryId": "shortest-evidence-path",
        "title": "Shortest evidence path",
        "question": "What is the shortest sourced path between two selected entities?",
        "description": "Return the shortest simple evidence-backed paths and their provenance.",
        "parameterSchema": {"startEntityId": {"type": "string", "required": True}, "targetEntityId": {"type": "string", "required": True}, "maxDepth": {"type": "integer", "default": 6}},
        "supportedEntityTypes": ["*"],
        "semanticIntent": "connection explanation",
    },
]


@router.get("/cases/{case_id}/workspace")
def get_investigation_workspace(case_id: str):
    case_row = _ensure_case(case_id)
    driver = get_driver()
    queries = {
        "datasets": "MATCH (:DueDiligenceCase {caseId: $caseId})-[:USES_INVESTIGATION_SOURCE]->(n) RETURN count(DISTINCT n) AS count",
        "entities": "MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_ENTITY]->(n) RETURN count(DISTINCT n) AS count",
        "statements": "MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_STATEMENT]->(n) RETURN count(DISTINCT n) AS count",
        "evidence": "MATCH (:DueDiligenceCase {caseId: $caseId})-[:USES_INVESTIGATION_EVIDENCE]->(n) RETURN count(DISTINCT n) AS count",
        "matchValues": "MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_ENTITY]->()-[:HAS_MATCH_VALUE {caseId: $caseId}]->(value) RETURN count(DISTINCT value) AS count",
        "unresolvedCandidates": "MATCH (caseNode:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_ENTITY]->(a), (caseNode)-[:HAS_INVESTIGATION_ENTITY]->(b) WHERE a.entityId < b.entityId AND coalesce(a.canonicalEntityId, a.entityId) <> coalesce(b.canonicalEntityId, b.entityId) AND (EXISTS { MATCH (a)-[:HAS_INVESTIGATION_NAME {caseId: $caseId}]->(name)<-[:HAS_INVESTIGATION_NAME {caseId: $caseId}]-(b) } OR EXISTS { MATCH (a)-[:HAS_MATCH_VALUE {caseId: $caseId}]->(value)<-[:HAS_MATCH_VALUE {caseId: $caseId}]-(b) }) AND NOT EXISTS { MATCH (caseNode)-[:HAS_RESOLUTION_REVIEW]->(review:EntityResolutionReview) WHERE review.pairKey = a.entityId + '|' + b.entityId AND review.decision IN ['accepted', 'rejected'] } RETURN count(DISTINCT a.entityId + '|' + b.entityId) AS count",
        "pathRuns": "MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_PATH_RUN]->(n) RETURN count(DISTINCT n) AS count",
        "importRuns": "MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_IMPORT_RUN]->(n) RETURN count(DISTINCT n) AS count",
        "findings": "MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_FINDING]->(n) RETURN count(DISTINCT n) AS count",
        "acceptedFindings": "MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_FINDING]->(n {status: 'accepted'}) RETURN count(DISTINCT n) AS count",
        "openFindings": "MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_FINDING]->(n) WHERE n.status IN ['open', 'needs-research'] RETURN count(DISTINCT n) AS count",
        "publications": "MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_PUBLICATION]->(n) RETURN count(DISTINCT n) AS count",
        "provenanceGaps": "MATCH (a:InvestigationEntity)-[link:INVESTIGATION_LINK {caseId: $caseId}]->(b:InvestigationEntity) WHERE size(coalesce(link.evidenceIds, [])) = 0 RETURN count(link) AS count",
    }
    counts: Dict[str, int] = {}
    with _db_session(driver) as session:
        for key, query in queries.items():
            rows = _execute_read(session, query, {"caseId": case_id})
            counts[key] = int((rows[0].get("count") if rows else 0) or 0)
    blockers = []
    if not counts["datasets"]:
        blockers.append("Add at least one source dataset.")
    if counts["unresolvedCandidates"]:
        blockers.append(f"Review {counts['unresolvedCandidates']} unresolved identity candidate(s).")
    if counts["provenanceGaps"]:
        blockers.append(f"Repair {counts['provenanceGaps']} relationship(s) without evidence.")
    if not counts["acceptedFindings"]:
        blockers.append("Accept at least one evidence-backed finding before publication.")
    return {
        "caseId": case_id,
        "subject": case_row.get("subject"),
        "lastActivityAt": case_row.get("updatedAt"),
        "counts": counts,
        "blockers": blockers,
        "publishReady": not blockers,
        "workflow": ["sources", "entities", "resolve", "follow-the-money", "findings", "publish"],
    }


@router.get("/cases/{case_id}/datasets")
def list_investigation_datasets(case_id: str):
    _ensure_case(case_id)
    driver = get_driver()
    query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})-[:USES_INVESTIGATION_SOURCE]->(source:InvestigationDataSource)
    OPTIONAL MATCH (caseNode)-[:USES_INVESTIGATION_EVIDENCE]->(evidence:InvestigationEvidence {sourceId: source.sourceId})
    WITH caseNode, source, count(DISTINCT evidence) AS evidenceCount
    OPTIONAL MATCH (caseNode)-[:HAS_INVESTIGATION_STATEMENT]->(statement:InvestigationStatement {sourceId: source.sourceId})
    WITH source, evidenceCount, count(DISTINCT statement) AS statementCount,
         count(DISTINCT statement.subjectId) AS recordCount,
         collect(DISTINCT statement.schema) AS schemas,
         collect(DISTINCT statement.predicate) AS predicates,
         max(statement.lastSeen) AS lastSeen
    OPTIONAL MATCH (source)-[:HAS_IMPORT_RUN]->(run:InvestigationImportRun {caseId: $caseId})
    WITH source, evidenceCount, statementCount, recordCount, schemas, predicates, lastSeen,
         count(DISTINCT run) AS importRunCount, max(run.completedAt) AS lastRunAt,
         sum(coalesce(run.errorCount, 0)) AS importErrorCount
    RETURN source.sourceId AS sourceId, source.sourceId AS datasetId,
           source.name AS name, coalesce(source.sourceType, 'Public source') AS type,
           coalesce(source.url, '') AS url, coalesce(source.license, '') AS license,
           coalesce(source.ingestionMode, 'projection') AS ingestionMode,
           coalesce(source.connector, '') AS connector,
           coalesce(source.platform, '') AS platform,
           coalesce(source.actorId, '') AS actorId,
           coalesce(source.actorName, '') AS actorName,
           coalesce(source.actorUrl, '') AS actorUrl,
           coalesce(source.resolvedActorId, '') AS resolvedActorId,
           coalesce(source.actorSchemaVersion, '') AS actorSchemaVersion,
           coalesce(source.actorBuildId, '') AS actorBuildId,
           coalesce(source.actorBuildNumber, '') AS actorBuildNumber,
           coalesce(source.externalRunId, '') AS externalRunId,
           coalesce(source.externalDatasetId, '') AS externalDatasetId,
           coalesce(source.pricingModel, '') AS pricingModel,
           coalesce(source.usageTotalUsd, 0.0) AS usageTotalUsd,
           coalesce(source.requestedCostCapUsd, 0.0) AS requestedCostCapUsd,
           coalesce(source.chargedItemCount, 0) AS chargedItemCount,
           coalesce(source.sourceTotalItems, 0) AS sourceTotalItems,
           coalesce(source.datasetTruncated, false) AS datasetTruncated,
           coalesce(source.schemaRejectedItems, 0) AS schemaRejectedItems,
           toString(source.fetchedAt) AS fetchedAt,
           coalesce(source.publicContentOnly, false) AS publicContentOnly,
           coalesce(source.collectionPolicy, '') AS collectionPolicy,
           coalesce(source.retentionDays, 0) AS retentionDays,
           coalesce(source.retentionEnforcement, '') AS retentionEnforcement,
           coalesce(source.rawArtifactPolicy, '') AS rawArtifactPolicy,
           CASE WHEN statementCount > 0 THEN 'ready' ELSE 'registered' END AS status,
           toString(coalesce(lastRunAt, lastSeen)) AS lastImportedAt,
           recordCount, statementCount, evidenceCount,
           importErrorCount AS errorCount, importRunCount,
           [schema IN schemas WHERE schema IS NOT NULL] AS ontologySchemas,
           [predicate IN predicates WHERE predicate IS NOT NULL] AS ontologyMappings,
           CASE WHEN statementCount = 0 THEN 0.0 ELSE 1.0 END AS provenanceCompleteness,
           {state: CASE WHEN coalesce(lastRunAt, lastSeen) IS NULL THEN 'unknown' ELSE 'observed' END,
            lastImportedAt: toString(coalesce(lastRunAt, lastSeen))} AS freshness,
           toString(source.updatedAt) AS updatedAt
    ORDER BY source.name
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query, {"caseId": case_id})
    return [row.data() for row in records]


@router.get("/cases/{case_id}/datasets/{source_id}/imports")
def list_investigation_dataset_imports(
    case_id: str,
    source_id: str,
    limit: int = Query(default=25, ge=1, le=100),
):
    _ensure_case(case_id)
    driver = get_driver()
    query = """
    MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_IMPORT_RUN]->(run:InvestigationImportRun {sourceId: $sourceId})
    RETURN run.runId AS runId, run.sourceId AS sourceId, run.status AS status,
           coalesce(run.connector, '') AS connector,
           coalesce(run.platform, '') AS platform,
           coalesce(run.actorId, '') AS actorId,
           coalesce(run.actorName, '') AS actorName,
           coalesce(run.actorUrl, '') AS actorUrl,
           coalesce(run.resolvedActorId, '') AS resolvedActorId,
           coalesce(run.actorSchemaVersion, '') AS actorSchemaVersion,
           coalesce(run.actorBuildId, '') AS actorBuildId,
           coalesce(run.actorBuildNumber, '') AS actorBuildNumber,
           coalesce(run.externalRunId, '') AS externalRunId,
           coalesce(run.externalDatasetId, '') AS externalDatasetId,
           coalesce(run.externalRunStatus, '') AS externalRunStatus,
           coalesce(run.pricingModel, '') AS pricingModel,
           coalesce(run.usageTotalUsd, 0.0) AS usageTotalUsd,
           coalesce(run.requestedCostCapUsd, 0.0) AS requestedCostCapUsd,
           coalesce(run.chargedItemCount, 0) AS chargedItemCount,
           coalesce(run.chargedEventCountsJson, '{}') AS chargedEventCountsJson,
           coalesce(run.rawItemCount, 0) AS rawItemCount,
           coalesce(run.acceptedItemCount, 0) AS acceptedItemCount,
           coalesce(run.rejectedItemCount, 0) AS rejectedItemCount,
           coalesce(run.duplicateItemCount, 0) AS duplicateItemCount,
           coalesce(run.entityCount, 0) AS entityCount,
           coalesce(run.relationshipCount, 0) AS relationshipCount,
           coalesce(run.evidenceCount, 0) AS evidenceCount,
           coalesce(run.errorCount, 0) AS errorCount,
           coalesce(run.sourceTotalItems, 0) AS sourceTotalItems,
           coalesce(run.datasetTruncated, false) AS datasetTruncated,
           coalesce(run.fetchPageCount, 0) AS fetchPageCount,
           coalesce(run.schemaRejectedItemCount, 0) AS schemaRejectedItemCount,
           coalesce(run.schemaRejectionReasonsJson, '{}') AS schemaRejectionReasonsJson,
           coalesce(run.inputMode, '') AS inputMode,
           coalesce(run.retentionDays, 0) AS retentionDays,
           toString(run.retentionExpiresAt) AS retentionExpiresAt,
           coalesce(run.retentionEnforcement, '') AS retentionEnforcement,
           coalesce(run.rawArtifactPolicy, '') AS rawArtifactPolicy,
           coalesce(run.retentionStatus, '') AS retentionStatus,
           toString(run.contentExpiredAt) AS contentExpiredAt,
           toString(run.fetchedAt) AS fetchedAt,
           coalesce(run.inputFingerprint, '') AS inputFingerprint,
           toString(run.startedAt) AS startedAt,
           toString(run.completedAt) AS completedAt
    ORDER BY run.startedAt DESC
    LIMIT $limit
    """
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            query,
            {"caseId": case_id, "sourceId": source_id, "limit": int(limit)},
        )
    return [row.data() for row in records]


@router.get("/cases/{case_id}/statements")
def list_investigation_statements(
    case_id: str,
    subject_id: Optional[str] = Query(default=None, alias="subjectId"),
    predicate: Optional[str] = Query(default=None),
    source_id: Optional[str] = Query(default=None, alias="sourceId"),
    assertion_kind: Optional[str] = Query(default=None, alias="assertionKind"),
    verification_status: Optional[str] = Query(default=None, alias="verificationStatus"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    _ensure_case(case_id)
    driver = get_driver()
    query = """
    MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_STATEMENT]->(statement:InvestigationStatement)
    WHERE ($subjectId IS NULL OR statement.subjectId = $subjectId)
      AND ($predicate IS NULL OR statement.predicate = $predicate)
      AND ($sourceId IS NULL OR statement.sourceId = $sourceId)
      AND ($assertionKind IS NULL OR statement.assertionKind = $assertionKind)
      AND ($verificationStatus IS NULL OR statement.verificationStatus = $verificationStatus)
    RETURN statement.statementId AS statementId,
           statement.subjectId AS subjectId,
           statement.canonicalSubjectId AS canonicalSubjectId,
           statement.schema AS schema,
           statement.predicate AS predicate,
           CASE WHEN coalesce(statement.objectEntityId, '') <> ''
             THEN {entityId: statement.objectEntityId, value: null, valueType: 'entity'}
             ELSE {entityId: null, value: statement.value, valueType: statement.valueType}
           END AS object,
           statement.assertionKind AS assertionKind,
           statement.verificationStatus AS verificationStatus,
           statement.confidence AS confidence,
           statement.sourceId AS sourceId,
           statement.evidenceId AS evidenceId,
           coalesce(statement.sourceLocator, '') AS sourceLocator,
           coalesce(statement.sourceExcerpt, '') AS sourceExcerpt,
           coalesce(statement.sourceRecordKey, '') AS sourceRecordKey,
           coalesce(statement.originalValue, '') AS originalValue,
           coalesce(statement.extractionMethod, '') AS extractionMethod,
           coalesce(statement.supersedesStatementIds, []) AS supersedesStatementIds,
           coalesce(statement.contradictsStatementIds, []) AS contradictsStatementIds,
           toString(statement.firstSeen) AS observedAt,
           coalesce(statement.publishedAt, '') AS publishedAt,
           toString(statement.lastSeen) AS importedAt,
           statement.relationshipId AS relationshipId
    ORDER BY statement.lastSeen DESC, statement.statementId
    SKIP $offset LIMIT $limit
    """
    params = {
        "caseId": case_id,
        "subjectId": subject_id,
        "predicate": predicate,
        "sourceId": source_id,
        "assertionKind": assertion_kind,
        "verificationStatus": verification_status,
        "limit": int(limit),
        "offset": int(offset),
    }
    with _db_session(driver) as session:
        records = _execute_read(session, query, params)
    return [row.data() for row in records]


@router.get("/cases/{case_id}/entities")
def list_investigation_entities(
    case_id: str,
    q: Optional[str] = Query(default=None),
    entity_type: Optional[str] = Query(default=None, alias="entityType"),
    resolution_state: Optional[str] = Query(default=None, alias="resolutionState"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    _ensure_case(case_id)
    driver = get_driver()
    query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_ENTITY]->(entity:InvestigationEntity)
    WHERE ($q IS NULL OR toLower(entity.name) CONTAINS toLower($q)
      OR EXISTS {
        MATCH (entity)-[aliasLink:HAS_INVESTIGATION_NAME {caseId: $caseId}]->(:InvestigationName)
        WHERE toLower(aliasLink.displayName) CONTAINS toLower($q)
      })
      AND ($entityType IS NULL OR entity.entityType = $entityType)
    OPTIONAL MATCH (entity)-[:HAS_STATEMENT]->(statement:InvestigationStatement {caseId: $caseId})
    WITH caseNode, entity, count(DISTINCT statement) AS statementCount,
         collect(DISTINCT statement.sourceId) AS statementSources,
         collect(DISTINCT CASE WHEN statement.predicate CONTAINS 'idNumber' THEN statement.value END) AS identifiers,
         collect(DISTINCT CASE WHEN statement.predicate CONTAINS 'jurisdiction' THEN statement.value END) AS jurisdictions
    OPTIONAL MATCH (entity)-[connection:INVESTIGATION_LINK {caseId: $caseId}]-()
    WITH caseNode, entity, statementCount, statementSources, identifiers, jurisdictions,
         count(DISTINCT connection) AS connectionCount
    OPTIONAL MATCH (entity)-[:HAS_INVESTIGATION_NAME {caseId: $caseId}]->(name)<-[:HAS_INVESTIGATION_NAME {caseId: $caseId}]-(candidate)<-[:HAS_INVESTIGATION_ENTITY]-(caseNode)
    WHERE candidate <> entity AND coalesce(candidate.canonicalEntityId, candidate.entityId) <> coalesce(entity.canonicalEntityId, entity.entityId)
    WITH entity, statementCount, statementSources, identifiers, jurisdictions, connectionCount,
         count(DISTINCT candidate) AS candidateCount
    WITH entity, statementCount, statementSources, identifiers, jurisdictions, connectionCount, candidateCount,
         CASE WHEN candidateCount > 0 THEN 'candidate' WHEN entity.canonicalEntityId IS NOT NULL AND entity.canonicalEntityId <> entity.entityId THEN 'resolved' ELSE 'unresolved' END AS resolutionState
    WHERE ($resolutionState IS NULL OR resolutionState = $resolutionState)
    RETURN entity.entityId AS id, entity.name AS displayName, entity.entityType AS type,
           coalesce(entity.entityRole, '') AS entityRole,
           coalesce(entity.canonicalEntityId, entity.entityId) AS canonicalEntityId,
           [value IN identifiers WHERE value IS NOT NULL] AS identifiers,
           CASE WHEN coalesce(entity.address, '') = '' THEN [] ELSE [entity.address] END AS addresses,
           [value IN jurisdictions WHERE value IS NOT NULL] AS jurisdictions,
           [value IN statementSources WHERE value IS NOT NULL] AS sourceIds,
           statementCount, connectionCount, resolutionState, candidateCount,
           coalesce(entity.isRoot, false) AS isRoot
    ORDER BY entity.isRoot DESC, entity.name
    SKIP $offset LIMIT $limit
    """
    params = {
        "caseId": case_id,
        "q": q.strip() if q and q.strip() else None,
        "entityType": entity_type.strip() if entity_type and entity_type.strip() else None,
        "resolutionState": resolution_state.strip() if resolution_state and resolution_state.strip() else None,
        "limit": int(limit),
        "offset": int(offset),
    }
    with _db_session(driver) as session:
        records = _execute_read(session, query, params)
    return [row.data() for row in records]


def _load_investigation_aliases(
    case_id: str, entity_id: str, include_cluster: bool = True
) -> List[Dict[str, object]]:
    _ensure_case(case_id)
    driver = get_driver()
    query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_ENTITY]->(requested:InvestigationEntity {entityId: $entityId})
    WITH caseNode, requested, coalesce(requested.canonicalEntityId, requested.entityId) AS canonicalEntityId
    MATCH (caseNode)-[:HAS_INVESTIGATION_ENTITY]->(member:InvestigationEntity)
    WHERE member = requested OR ($includeCluster AND coalesce(member.canonicalEntityId, member.entityId) = canonicalEntityId)
    MATCH (member)-[link:HAS_INVESTIGATION_NAME {caseId: $caseId}]->(name:InvestigationName)
    RETURN member.entityId + '|' + name.normalizedName AS aliasId,
           member.entityId AS sourceEntityId,
           member.entityType AS sourceEntityType,
           member.entityId = requested.entityId AS belongsToRequestedEntity,
           link.displayName AS value,
           name.normalizedName AS normalizedValue,
           coalesce(link.aliasType, CASE WHEN member.entityType = 'Social profile' THEN 'social-display' ELSE 'source-alias' END) AS aliasType,
           coalesce(link.platform, member.platform, '') AS platform,
           coalesce(link.assertionKind, 'sourced') AS assertionKind,
           coalesce(link.verificationStatus, 'source-stated') AS verificationStatus,
           coalesce(link.sourceIds, []) AS sourceIds,
           coalesce(link.evidenceIds, []) AS evidenceIds,
           canonicalEntityId
    ORDER BY belongsToRequestedEntity DESC, aliasType, value
    """
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            query,
            {
                "caseId": case_id,
                "entityId": entity_id,
                "includeCluster": bool(include_cluster),
            },
        )
    return [row.data() for row in records]


@router.get("/cases/{case_id}/entities/{entity_id}/aliases")
def list_investigation_entity_aliases(
    case_id: str,
    entity_id: str,
    include_cluster: bool = Query(default=True, alias="includeCluster"),
):
    aliases = _load_investigation_aliases(case_id, entity_id, include_cluster)
    if not aliases:
        driver = get_driver()
        query = """
        MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_ENTITY]->(entity:InvestigationEntity {entityId: $entityId})
        RETURN count(entity) AS count
        """
        with _db_session(driver) as session:
            records = _execute_read(
                session, query, {"caseId": case_id, "entityId": entity_id}
            )
        if not records or int(records[0].get("count") or 0) == 0:
            raise HTTPException(status_code=404, detail="Entity is not attached to this case")
    return {
        "caseId": case_id,
        "entityId": entity_id,
        "includeCluster": include_cluster,
        "aliases": aliases,
    }


@router.get("/cases/{case_id}/entities/{entity_id}")
def get_investigation_entity_dossier(case_id: str, entity_id: str):
    entities = list_investigation_entities(
        case_id,
        q=None,
        entity_type=None,
        resolution_state=None,
        limit=200,
        offset=0,
    )
    entity = next((row for row in entities if row.get("id") == entity_id), None)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity is not attached to this case")
    statements = list_investigation_statements(
        case_id,
        subject_id=entity_id,
        predicate=None,
        source_id=None,
        assertion_kind=None,
        verification_status=None,
        limit=500,
        offset=0,
    )
    graph = _graph_snapshot(case_id)
    connections = [
        row
        for row in graph["relationships"]
        if row.get("source") == entity_id or row.get("target") == entity_id
    ]
    groups: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for statement in statements:
        groups[str(statement.get("predicate") or "Other")].append(statement)
    return {
        "caseId": case_id,
        "entity": entity,
        "aliases": _load_investigation_aliases(case_id, entity_id, True),
        "statementGroups": [
            {"predicate": predicate, "statements": rows}
            for predicate, rows in sorted(groups.items())
        ],
        "connections": connections,
        "provenance": {
            "statementCount": len(statements),
            "sourceIds": _ordered_unique([row.get("sourceId") for row in statements]),
            "evidenceIds": _ordered_unique([row.get("evidenceId") for row in statements]),
        },
    }


@router.get("/cases/{case_id}/graph/metadata")
def get_investigation_graph_metadata(case_id: str):
    _ensure_case(case_id)
    driver = get_driver()
    assertion_query = """
    MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_STATEMENT]->(statement:InvestigationStatement)
    RETURN statement.assertionKind AS key, count(statement) AS count
    """
    verification_query = """
    MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_STATEMENT]->(statement:InvestigationStatement)
    RETURN statement.verificationStatus AS key, count(statement) AS count
    """
    graph = _graph_snapshot(case_id)
    with _db_session(driver) as session:
        assertion_rows = _execute_read(session, assertion_query, {"caseId": case_id})
        verification_rows = _execute_read(session, verification_query, {"caseId": case_id})
    return {
        "caseId": case_id,
        "nodeCount": len(graph["nodes"]),
        "relationshipCount": len(graph["relationships"]),
        "assertionKinds": {str(row.get("key") or "unknown"): int(row.get("count") or 0) for row in assertion_rows},
        "verificationStates": {str(row.get("key") or "unknown"): int(row.get("count") or 0) for row in verification_rows},
        "rendering": {
            "sourced": "solid",
            "inferred": "dashed",
            "hypothesis": "dotted",
            "analyst": "double",
        },
    }


def _ftm_resolution_proxy(
    row: Dict[str, object], preferred_schema: Optional[str] = None
):
    model = official_ftm_model()
    if model is None:
        return None
    entity_type = str(row.get("type") or "")
    schema_name = preferred_schema or entity_type
    schema = model.get(schema_name)
    if schema is None or not schema.matchable:
        schema_name = "Person" if entity_type in {"Person", "Screening record"} else "LegalEntity"
    proxy = model.make_entity(schema_name)
    proxy.id = str(row.get("id") or "")
    names = _ordered_unique(
        [row.get("displayName")]
        + [item.get("display") for item in row.get("names") or [] if isinstance(item, dict)]
    )
    proxy.add("name", names, quiet=True)
    properties = row.get("properties") or {}
    if isinstance(properties, dict):
        try:
            ftm_properties = json.loads(str(properties.get("ftmPropertiesJson") or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            ftm_properties = {}
        if isinstance(ftm_properties, dict):
            for property_name, property_values in ftm_properties.items():
                if property_values not in (None, "", []):
                    proxy.add(str(property_name), property_values, quiet=True, fuzzy=True)
        mappings = {
            "birthYear": "birthDate",
            "birthDate": "birthDate",
            "address": "address",
            "jurisdiction": "jurisdiction",
            "country": "country",
            "nationality": "nationality",
            "identifiers": "idNumber",
            "idNumber": "idNumber",
            "registrationNumber": "registrationNumber",
            "taxNumber": "taxNumber",
        }
        for source_key, target_key in mappings.items():
            value = properties.get(source_key)
            if value not in (None, "", []):
                proxy.add(target_key, value, quiet=True, fuzzy=True)
    return proxy


def _fallback_resolution_evaluation(
    left: Dict[str, object],
    right: Dict[str, object],
    shared_names: Set[str],
    shared_match_values: Dict[str, Set[str]],
) -> Tuple[float, List[Dict[str, object]], List[Dict[str, object]], str]:
    signals: List[Dict[str, object]] = []
    conflicts: List[Dict[str, object]] = []
    score = 0.0
    if shared_names:
        signals.append(
            {
                "type": "shared-normalized-name",
                "label": "Shared normalized name",
                "values": sorted(shared_names),
                "weight": 0.62,
            }
        )
        score = 0.62
    match_weights = {
        "identifier": (0.95, "Shared identifier"),
        "email": (0.9, "Shared email address"),
        "phone": (0.9, "Shared phone number"),
        "address": (0.72, "Shared normalized address"),
        "url": (0.65, "Shared URL"),
    }
    for value_type, values in sorted(shared_match_values.items()):
        if not values or value_type not in match_weights:
            continue
        weight, label = match_weights[value_type]
        signals.append(
            {
                "type": f"shared-{value_type}",
                "label": label,
                "values": sorted(values),
                "weight": weight,
            }
        )
        score = max(score, weight)
    if shared_names and shared_match_values:
        score = min(1.0, score + 0.04)
    left_props = left.get("properties") or {}
    right_props = right.get("properties") or {}
    left_birth = str(left_props.get("birthYear") or left_props.get("birthDate") or "")
    right_birth = str(right_props.get("birthYear") or right_props.get("birthDate") or "")
    if left_birth and right_birth:
        if left_birth == right_birth:
            signals.append(
                {
                    "type": "shared-birth-year",
                    "label": "Shared birth year",
                    "values": [left_birth],
                    "weight": 0.2,
                }
            )
            score += 0.2
        else:
            conflicts.append(
                {"type": "birth-year-conflict", "left": left_birth, "right": right_birth}
            )
            score -= 0.25
    if left.get("type") == right.get("type"):
        signals.append(
            {
                "type": "compatible-schema",
                "label": "Same entity type",
                "values": [left.get("type")],
                "weight": 0.08,
            }
        )
        score += 0.08
    elif {left.get("type"), right.get("type")} <= {
        "Person",
        "Screening record",
        "Social profile",
    }:
        signals.append(
            {
                "type": "screening-profile",
                "label": "Compatible person-profile comparison",
                "values": [],
                "weight": 0.04,
            }
        )
        score += 0.04
    else:
        conflicts.append(
            {"type": "schema-conflict", "left": left.get("type"), "right": right.get("type")}
        )
        score -= 0.15
    return max(0.0, min(score, 1.0)), signals, conflicts, "evidence-rule-v1"


def _resolution_evaluation(
    left: Dict[str, object],
    right: Dict[str, object],
    shared_names: Set[str],
    shared_match_values: Dict[str, Set[str]],
) -> Tuple[float, List[Dict[str, object]], List[Dict[str, object]], str]:
    logic_v2 = official_logic_v2()
    if logic_v2 is None:
        return _fallback_resolution_evaluation(
            left, right, shared_names, shared_match_values
        )
    try:
        preferred_schema = (
            "Person"
            if {left.get("type"), right.get("type")}
            <= {"Person", "Screening record", "Social profile"}
            else None
        )
        left_proxy = _ftm_resolution_proxy(left, preferred_schema)
        right_proxy = _ftm_resolution_proxy(right, preferred_schema)
        if left_proxy is None or right_proxy is None:
            return _fallback_resolution_evaluation(
                left, right, shared_names, shared_match_values
            )
        result = logic_v2.compare(left_proxy, right_proxy, logic_v2.default_config())
        signals: List[Dict[str, object]] = []
        conflicts: List[Dict[str, object]] = []
        for name, explanation in result.explanations.items():
            row = {
                "type": name.replace("_", "-"),
                "label": name.replace("_", " ").title(),
                "values": _ordered_unique([explanation.query, explanation.candidate]),
                "weight": round(float(explanation.score), 4),
                "detail": explanation.detail or "",
            }
            if float(explanation.score) < 0:
                conflicts.append(row)
            else:
                signals.append(row)
        if not signals:
            return _fallback_resolution_evaluation(
                left, right, shared_names, shared_match_values
            )
        return (
            max(0.0, min(float(result.score), 1.0)),
            signals,
            conflicts,
            "nomenklatura-logic-v2",
        )
    except Exception:
        return _fallback_resolution_evaluation(left, right, shared_names, shared_match_values)


def _load_resolution_candidates(case_id: str) -> List[Dict[str, object]]:
    _ensure_case(case_id)
    driver = get_driver()
    entity_query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_ENTITY]->(entity:InvestigationEntity)
    OPTIONAL MATCH (entity)-[nameLink:HAS_INVESTIGATION_NAME {caseId: $caseId}]->(name:InvestigationName)
    OPTIONAL MATCH (entity)-[:HAS_STATEMENT]->(statement:InvestigationStatement {caseId: $caseId})
    OPTIONAL MATCH (entity)-[valueLink:HAS_MATCH_VALUE {caseId: $caseId}]->(matchValue:InvestigationMatchValue)
    RETURN entity.entityId AS id, entity.name AS displayName, entity.entityType AS type,
           coalesce(entity.entityRole, '') AS entityRole,
           coalesce(entity.canonicalEntityId, entity.entityId) AS canonicalEntityId,
           properties(entity) AS properties,
           collect(DISTINCT {normalized: name.normalizedName, display: nameLink.displayName}) AS names,
           collect(DISTINCT {type: matchValue.valueType, normalized: matchValue.normalizedValue,
                             display: matchValue.displayValue, predicate: valueLink.predicate}) AS matchValues,
           collect(DISTINCT statement.sourceId) AS sourceIds,
           collect(DISTINCT statement.evidenceId) AS evidenceIds
    """
    review_query = """
    MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_RESOLUTION_REVIEW]->(review:EntityResolutionReview)
    RETURN review.candidateId AS candidateId, review.decision AS decision,
           review.rationale AS rationale, review.reviewedBy AS reviewedBy,
           toString(review.reviewedAt) AS reviewedAt
    """
    with _db_session(driver) as session:
        entity_rows = [row.data() for row in _execute_read(session, entity_query, {"caseId": case_id})]
        review_rows = [row.data() for row in _execute_read(session, review_query, {"caseId": case_id})]
    reviews = {str(row.get("candidateId")): row for row in review_rows}
    by_name: Dict[str, Set[str]] = defaultdict(set)
    by_match_value: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    entities = {str(row.get("id")): row for row in entity_rows}
    for entity in entity_rows:
        for name in entity.get("names") or []:
            normalized = str((name or {}).get("normalized") or "")
            if normalized:
                by_name[normalized].add(str(entity.get("id")))
        for match_value in entity.get("matchValues") or []:
            value_type = str((match_value or {}).get("type") or "")
            normalized = str((match_value or {}).get("normalized") or "")
            if value_type and normalized:
                by_match_value[(value_type, normalized)].add(str(entity.get("id")))

    pairs: Dict[Tuple[str, str], Dict[str, Set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for normalized, entity_ids in by_name.items():
        ordered = sorted(entity_ids)
        for left_index in range(len(ordered)):
            for right_index in range(left_index + 1, len(ordered)):
                pairs[(ordered[left_index], ordered[right_index])]["name"].add(normalized)
    for (value_type, normalized), entity_ids in by_match_value.items():
        # Very common pivots (for example a headquarters address) are useful for
        # graph exploration but too ambiguous to create pairwise identity candidates.
        if len(entity_ids) > 50:
            continue
        ordered = sorted(entity_ids)
        for left_index in range(len(ordered)):
            for right_index in range(left_index + 1, len(ordered)):
                pairs[(ordered[left_index], ordered[right_index])][value_type].add(
                    normalized
                )

    candidates: List[Dict[str, object]] = []
    for (left_id, right_id), shared_values in pairs.items():
        shared_names = shared_values.get("name", set())
        shared_match_values = {
            key: values for key, values in shared_values.items() if key != "name"
        }
        left = entities[left_id]
        right = entities[right_id]
        if left.get("canonicalEntityId") == right.get("canonicalEntityId"):
            continue
        candidate_id = _stable_id("resolution", case_id, left_id, right_id)
        score, signals, conflicts, matching_engine = _resolution_evaluation(
            left, right, shared_names, shared_match_values
        )
        review = reviews.get(candidate_id)
        candidates.append(
            {
                "candidateId": candidate_id,
                "left": {
                    "id": left_id,
                    "displayName": left.get("displayName"),
                    "type": left.get("type"),
                    "entityRole": left.get("entityRole"),
                    "sourceIds": _ordered_unique(left.get("sourceIds") or []),
                },
                "right": {
                    "id": right_id,
                    "displayName": right.get("displayName"),
                    "type": right.get("type"),
                    "entityRole": right.get("entityRole"),
                    "sourceIds": _ordered_unique(right.get("sourceIds") or []),
                },
                "score": round(max(0.0, min(score, 1.0)), 3),
                "matchingEngine": matching_engine,
                "sharedValues": {
                    key: sorted(values) for key, values in shared_match_values.items()
                },
                "signals": signals,
                "conflicts": conflicts,
                "sourceIds": _ordered_unique((left.get("sourceIds") or []) + (right.get("sourceIds") or [])),
                "evidenceIds": _ordered_unique((left.get("evidenceIds") or []) + (right.get("evidenceIds") or [])),
                "status": review.get("decision") if review else "pending",
                "review": review,
            }
        )
    candidates.sort(key=lambda row: (-float(row.get("score") or 0), str(row.get("candidateId"))))
    return candidates


@router.get("/cases/{case_id}/resolution-candidates")
def list_entity_resolution_candidates(
    case_id: str,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    candidates = _load_resolution_candidates(case_id)
    if status:
        candidates = [row for row in candidates if row.get("status") == status]
    return {
        "caseId": case_id,
        "summary": {
            "total": len(candidates),
            "pending": sum(1 for row in candidates if row.get("status") == "pending"),
            "accepted": sum(1 for row in candidates if row.get("status") == "accepted"),
            "rejected": sum(1 for row in candidates if row.get("status") == "rejected"),
            "deferred": sum(1 for row in candidates if row.get("status") == "deferred"),
        },
        "candidates": candidates[: int(limit)],
    }


@router.post("/cases/{case_id}/resolution-candidates/{candidate_id}/review")
def review_entity_resolution_candidate(
    request: Request, case_id: str, candidate_id: str, payload: EntityResolutionReviewRequest
):
    decision = payload.decision.strip().casefold()
    if decision not in RESOLUTION_DECISIONS:
        raise HTTPException(status_code=400, detail="decision must be accepted, rejected, or deferred")
    left_id, right_id = sorted([payload.left_entity_id.strip(), payload.right_entity_id.strip()])
    expected_id = _stable_id("resolution", case_id, left_id, right_id)
    if expected_id != candidate_id:
        raise HTTPException(status_code=400, detail="candidateId does not match the supplied entity pair")
    candidates = _load_resolution_candidates(case_id)
    candidate = next((row for row in candidates if row.get("candidateId") == candidate_id), None)
    if not candidate:
        raise HTTPException(status_code=404, detail="Resolution candidate not found")
    if decision == "accepted":
        signal_types = {
            str(signal.get("type") or "").casefold()
            for signal in (candidate.get("signals") or [])
        }
        independent_terms = ("identifier", "registration", "email", "phone", "address", "birth", "date", "tax", "lei")
        has_independent_signal = bool(candidate.get("sharedValues")) or any(
            any(term in signal_type for term in independent_terms)
            for signal_type in signal_types
        )
        if not has_independent_signal:
            return error_response(
                409,
                "NAME_ONLY_MATCH_REQUIRES_MORE_EVIDENCE",
                "Name similarity alone cannot confirm a person or entity identity.",
                request_id=str(getattr(request.state, "request_id", "")),
                details={"candidateId": candidate_id, "required": "independent identifier or corroborating attribute"},
            )

    left_canonical = str((candidate.get("left") or {}).get("id") or left_id)
    right_canonical = str((candidate.get("right") or {}).get("id") or right_id)
    canonical_id = _stable_id("canonical", *sorted([left_canonical, right_canonical]))
    driver = get_driver()
    review_query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
    MATCH (left:InvestigationEntity {entityId: $leftEntityId})
    MATCH (right:InvestigationEntity {entityId: $rightEntityId})
    WHERE EXISTS { MATCH (caseNode)-[:HAS_INVESTIGATION_ENTITY]->(left) }
      AND EXISTS { MATCH (caseNode)-[:HAS_INVESTIGATION_ENTITY]->(right) }
    MERGE (review:EntityResolutionReview {candidateId: $candidateId})
    ON CREATE SET review.createdAt = datetime()
    SET review.caseId = $caseId, review.pairKey = $pairKey,
        review.leftEntityId = $leftEntityId, review.rightEntityId = $rightEntityId,
        review.decision = $decision, review.rationale = $rationale,
        review.reviewedBy = $reviewedBy, review.reviewedAt = datetime(),
        review.updatedAt = datetime()
    MERGE (caseNode)-[:HAS_RESOLUTION_REVIEW]->(review)
    RETURN review.candidateId AS candidateId
    """
    canonical_query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_ENTITY]->(left:InvestigationEntity {entityId: $leftEntityId})
    MATCH (caseNode)-[:HAS_INVESTIGATION_ENTITY]->(right:InvestigationEntity {entityId: $rightEntityId})
    WITH caseNode, left, right,
         coalesce(left.canonicalEntityId, left.entityId) AS leftCanonical,
         coalesce(right.canonicalEntityId, right.entityId) AS rightCanonical
    MATCH (caseNode)-[:HAS_INVESTIGATION_ENTITY]->(member:InvestigationEntity)
    WHERE member.entityId IN [$leftEntityId, $rightEntityId]
       OR coalesce(member.canonicalEntityId, member.entityId) IN [leftCanonical, rightCanonical]
    SET member.canonicalEntityId = $canonicalEntityId,
        member.resolutionUpdatedAt = datetime()
    WITH collect(member.entityId) AS memberIds
    MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_STATEMENT]->(statement:InvestigationStatement)
    WHERE statement.subjectId IN memberIds
    SET statement.canonicalSubjectId = $canonicalEntityId,
        statement.updatedAt = datetime()
    RETURN size(memberIds) AS membersUpdated
    """
    params = {
        "caseId": case_id,
        "candidateId": candidate_id,
        "pairKey": f"{left_id}|{right_id}",
        "leftEntityId": left_id,
        "rightEntityId": right_id,
        "decision": decision,
        "rationale": payload.rationale.strip(),
        "reviewedBy": str(((getattr(request.state, "principal", None) or {}).get("principalId")) or payload.reviewed_by or "local-development").strip(),
        "canonicalEntityId": canonical_id,
    }
    with _db_session(driver) as session:
        records = _execute_write(session, review_query, params)
        if not records:
            raise HTTPException(status_code=404, detail="Entities are not attached to this case")
        members_updated = 0
        if decision == "accepted":
            canonical_rows = _execute_write(session, canonical_query, params)
            members_updated = int((canonical_rows[0].get("membersUpdated") if canonical_rows else 0) or 0)
    if decision == "accepted":
        _refresh_statement_contradictions(case_id)
    review_event_id = append_review_event(
        case_id,
        target_type="resolution",
        target_id=candidate_id,
        decision=decision,
        rationale=payload.rationale.strip(),
        reviewer_id=params["reviewedBy"],
        evidence_ids=list(candidate.get("evidenceIds") or []),
        metadata={"signals": candidate.get("signals") or [], "conflicts": candidate.get("conflicts") or [], "score": candidate.get("score")},
    )
    return {
        "candidateId": candidate_id,
        "decision": decision,
        "canonicalEntityId": canonical_id if decision == "accepted" else None,
        "membersUpdated": members_updated,
        "reviewedAt": datetime.now(timezone.utc).isoformat(),
        "reviewEventId": review_event_id,
        "message": "Identity decision recorded without deleting either source record.",
    }


def _path_statement_ids(case_id: str, relationship_ids: List[str]) -> Dict[str, List[str]]:
    if not relationship_ids:
        return {}
    driver = get_driver()
    query = """
    UNWIND $relationshipIds AS relationshipId
    OPTIONAL MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_STATEMENT]->(statement:InvestigationStatement {relationshipId: relationshipId})
    RETURN relationshipId, collect(DISTINCT statement.statementId) AS statementIds
    """
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            query,
            {"caseId": case_id, "relationshipIds": relationship_ids},
        )
    return {
        str(row.get("relationshipId")): _ordered_unique(row.get("statementIds") or [])
        for row in records
    }


def _enumerate_paths(
    graph: Dict[str, object],
    query_id: str,
    payload: InvestigationPathQueryRequest,
) -> Tuple[List[Dict[str, object]], List[str], bool]:
    nodes = graph.get("nodes") or []
    relationships = graph.get("relationships") or []
    node_by_id = {str(row.get("id")): row for row in nodes}
    root = next((row for row in nodes if row.get("isRoot")), None)
    start_id = payload.start_entity_id or (root.get("id") if root else None)
    if query_id == "shared-address" and not payload.start_entity_id:
        start_ids = [str(row.get("id")) for row in nodes if row.get("type") in {"Asset", "Organization"}]
    elif start_id:
        start_ids = [str(start_id)]
    else:
        raise HTTPException(status_code=409, detail="The case graph has no start entity")
    if any(entity_id not in node_by_id for entity_id in start_ids):
        raise HTTPException(status_code=400, detail="startEntityId is not attached to this case")
    if payload.target_entity_id and payload.target_entity_id not in node_by_id:
        raise HTTPException(status_code=400, detail="targetEntityId is not attached to this case")

    adjacency: Dict[str, List[Tuple[str, Dict[str, object]]]] = defaultdict(list)
    for relationship in relationships:
        if (
            relationship.get("verificationStatus") == "candidate-match"
            and not payload.include_candidate_matches
            and query_id != "sanctioned-ownership"
        ):
            continue
        source = str(relationship.get("source") or "")
        target = str(relationship.get("target") or "")
        adjacency[source].append((target, relationship))
        adjacency[target].append((source, relationship))

    money_terms = ("ownership", "business", "contract", "payment", "transaction", "position", "officer", "director")

    def matches(node_ids: List[str], path_relationships: List[Dict[str, object]]) -> bool:
        labels = [str(row.get("label") or "").casefold() for row in path_relationships]
        types = [str(node_by_id.get(node_id, {}).get("type") or "") for node_id in node_ids]
        if query_id == "shortest-evidence-path":
            return bool(payload.target_entity_id and node_ids[-1] == payload.target_entity_id)
        if query_id == "official-relative-contract":
            return bool(labels and labels[0].startswith("family:") and ("Contract" in types or any("contract" in label or "business interest" in label for label in labels[1:])))
        if query_id == "shared-address":
            return len(node_ids) >= 3 and "Address" in types and types[-1] in {"Asset", "Organization"} and node_ids[0] != node_ids[-1]
        if query_id == "sanctioned-ownership":
            return "Screening record" in types and any("ownership" in label or "business interest" in label for label in labels)
        if query_id == "follow-money":
            return len(path_relationships) >= 1 and all(any(term in label for term in money_terms) for label in labels)
        return False

    paths: List[Dict[str, object]] = []
    seen_paths: Set[Tuple[str, ...]] = set()
    max_candidates = payload.limit * 10
    for origin in start_ids:
        queue = deque([(origin, [origin], [])])
        while queue and len(paths) < payload.limit and len(seen_paths) < max_candidates:
            current, node_path, relationship_path = queue.popleft()
            if relationship_path and matches(node_path, relationship_path):
                relationship_ids = [str(row.get("id")) for row in relationship_path]
                signature = tuple(relationship_ids)
                if signature not in seen_paths:
                    seen_paths.add(signature)
                    paths.append(
                        {
                            "nodeIds": list(node_path),
                            "relationshipIds": relationship_ids,
                            "evidenceIds": _ordered_unique(
                                [
                                    evidence_id
                                    for row in relationship_path
                                    for evidence_id in (row.get("evidenceIds") or [])
                                ]
                            ),
                            "confidence": round(
                                min(float(row.get("confidence") or 0) for row in relationship_path),
                                3,
                            ),
                            "assertionKindCounts": {
                                "sourced": sum(1 for row in relationship_path if row.get("verificationStatus") in {"source-stated", "verified"}),
                                "analyst": sum(1 for row in relationship_path if row.get("verificationStatus") == "analyst-added"),
                                "hypothesis": sum(1 for row in relationship_path if row.get("verificationStatus") == "candidate-match"),
                                "inferred": 0,
                            },
                            "verificationStatus": (
                                "requires-review"
                                if any(row.get("verificationStatus") == "candidate-match" for row in relationship_path)
                                else "source-stated"
                            ),
                        }
                    )
                    if query_id == "shortest-evidence-path":
                        break
            if len(relationship_path) >= payload.max_depth:
                continue
            for neighbor, relationship in adjacency.get(current, []):
                if neighbor in node_path:
                    continue
                queue.append((neighbor, node_path + [neighbor], relationship_path + [relationship]))
        if len(paths) >= payload.limit:
            break

    relationship_ids = _ordered_unique(
        [relationship_id for path in paths for relationship_id in path["relationshipIds"]]
    )
    statements_by_relationship = _path_statement_ids(graph["caseId"], relationship_ids)
    for path in paths:
        path["statementIds"] = _ordered_unique(
            [
                statement_id
                for relationship_id in path["relationshipIds"]
                for statement_id in statements_by_relationship.get(relationship_id, [])
            ]
        )
        path["pathId"] = _stable_id("path", graph["caseId"], query_id, *path["relationshipIds"])
        path["length"] = len(path["relationshipIds"])
        path["summary"] = " → ".join(
            str(node_by_id.get(node_id, {}).get("label") or node_id) for node_id in path["nodeIds"]
        )
    warnings = []
    if query_id == "sanctioned-ownership":
        warnings.append("Screening candidates are included for lead generation; resolve identity before applying sanctions conclusions.")
    if any(path.get("verificationStatus") == "requires-review" for path in paths):
        warnings.append("At least one returned path contains an unresolved candidate match.")
    truncated = len(paths) >= payload.limit
    return paths, warnings, truncated


@router.get("/investigation-queries")
def list_investigation_path_queries():
    return PATH_QUERY_CATALOG


@router.post("/cases/{case_id}/investigation-queries/{query_id}/execute")
def execute_investigation_path_query(
    case_id: str, query_id: str, payload: InvestigationPathQueryRequest
):
    catalog_entry = next((row for row in PATH_QUERY_CATALOG if row["queryId"] == query_id), None)
    if not catalog_entry:
        raise HTTPException(status_code=404, detail="Investigation query not found")
    if query_id == "shortest-evidence-path" and not payload.target_entity_id:
        raise HTTPException(status_code=400, detail="targetEntityId is required for shortest-evidence-path")
    graph = _graph_snapshot(case_id)
    paths, warnings, truncated = _enumerate_paths(graph, query_id, payload)
    generated_at = datetime.now(timezone.utc).isoformat()
    run_id = _stable_id("path-run", case_id, query_id, generated_at)
    params_payload = payload.model_dump(by_alias=True)
    driver = get_driver()
    query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
    CREATE (run:InvestigationPathRun {
      runId: $runId, caseId: $caseId, queryId: $queryId,
      paramsJson: $paramsJson, pathsJson: $pathsJson, warnings: $warnings,
      truncated: $truncated, createdAt: datetime()
    })
    MERGE (caseNode)-[:HAS_PATH_RUN]->(run)
    RETURN run.runId AS runId
    """
    with _db_session(driver) as session:
        _execute_write(
            session,
            query,
            {
                "caseId": case_id,
                "runId": run_id,
                "queryId": query_id,
                "paramsJson": json.dumps(params_payload),
                "pathsJson": json.dumps(paths),
                "warnings": warnings,
                "truncated": truncated,
            },
        )
    return {
        "runId": run_id,
        "caseId": case_id,
        "queryId": query_id,
        "question": catalog_entry["question"],
        "params": params_payload,
        "generatedAt": generated_at,
        "paths": paths,
        "warnings": warnings,
        "truncated": truncated,
    }


def _validate_finding_references(
    case_id: str,
    *,
    statement_ids: List[str],
    path_run_ids: List[str],
    evidence_ids: List[str],
    node_ids: List[str],
    relationship_ids: List[str],
) -> None:
    driver = get_driver()
    checks = [
        (
            "statementIds",
            _ordered_unique(statement_ids),
            "MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_STATEMENT]->(item:InvestigationStatement) WHERE item.statementId IN $ids RETURN collect(item.statementId) AS found",
        ),
        (
            "pathRunIds",
            _ordered_unique(path_run_ids),
            "MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_PATH_RUN]->(item:InvestigationPathRun) WHERE item.runId IN $ids RETURN collect(item.runId) AS found",
        ),
        (
            "evidenceIds",
            _ordered_unique(evidence_ids),
            "MATCH (:DueDiligenceCase {caseId: $caseId})-[:USES_INVESTIGATION_EVIDENCE]->(item:InvestigationEvidence) WHERE item.evidenceId IN $ids RETURN collect(item.evidenceId) AS found",
        ),
        (
            "nodeIds",
            _ordered_unique(node_ids),
            "MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_ENTITY]->(item:InvestigationEntity) WHERE item.entityId IN $ids RETURN collect(item.entityId) AS found",
        ),
        (
            "relationshipIds",
            _ordered_unique(relationship_ids),
            "MATCH (:InvestigationEntity)-[item:INVESTIGATION_LINK {caseId: $caseId}]->(:InvestigationEntity) WHERE item.relationshipId IN $ids RETURN collect(item.relationshipId) AS found",
        ),
    ]
    with _db_session(driver) as session:
        for field_name, requested, query in checks:
            if not requested:
                continue
            rows = _execute_read(session, query, {"caseId": case_id, "ids": requested})
            found = set(rows[0].get("found") or []) if rows else set()
            missing = [item for item in requested if item not in found]
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"{field_name} contains IDs not attached to this case: {', '.join(missing[:10])}",
                )


def _finding_row(record) -> Dict[str, object]:
    return record.data() if hasattr(record, "data") else dict(record)


@router.get("/cases/{case_id}/findings")
def list_investigation_findings(
    case_id: str,
    status: Optional[str] = Query(default=None),
):
    _ensure_case(case_id)
    driver = get_driver()
    query = """
    MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_FINDING]->(finding:InvestigationFinding)
    WHERE ($status IS NULL OR finding.status = $status)
    RETURN finding.findingId AS findingId, finding.title AS title, finding.claim AS claim,
           finding.findingType AS findingType, finding.status AS status,
           finding.priority AS priority, finding.confidence AS confidence,
           coalesce(finding.supportingStatementIds, []) AS supportingStatementIds,
           coalesce(finding.contradictingStatementIds, []) AS contradictingStatementIds,
           coalesce(finding.pathRunIds, []) AS pathRunIds,
           coalesce(finding.evidenceIds, []) AS evidenceIds,
           coalesce(finding.nodeIds, []) AS nodeIds,
           coalesce(finding.relationshipIds, []) AS relationshipIds,
           coalesce(finding.analystRationale, '') AS analystRationale,
           coalesce(finding.recommendedNextSteps, []) AS recommendedNextSteps,
           coalesce(finding.createdBy, '') AS createdBy,
           coalesce(finding.reviewedBy, '') AS reviewedBy,
           toString(finding.createdAt) AS createdAt,
           toString(finding.updatedAt) AS updatedAt,
           toString(finding.reviewedAt) AS reviewedAt
    ORDER BY finding.priority, finding.updatedAt DESC
    """
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            query,
            {"caseId": case_id, "status": status.strip() if status and status.strip() else None},
        )
    findings = [_finding_row(row) for row in records]
    return {
        "caseId": case_id,
        "summary": {
            "total": len(findings),
            "open": sum(1 for row in findings if row.get("status") == "open"),
            "accepted": sum(1 for row in findings if row.get("status") == "accepted"),
            "rejected": sum(1 for row in findings if row.get("status") == "rejected"),
            "needsResearch": sum(1 for row in findings if row.get("status") == "needs-research"),
        },
        "findings": findings,
    }


@router.post("/cases/{case_id}/findings")
def create_investigation_finding(request: Request, case_id: str, payload: InvestigationFindingCreate):
    _ensure_case(case_id)
    status = payload.status.strip().casefold()
    if status not in FINDING_STATUSES:
        raise HTTPException(status_code=400, detail="status must be open, accepted, rejected, or needs-research")
    supporting_ids = _ordered_unique(payload.supporting_statement_ids)
    contradicting_ids = _ordered_unique(payload.contradicting_statement_ids)
    path_run_ids = _ordered_unique(payload.path_run_ids)
    evidence_ids = _ordered_unique(payload.evidence_ids)
    node_ids = _ordered_unique(payload.node_ids)
    relationship_ids = _ordered_unique(payload.relationship_ids)
    if not (supporting_ids or path_run_ids or evidence_ids):
        raise HTTPException(
            status_code=400,
            detail="A finding must reference at least one supporting statement, path run, or evidence record.",
        )
    if status == "accepted" and not payload.analyst_rationale.strip():
        raise HTTPException(status_code=400, detail="Accepted findings require analystRationale")
    _validate_finding_references(
        case_id,
        statement_ids=supporting_ids + contradicting_ids,
        path_run_ids=path_run_ids,
        evidence_ids=evidence_ids,
        node_ids=node_ids,
        relationship_ids=relationship_ids,
    )
    finding_id = _stable_id("finding", case_id, payload.title, datetime.now(timezone.utc).isoformat())
    driver = get_driver()
    query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
    CREATE (finding:InvestigationFinding {
      findingId: $findingId, caseId: $caseId, title: $title, claim: $claim,
      findingType: $findingType, status: $status, priority: $priority,
      confidence: $confidence, supportingStatementIds: $supportingStatementIds,
      contradictingStatementIds: $contradictingStatementIds, pathRunIds: $pathRunIds,
      evidenceIds: $evidenceIds, nodeIds: $nodeIds, relationshipIds: $relationshipIds,
      analystRationale: $analystRationale, recommendedNextSteps: $recommendedNextSteps,
      createdBy: $createdBy, createdAt: datetime(), updatedAt: datetime()
    })
    FOREACH (_ IN CASE WHEN $status = 'accepted' THEN [1] ELSE [] END | SET finding.reviewedAt = datetime())
    MERGE (caseNode)-[:HAS_INVESTIGATION_FINDING]->(finding)
    RETURN finding.findingId AS findingId
    """
    params = {
        "caseId": case_id,
        "findingId": finding_id,
        "title": payload.title.strip(),
        "claim": payload.claim.strip(),
        "findingType": payload.finding_type.strip() or "Investigative finding",
        "status": status,
        "priority": payload.priority,
        "confidence": payload.confidence,
        "supportingStatementIds": supporting_ids,
        "contradictingStatementIds": contradicting_ids,
        "pathRunIds": path_run_ids,
        "evidenceIds": evidence_ids,
        "nodeIds": node_ids,
        "relationshipIds": relationship_ids,
        "analystRationale": payload.analyst_rationale.strip(),
        "recommendedNextSteps": _ordered_unique(payload.recommended_next_steps),
        "createdBy": str(((getattr(request.state, "principal", None) or {}).get("principalId")) or payload.created_by or "local-development").strip(),
    }
    with _db_session(driver) as session:
        _execute_write(session, query, params)
    append_review_event(
        case_id,
        target_type="finding",
        target_id=finding_id,
        decision=status if status in {"accepted", "rejected", "needs-research"} else "deferred",
        rationale=payload.analyst_rationale.strip() or "Finding created for human review.",
        reviewer_id=params["createdBy"],
        evidence_ids=evidence_ids,
        metadata={"action": "created", "status": status},
    )
    return next(
        row
        for row in list_investigation_findings(case_id, status=None)["findings"]
        if row.get("findingId") == finding_id
    )


@router.patch("/cases/{case_id}/findings/{finding_id}")
def update_investigation_finding(
    request: Request, case_id: str, finding_id: str, payload: InvestigationFindingUpdate
):
    _ensure_case(case_id)
    current = next(
        (
            row
            for row in list_investigation_findings(case_id, status=None)["findings"]
            if row.get("findingId") == finding_id
        ),
        None,
    )
    if not current:
        raise HTTPException(status_code=404, detail="Finding not found")
    status = payload.status.strip().casefold() if payload.status is not None else current.get("status")
    if status not in FINDING_STATUSES:
        raise HTTPException(status_code=400, detail="status must be open, accepted, rejected, or needs-research")
    supporting_ids = _ordered_unique(payload.supporting_statement_ids if payload.supporting_statement_ids is not None else current.get("supportingStatementIds") or [])
    contradicting_ids = _ordered_unique(payload.contradicting_statement_ids if payload.contradicting_statement_ids is not None else current.get("contradictingStatementIds") or [])
    path_run_ids = _ordered_unique(payload.path_run_ids if payload.path_run_ids is not None else current.get("pathRunIds") or [])
    evidence_ids = _ordered_unique(payload.evidence_ids if payload.evidence_ids is not None else current.get("evidenceIds") or [])
    node_ids = _ordered_unique(payload.node_ids if payload.node_ids is not None else current.get("nodeIds") or [])
    relationship_ids = _ordered_unique(payload.relationship_ids if payload.relationship_ids is not None else current.get("relationshipIds") or [])
    rationale = payload.analyst_rationale if payload.analyst_rationale is not None else current.get("analystRationale") or ""
    if status == "accepted" and not str(rationale).strip():
        raise HTTPException(status_code=400, detail="Accepted findings require analystRationale")
    _validate_finding_references(
        case_id,
        statement_ids=supporting_ids + contradicting_ids,
        path_run_ids=path_run_ids,
        evidence_ids=evidence_ids,
        node_ids=node_ids,
        relationship_ids=relationship_ids,
    )
    driver = get_driver()
    query = """
    MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_FINDING]->(finding:InvestigationFinding {findingId: $findingId})
    SET finding.title = $title, finding.claim = $claim, finding.findingType = $findingType,
        finding.status = $status, finding.priority = $priority, finding.confidence = $confidence,
        finding.supportingStatementIds = $supportingStatementIds,
        finding.contradictingStatementIds = $contradictingStatementIds,
        finding.pathRunIds = $pathRunIds, finding.evidenceIds = $evidenceIds,
        finding.nodeIds = $nodeIds, finding.relationshipIds = $relationshipIds,
        finding.analystRationale = $analystRationale,
        finding.recommendedNextSteps = $recommendedNextSteps,
        finding.reviewedBy = $reviewedBy, finding.updatedAt = datetime()
    FOREACH (_ IN CASE WHEN $status IN ['accepted', 'rejected'] THEN [1] ELSE [] END | SET finding.reviewedAt = datetime())
    RETURN finding.findingId AS findingId
    """
    params = {
        "caseId": case_id,
        "findingId": finding_id,
        "title": (payload.title if payload.title is not None else current.get("title") or "").strip(),
        "claim": (payload.claim if payload.claim is not None else current.get("claim") or "").strip(),
        "findingType": (payload.finding_type if payload.finding_type is not None else current.get("findingType") or "Investigative finding").strip(),
        "status": status,
        "priority": payload.priority if payload.priority is not None else current.get("priority") or 2,
        "confidence": payload.confidence if payload.confidence is not None else current.get("confidence") or 0.7,
        "supportingStatementIds": supporting_ids,
        "contradictingStatementIds": contradicting_ids,
        "pathRunIds": path_run_ids,
        "evidenceIds": evidence_ids,
        "nodeIds": node_ids,
        "relationshipIds": relationship_ids,
        "analystRationale": str(rationale).strip(),
        "recommendedNextSteps": _ordered_unique(payload.recommended_next_steps if payload.recommended_next_steps is not None else current.get("recommendedNextSteps") or []),
        "reviewedBy": str(((getattr(request.state, "principal", None) or {}).get("principalId")) or (payload.reviewed_by if payload.reviewed_by is not None else current.get("reviewedBy")) or "local-development").strip(),
    }
    with _db_session(driver) as session:
        records = _execute_write(session, query, params)
    if not records:
        raise HTTPException(status_code=404, detail="Finding not found")
    append_review_event(
        case_id,
        target_type="finding",
        target_id=finding_id,
        decision=status if status in {"accepted", "rejected", "needs-research"} else "deferred",
        rationale=str(rationale).strip() or "Finding record updated.",
        reviewer_id=params["reviewedBy"],
        evidence_ids=evidence_ids,
        metadata={"action": "updated", "previousStatus": current.get("status"), "status": status},
    )
    return next(
        row
        for row in list_investigation_findings(case_id, status=None)["findings"]
        if row.get("findingId") == finding_id
    )


def _load_publication(case_id: str, publication_id: str) -> Dict[str, object]:
    driver = get_driver()
    query = """
    MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_PUBLICATION]->(publication:InvestigationPublication {publicationId: $publicationId})
    RETURN publication.publicationId AS publicationId,
           publication.caseId AS caseId, publication.title AS title,
           publication.executiveSummary AS executiveSummary,
           publication.preparedBy AS preparedBy, publication.status AS status,
           coalesce(publication.findingIds, []) AS findingIds,
           coalesce(publication.statementIds, []) AS statementIds,
           coalesce(publication.pathRunIds, []) AS pathRunIds,
           coalesce(publication.evidenceIds, []) AS evidenceIds,
           coalesce(publication.nodeIds, []) AS nodeIds,
           coalesce(publication.relationshipIds, []) AS relationshipIds,
           publication.findingsJson AS findingsJson,
           toString(publication.createdAt) AS createdAt
    """
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            query,
            {"caseId": case_id, "publicationId": publication_id},
        )
    if not records:
        raise HTTPException(status_code=404, detail="Publication not found")
    row = records[0].data()
    try:
        row["findings"] = json.loads(row.pop("findingsJson") or "[]")
    except (TypeError, ValueError):
        row["findings"] = []
    return row


@router.get("/cases/{case_id}/publications")
def list_investigation_publications(case_id: str):
    _ensure_case(case_id)
    driver = get_driver()
    query = """
    MATCH (:DueDiligenceCase {caseId: $caseId})-[:HAS_INVESTIGATION_PUBLICATION]->(publication:InvestigationPublication)
    RETURN publication.publicationId AS publicationId,
           publication.title AS title, publication.status AS status,
           publication.preparedBy AS preparedBy,
           size(coalesce(publication.findingIds, [])) AS findingCount,
           size(coalesce(publication.evidenceIds, [])) AS evidenceCount,
           toString(publication.createdAt) AS createdAt
    ORDER BY publication.createdAt DESC
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query, {"caseId": case_id})
    return [row.data() for row in records]


@router.get("/cases/{case_id}/publications/{publication_id}")
def get_investigation_publication(case_id: str, publication_id: str):
    _ensure_case(case_id)
    return _load_publication(case_id, publication_id)


@router.post("/cases/{case_id}/publications")
def create_investigation_publication(
    request: Request, case_id: str, payload: InvestigationPublicationCreate
):
    case_row = _ensure_case(case_id)
    governance_blockers = publication_governance_blockers(case_id)
    if governance_blockers:
        return error_response(
            409,
            "PUBLICATION_GOVERNANCE_BLOCKED",
            "Publication is blocked until governance requirements are satisfied.",
            request_id=str(getattr(request.state, "request_id", "")),
            details={"blockers": governance_blockers},
        )
    accepted = list_investigation_findings(case_id, status="accepted")["findings"]
    if not accepted:
        raise HTTPException(
            status_code=409,
            detail="Publication requires at least one accepted evidence-backed finding.",
        )
    finding_ids = _ordered_unique([row.get("findingId") for row in accepted])
    statement_ids = _ordered_unique(
        [
            statement_id
            for row in accepted
            for statement_id in (
                (row.get("supportingStatementIds") or [])
                + (row.get("contradictingStatementIds") or [])
            )
        ]
    )
    path_run_ids = _ordered_unique(
        [path_run_id for row in accepted for path_run_id in (row.get("pathRunIds") or [])]
    )
    evidence_ids = _ordered_unique(
        [evidence_id for row in accepted for evidence_id in (row.get("evidenceIds") or [])]
    )
    node_ids = _ordered_unique(
        [node_id for row in accepted for node_id in (row.get("nodeIds") or [])]
    )
    relationship_ids = _ordered_unique(
        [
            relationship_id
            for row in accepted
            for relationship_id in (row.get("relationshipIds") or [])
        ]
    )
    created_at = datetime.now(timezone.utc).isoformat()
    publication_id = _stable_id("publication", case_id, created_at)
    title = payload.title.strip() or f"Investigation findings: {case_row.get('subject') or 'case'}"
    driver = get_driver()
    query = """
    MATCH (caseNode:DueDiligenceCase {caseId: $caseId})
    CREATE (publication:InvestigationPublication {
      publicationId: $publicationId, caseId: $caseId,
      title: $title, executiveSummary: $executiveSummary,
      preparedBy: $preparedBy, status: 'published',
      findingIds: $findingIds, statementIds: $statementIds,
      pathRunIds: $pathRunIds, evidenceIds: $evidenceIds,
      nodeIds: $nodeIds, relationshipIds: $relationshipIds,
      findingsJson: $findingsJson, createdAt: datetime()
    })
    MERGE (caseNode)-[:HAS_INVESTIGATION_PUBLICATION]->(publication)
    RETURN publication.publicationId AS publicationId
    """
    params = {
        "caseId": case_id,
        "publicationId": publication_id,
        "title": title,
        "executiveSummary": str(payload.executive_summary or "").strip(),
        "preparedBy": str(payload.prepared_by or "").strip(),
        "findingIds": finding_ids,
        "statementIds": statement_ids,
        "pathRunIds": path_run_ids,
        "evidenceIds": evidence_ids,
        "nodeIds": node_ids,
        "relationshipIds": relationship_ids,
        "findingsJson": json.dumps(accepted),
    }
    with _db_session(driver) as session:
        _execute_write(session, query, params)
    return _load_publication(case_id, publication_id)
