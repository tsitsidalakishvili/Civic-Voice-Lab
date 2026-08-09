from __future__ import annotations

import json
import os
from collections import Counter
from copy import deepcopy
from typing import Any, Dict, Iterable, List

from .dd_workflow_v2 import MUTATION_CONTRACT_VERSION, initial_projection
from .db import get_active_database, get_driver


MIGRATION_WRITE_FLAG = "FS_DD_WORKFLOW_V2_MIGRATION_WRITE_ENABLED"
MIGRATION_CONFIRMATION = "APPLY_BE1_PROJECTIONS"
ROLLBACK_CONFIRMATION = "ROLLBACK_BE1_PROJECTIONS"
TRUTHY = {"1", "true", "yes", "on"}

CONSTRAINTS = (
    "CREATE CONSTRAINT dd_workflow_event_id IF NOT EXISTS FOR (n:DDWorkflowEvent) REQUIRE n.eventId IS UNIQUE",
    "CREATE CONSTRAINT dd_workflow_idempotency_key IF NOT EXISTS FOR (n:DDWorkflowIdempotency) REQUIRE n.operationKey IS UNIQUE",
)


def plan_projection_migration(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    projections: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    skipped = 0
    stage_counts: Counter[str] = Counter()
    for raw in rows:
        row = deepcopy(raw)
        case_id = str(row.get("caseId") or "").strip()
        if not case_id:
            errors.append({"code": "CASE_ID_MISSING"})
            continue
        if str(row.get("ddWorkflowSchemaVersion") or "") == MUTATION_CONTRACT_VERSION and row.get("projectionJson"):
            skipped += 1
            continue
        try:
            projection = initial_projection(row)
            stage_counts[projection["stage"]] += 1
            projections.append(
                {
                    "caseId": case_id,
                    "expectedWorkflowVersion": int(row.get("ddWorkflowVersion") or 1),
                    "projection": projection,
                }
            )
        except Exception as exc:
            errors.append({"caseId": case_id, "code": "PROJECTION_FAILED", "errorType": type(exc).__name__})
    return {
        "migrationVersion": MUTATION_CONTRACT_VERSION,
        "dryRun": True,
        "plannedCount": len(projections),
        "skippedCount": skipped,
        "errorCount": len(errors),
        "migrationNeedsReviewCount": len(projections),
        "stageCounts": dict(sorted(stage_counts.items())),
        "errors": errors,
        "projections": projections,
    }


def safe_migration_report(plan: Dict[str, Any]) -> Dict[str, Any]:
    return {key: deepcopy(value) for key, value in plan.items() if key != "projections"}


def apply_projection_plan_to_memory(rows: Iterable[Dict[str, Any]], plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pure synthetic verifier used by tests; it does not represent a DB write."""
    by_id = {str(item.get("caseId") or ""): deepcopy(item) for item in rows}
    for item in plan.get("projections") or []:
        row = by_id[item["caseId"]]
        if str(row.get("ddWorkflowSchemaVersion") or "") == MUTATION_CONTRACT_VERSION:
            continue
        row["ddWorkflowVersion"] = item["projection"]["workflowVersion"]
        row["ddWorkflowSchemaVersion"] = MUTATION_CONTRACT_VERSION
        row["projectionJson"] = json.dumps(item["projection"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return list(by_id.values())


def rollback_projection_plan_in_memory(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rolled_back = []
    for source in rows:
        row = deepcopy(source)
        if str(row.get("ddWorkflowSchemaVersion") or "") == MUTATION_CONTRACT_VERSION:
            row.pop("ddWorkflowVersion", None)
            row.pop("ddWorkflowSchemaVersion", None)
            row.pop("projectionJson", None)
        rolled_back.append(row)
    return rolled_back


def read_legacy_case_rows() -> List[Dict[str, Any]]:
    query = """
    MATCH (c:DueDiligenceCase)
    RETURN c.caseId AS caseId, c.subject AS subject,
           c.subjectGeorgian AS subjectGeorgian,
           c.subjectEnglish AS subjectEnglish,
           c.subjectType AS subjectType, c.status AS status,
           c.owner AS owner, toString(c.createdAt) AS createdAt,
           toString(c.updatedAt) AS updatedAt,
           c.ddWorkflowProjectionJson AS projectionJson,
           c.ddWorkflowVersion AS ddWorkflowVersion,
           c.ddWorkflowSchemaVersion AS ddWorkflowSchemaVersion
    ORDER BY c.caseId
    """
    with get_driver().session(database=get_active_database()) as session:
        records = session.run(query)
        return [record.data() for record in records]


def _writes_enabled(confirmation: str, expected: str) -> bool:
    enabled = str(os.getenv(MIGRATION_WRITE_FLAG, "")).strip().casefold() in TRUTHY
    return enabled and confirmation == expected


def apply_projection_plan_to_database(plan: Dict[str, Any], *, confirmation: str) -> Dict[str, Any]:
    if not _writes_enabled(confirmation, MIGRATION_CONFIRMATION):
        raise RuntimeError(
            f"Migration writes are disabled. Set {MIGRATION_WRITE_FLAG}=1 and provide the exact confirmation token."
        )
    driver = get_driver()
    applied = 0
    skipped = 0
    with driver.session(database=get_active_database()) as session:
        for constraint in CONSTRAINTS:
            session.run(constraint).consume()
        for item in plan.get("projections") or []:
            result = session.run(
                """
                MATCH (c:DueDiligenceCase {caseId: $caseId})
                WHERE c.ddWorkflowSchemaVersion IS NULL
                SET c.ddWorkflowVersion = $workflowVersion,
                    c.ddWorkflowSchemaVersion = $schemaVersion,
                    c.ddWorkflowProjectionJson = $projectionJson,
                    c.ddWorkflowMigratedAt = datetime()
                RETURN c.caseId AS caseId
                """,
                {
                    "caseId": item["caseId"],
                    "workflowVersion": item["projection"]["workflowVersion"],
                    "schemaVersion": MUTATION_CONTRACT_VERSION,
                    "projectionJson": json.dumps(item["projection"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                },
            ).single()
            if result:
                applied += 1
            else:
                skipped += 1
    return {"migrationVersion": MUTATION_CONTRACT_VERSION, "appliedCount": applied, "skippedCount": skipped}


def rollback_database_projections(*, confirmation: str) -> Dict[str, Any]:
    if not _writes_enabled(confirmation, ROLLBACK_CONFIRMATION):
        raise RuntimeError(
            f"Migration rollback is disabled. Set {MIGRATION_WRITE_FLAG}=1 and provide the exact confirmation token."
        )
    query = """
    MATCH (c:DueDiligenceCase {ddWorkflowSchemaVersion: $schemaVersion})
    OPTIONAL MATCH (c)-[eventRel:HAS_DD_WORKFLOW_EVENT]->(event:DDWorkflowEvent)
    WITH c, collect(eventRel) AS eventRels, collect(event) AS events
    FOREACH (rel IN eventRels | DELETE rel)
    FOREACH (event IN events | DELETE event)
    WITH c
    OPTIONAL MATCH (idem:DDWorkflowIdempotency {caseId: c.caseId})
    WITH c, collect(idem) AS idempotencyNodes
    FOREACH (idem IN idempotencyNodes | DELETE idem)
    REMOVE c.ddWorkflowVersion, c.ddWorkflowSchemaVersion,
           c.ddWorkflowProjectionJson, c.ddWorkflowMigratedAt
    RETURN count(c) AS rolledBack
    """
    with get_driver().session(database=get_active_database()) as session:
        row = session.run(query, {"schemaVersion": MUTATION_CONTRACT_VERSION}).single()
    return {"migrationVersion": MUTATION_CONTRACT_VERSION, "rolledBackCount": int(row["rolledBack"] if row else 0)}
