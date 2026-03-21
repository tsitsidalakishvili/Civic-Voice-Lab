from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from .db import get_active_database, get_driver

router = APIRouter()

SKIP_PROPERTY_KEYS = {
    "raw_html",
    "cleaned_text",
    "embedding",
    "text",
    "html",
    "content",
    "vector",
    "binary",
}


class GraphCountOut(BaseModel):
    label: str
    count: int


class GraphSummaryOut(BaseModel):
    node_count: int = Field(alias="nodeCount")
    relationship_count: int = Field(alias="relationshipCount")
    label_counts: List[GraphCountOut] = Field(alias="labelCounts")
    relationship_counts: List[GraphCountOut] = Field(alias="relationshipCounts")


class GraphNodeOut(BaseModel):
    id: str
    labels: List[str] = []
    properties: dict = {}
    display: str = ""


class GraphEdgeOut(BaseModel):
    id: str
    source: str
    target: str
    type: str
    properties: dict = {}


class GraphSnapshotOut(BaseModel):
    summary: GraphSummaryOut
    nodes: List[GraphNodeOut]
    edges: List[GraphEdgeOut]


def _execute_read(session, query: str, params: Optional[dict] = None):
    if hasattr(session, "execute_read"):
        return session.execute_read(lambda tx: list(tx.run(query, params or {})))
    return session.read_transaction(lambda tx: list(tx.run(query, params or {})))


def _db_session(driver):
    return driver.session(database=get_active_database())


def _truncate_text(value: str, limit: int = 180) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _serialize_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        items = [_serialize_value(item) for item in value[:16]]
        if len(value) > 16:
            items.append("...")
        return items
    if isinstance(value, dict):
        return {key: _serialize_value(item) for key, item in value.items()}
    return str(value)


def _sanitize_properties(properties: dict) -> dict:
    safe = {}
    for key, value in (properties or {}).items():
        if key in SKIP_PROPERTY_KEYS:
            continue
        serialized = _serialize_value(value)
        if isinstance(serialized, str):
            serialized = _truncate_text(serialized)
        safe[key] = serialized
    return safe


def _pick_display(labels: List[str], properties: dict) -> str:
    candidates = [
        "name",
        "title",
        "label",
        "email",
        "id",
        "page_id",
        "pageId",
        "run_id",
        "runId",
        "campaignId",
        "comment_id",
        "commentId",
    ]
    for key in candidates:
        value = properties.get(key)
        if value:
            return _truncate_text(str(value), limit=64)
    if labels:
        return labels[0]
    return "Node"


def _load_graph_summary(session) -> GraphSummaryOut:
    node_rows = _execute_read(session, "MATCH (n) RETURN count(n) AS count")
    rel_rows = _execute_read(session, "MATCH ()-[r]-() RETURN count(r) AS count")
    node_count = int((node_rows[0].get("count") if node_rows else 0) or 0)
    relationship_count = int((rel_rows[0].get("count") if rel_rows else 0) or 0)
    label_rows = _execute_read(
        session,
        """
        MATCH (n)
        UNWIND labels(n) AS label
        RETURN label, count(*) AS count
        ORDER BY count DESC, label ASC
        """,
    )
    relationship_rows = _execute_read(
        session,
        """
        MATCH ()-[r]-()
        RETURN type(r) AS label, count(*) AS count
        ORDER BY count DESC, label ASC
        """,
    )
    label_counts = [
        GraphCountOut(label=row.get("label") or "Unknown", count=int(row.get("count") or 0))
        for row in label_rows
        if row.get("label")
    ]
    relationship_counts = [
        GraphCountOut(label=row.get("label") or "Unknown", count=int(row.get("count") or 0))
        for row in relationship_rows
        if row.get("label")
    ]
    return GraphSummaryOut(
        nodeCount=node_count,
        relationshipCount=relationship_count,
        labelCounts=label_counts,
        relationshipCounts=relationship_counts,
    )


def _load_graph_snapshot(session, limit: int, label: str) -> tuple[list, list]:
    records = _execute_read(
        session,
        """
        MATCH (n)-[r]-(m)
        WHERE $label = "" OR $label IN labels(n) OR $label IN labels(m)
        RETURN
          id(n) AS sourceId,
          labels(n) AS sourceLabels,
          properties(n) AS sourceProps,
          id(m) AS targetId,
          labels(m) AS targetLabels,
          properties(m) AS targetProps,
          id(r) AS relId,
          type(r) AS relType,
          properties(r) AS relProps
        LIMIT $limit
        """,
        {"limit": limit, "label": label or ""},
    )

    nodes = {}
    edges = []
    for row in records:
        source_id = str(row.get("sourceId"))
        target_id = str(row.get("targetId"))
        if source_id not in nodes:
            source_props = _sanitize_properties(row.get("sourceProps") or {})
            source_labels = list(row.get("sourceLabels") or [])
            nodes[source_id] = GraphNodeOut(
                id=source_id,
                labels=source_labels,
                properties=source_props,
                display=_pick_display(source_labels, source_props),
            )
        if target_id not in nodes:
            target_props = _sanitize_properties(row.get("targetProps") or {})
            target_labels = list(row.get("targetLabels") or [])
            nodes[target_id] = GraphNodeOut(
                id=target_id,
                labels=target_labels,
                properties=target_props,
                display=_pick_display(target_labels, target_props),
            )
        edges.append(
            GraphEdgeOut(
                id=str(row.get("relId") or f"{source_id}-{target_id}-{len(edges)}"),
                source=source_id,
                target=target_id,
                type=str(row.get("relType") or ""),
                properties=_sanitize_properties(row.get("relProps") or {}),
            )
        )

    if edges:
        return list(nodes.values()), edges

    node_rows = _execute_read(
        session,
        """
        MATCH (n)
        WHERE $label = "" OR $label IN labels(n)
        RETURN id(n) AS nodeId, labels(n) AS labels, properties(n) AS props
        LIMIT $limit
        """,
        {"limit": limit, "label": label or ""},
    )
    nodes = [
        GraphNodeOut(
            id=str(row.get("nodeId")),
            labels=list(row.get("labels") or []),
            properties=_sanitize_properties(row.get("props") or {}),
            display=_pick_display(list(row.get("labels") or []), row.get("props") or {}),
        )
        for row in node_rows
    ]
    return nodes, []


@router.get("/graph", response_model=GraphSnapshotOut)
def get_graph_snapshot(
    limit: int = Query(80, ge=10, le=300),
    label: Optional[str] = Query(default="", max_length=80),
):
    driver = get_driver()
    with _db_session(driver) as session:
        summary = _load_graph_summary(session)
        nodes, edges = _load_graph_snapshot(session, limit=limit, label=label or "")
    return GraphSnapshotOut(summary=summary, nodes=nodes, edges=edges)
