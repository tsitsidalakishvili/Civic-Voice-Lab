"""
Report creation, sharing, and public report retrieval.
Also contains the analyze_conversation endpoint which persists clustering results.
"""
import json
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from .db import get_driver
from .routes_analytics import _build_metrics, conversation_stats
from .routes_helpers import (
    _db_session,
    _execute_read,
    _execute_write,
    _get_conversation,
    _node_to_dict,
)
from .schemas import ReportCreate, ReportOut

router = APIRouter()


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _build_report_payload(conversation_id: str, payload: ReportCreate):
    metrics, points, _, cluster_summaries, cluster_similarity, potential_agreements = _build_metrics(
        conversation_id
    )
    stats = conversation_stats(conversation_id)

    comment_filter = None
    if payload.theme_ids and not payload.include_unassigned:
        driver = get_driver()
        with _db_session(driver) as session:
            records = _execute_read(
                session,
                """
                MATCH (t:Theme)
                WHERE t.id IN $theme_ids
                MATCH (cm:Comment)-[:IN_THEME]->(t)
                RETURN collect(DISTINCT cm.id) AS comment_ids
                """,
                {"theme_ids": payload.theme_ids},
            )
        comment_filter = set(records[0]["comment_ids"] if records else [])

    def _filter_metrics(items):
        if not comment_filter:
            return items
        return [item for item in items if item.id in comment_filter]

    return {
        "conversation_id": conversation_id,
        "name": payload.name,
        "theme_ids": payload.theme_ids,
        "include_unassigned": payload.include_unassigned,
        "generated_at": datetime.utcnow().isoformat(),
        "metrics": {
            "consensus": [item.dict() for item in _filter_metrics(metrics.consensus)],
            "polarizing": [item.dict() for item in _filter_metrics(metrics.polarizing)],
        },
        "clusters": cluster_summaries,
        "cluster_similarity": cluster_similarity,
        "potential_agreements": potential_agreements,
        "stats": stats,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/conversations/{conversation_id}/analyze", response_model=ReportOut)
def analyze_conversation(conversation_id: str):
    metrics, points, label_map, cluster_summaries, cluster_similarity, potential_agreements = _build_metrics(
        conversation_id
    )
    run_id = str(uuid4())
    clusters = sorted({point["cluster_id"] for point in points})

    cluster_sizes = {}
    for point in points:
        cluster_sizes[point["cluster_id"]] = cluster_sizes.get(point["cluster_id"], 0) + 1

    cluster_payload = [
        {"id": f"{run_id}-{cluster_id}", "label": cluster_id, "size": size}
        for cluster_id, size in cluster_sizes.items()
    ]
    assignments = [
        {"participant_id": point["participant_id"], "cluster_id": f"{run_id}-{point['cluster_id']}"}
        for point in points
    ]

    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            MATCH (c:Conversation {id: $cid})
            CREATE (ar:AnalysisRun {
                id: $rid,
                createdAt: datetime(),
                method: "pca+kmeans"
            })
            MERGE (ar)-[:FOR_CONVERSATION]->(c)
            """,
            {"cid": conversation_id, "rid": run_id},
        )
        _execute_write(
            session,
            """
            MATCH (c:Conversation {id: $cid})<-[:OF_CONVERSATION]-(cl:Cluster)
            DETACH DELETE cl
            """,
            {"cid": conversation_id},
        )
        if cluster_payload:
            _execute_write(
                session,
                """
                UNWIND $clusters AS cdata
                MATCH (c:Conversation {id: $cid})
                CREATE (cl:Cluster {id: cdata.id})
                SET cl.label = cdata.label,
                    cl.size = cdata.size,
                    cl.updatedAt = datetime(),
                    cl.runId = $rid
                MERGE (cl)-[:OF_CONVERSATION]->(c)
                """,
                {"cid": conversation_id, "clusters": cluster_payload, "rid": run_id},
            )
        if assignments:
            _execute_write(
                session,
                """
                UNWIND $assignments AS a
                MATCH (p:Participant {id: a.participant_id})
                MATCH (cl:Cluster {id: a.cluster_id})
                MERGE (p)-[:IN_CLUSTER {runId: $rid}]->(cl)
                """,
                {"assignments": assignments, "rid": run_id},
            )
        results_payload = [item.dict() for item in (metrics.consensus + metrics.polarizing)]
        _execute_write(
            session,
            """
            UNWIND $results AS r
            MATCH (cm:Comment {id: r.id})
            MATCH (ar:AnalysisRun {id: $rid})
            MERGE (ar)-[res:HAS_RESULT]->(cm)
            SET res.consensusScore = r.consensus_score,
                res.polarityScore = r.polarity_score,
                res.participation = r.participation,
                res.agreementRatio = r.agreement_ratio,
                res.agreeCount = r.agree_count,
                res.disagreeCount = r.disagree_count,
                res.passCount = r.pass_count,
                res.status = r.status
            """,
            {"rid": run_id, "results": results_payload},
        )

    return ReportOut(
        metrics=metrics,
        clusters=clusters,
        points=points,
        cluster_summaries=cluster_summaries,
        cluster_similarity=cluster_similarity,
        potential_agreements=potential_agreements,
    )


@router.post("/conversations/{conversation_id}/reports")
def create_report(conversation_id: str, payload: ReportCreate):
    _get_conversation(conversation_id)
    report_id = str(uuid4())
    share_id = uuid4().hex
    report_payload = _build_report_payload(conversation_id, payload)
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            MATCH (c:Conversation {id: $cid})
            CREATE (r:Report {
              id: $rid,
              shareId: $sid,
              name: $name,
              createdAt: datetime(),
              payload: $payload
            })
            CREATE (r)-[:FOR_CONVERSATION]->(c)
            """,
            {
                "cid": conversation_id,
                "rid": report_id,
                "sid": share_id,
                "name": payload.name,
                "payload": json.dumps(report_payload),
            },
        )
    return {"id": report_id, "share_id": share_id}


@router.get("/reports/{report_id}")
def get_report_by_id(report_id: str):
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            """
            MATCH (r:Report {id: $id})
            RETURN r
            """,
            {"id": report_id},
        )
    if not records:
        raise HTTPException(status_code=404, detail="Report not found")
    report = _node_to_dict(records[0]["r"])
    payload = report.get("payload")
    return {"id": report.get("id"), "share_id": report.get("shareId"), "payload": json.loads(payload)}


@router.get("/reports/public/{share_id}")
def get_public_report(share_id: str):
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            """
            MATCH (r:Report {shareId: $id})
            RETURN r
            """,
            {"id": share_id},
        )
    if not records:
        raise HTTPException(status_code=404, detail="Report not found")
    report = _node_to_dict(records[0]["r"])
    payload = report.get("payload")
    return {"id": report.get("id"), "share_id": report.get("shareId"), "payload": json.loads(payload)}
