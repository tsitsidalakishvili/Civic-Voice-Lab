import csv
import io
import re
from typing import List, Optional
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from .db import get_active_database, get_driver
from .routes_crm_helpers import _build_import_rows, _normalize_supporter_type

router = APIRouter()
INTAKE_MODULE_IDS = {
    "crm",
    "campaigns",
    "deliberation",
    "due-diligence",
    "audience-discovery",
}

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


class ConnectorOut(BaseModel):
    connector_id: str = Field(alias="connectorId")
    name: str
    category: str
    status: str
    source_type: str = Field(alias="sourceType")
    target: str
    purpose: str
    powers: List[str] = []
    endpoints: List[str] = []


class ConnectorModuleOut(BaseModel):
    module_id: str = Field(alias="moduleId")
    module_label: str = Field(alias="moduleLabel")
    description: str
    status: str
    connectors: List[ConnectorOut]


class ConnectorCatalogSummaryOut(BaseModel):
    module_count: int = Field(alias="moduleCount")
    connector_count: int = Field(alias="connectorCount")
    active_connector_count: int = Field(alias="activeConnectorCount")
    planned_connector_count: int = Field(alias="plannedConnectorCount")


class ConnectorCatalogOut(BaseModel):
    summary: ConnectorCatalogSummaryOut
    modules: List[ConnectorModuleOut]


class CsvImportOut(BaseModel):
    import_id: str = Field(alias="importId")
    module_id: str = Field(alias="moduleId")
    module_label: str = Field(alias="moduleLabel")
    file_name: str = Field(alias="fileName")
    row_count: int = Field(alias="rowCount")
    column_count: int = Field(alias="columnCount")
    columns: List[str]
    created_nodes: int = Field(alias="createdNodes")
    target: str
    message: str


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


def _build_connector_catalog() -> ConnectorCatalogOut:
    modules = [
        ConnectorModuleOut(
            moduleId="crm",
            moduleLabel="Network / CRM",
            description="Connectors for people, events, outreach channels, and supporter operations.",
            status="active",
            connectors=[
                ConnectorOut(
                    connectorId="crm-people-csv",
                    name="People CSV import",
                    category="ingest",
                    status="active",
                    sourceType="file",
                    target="Neo4j Person graph",
                    purpose="Bulk import supporters and members from spreadsheets.",
                    powers=["read", "write", "bulk-import"],
                    endpoints=["/crm/people/import", "/crm/people/bulk"],
                ),
                ConnectorOut(
                    connectorId="crm-events-registration",
                    name="Event registration intake",
                    category="public intake",
                    status="active",
                    sourceType="public form",
                    target="Neo4j Event + Person graph",
                    purpose="Capture public event registrations directly into the CRM graph.",
                    powers=["read", "write"],
                    endpoints=["/crm/events/{event_id}/register", "/crm/events/with-people"],
                ),
                ConnectorOut(
                    connectorId="crm-geocoding",
                    name="Address geocoding",
                    category="enrichment",
                    status="active",
                    sourceType="google maps api",
                    target="Neo4j geo properties",
                    purpose="Enrich supporter and campaign addresses with coordinates for map coverage.",
                    powers=["read", "enrich"],
                    endpoints=[],
                ),
                ConnectorOut(
                    connectorId="crm-channel-webhooks",
                    name="Outreach channel webhooks",
                    category="delivery",
                    status="active",
                    sourceType="slack / whatsapp webhooks",
                    target="External channels",
                    purpose="Push updates and outreach messages from CRM workflows to external channels.",
                    powers=["deliver"],
                    endpoints=["/crm/slack/send", "/crm/whatsapp-groups/{group_id}/send"],
                ),
            ],
        ),
        ConnectorModuleOut(
            moduleId="campaigns",
            moduleLabel="Campaigns",
            description="Connectors that power campaign funding, transparency, and public campaign pages.",
            status="active",
            connectors=[
                ConnectorOut(
                    connectorId="campaigns-public-page",
                    name="Public campaign experience",
                    category="public intake",
                    status="active",
                    sourceType="public web page",
                    target="Campaign graph",
                    purpose="Serve public campaign detail, volunteer intake, and transparency data.",
                    powers=["read", "write"],
                    endpoints=[
                        "/crm/campaigns/{campaign_id}",
                        "/crm/campaigns/{campaign_id}/volunteers",
                    ],
                ),
                ConnectorOut(
                    connectorId="campaigns-payments",
                    name="Contribution and payment webhook",
                    category="payments",
                    status="active",
                    sourceType="payment processor / webhook",
                    target="Campaign contribution graph",
                    purpose="Track contribution checkouts and synchronize payment outcomes.",
                    powers=["write", "sync"],
                    endpoints=[
                        "/crm/campaigns/{campaign_id}/contributions/checkout",
                        "/crm/payments/webhook",
                    ],
                ),
                ConnectorOut(
                    connectorId="campaigns-proof",
                    name="Proof and transparency intake",
                    category="verification",
                    status="active",
                    sourceType="admin workflow",
                    target="Campaign proof + expense graph",
                    purpose="Collect proof artifacts, approvals, and audit data for campaign transparency.",
                    powers=["read", "write", "review"],
                    endpoints=[
                        "/crm/campaigns/{campaign_id}/proof",
                        "/crm/admin/proof-queue",
                        "/crm/admin/expense-queue",
                    ],
                ),
            ],
        ),
        ConnectorModuleOut(
            moduleId="deliberation",
            moduleLabel="Survey & Consensus",
            description="Connectors that power public surveys, votes, moderation, reporting, and exports.",
            status="active",
            connectors=[
                ConnectorOut(
                    connectorId="deliberation-public-survey",
                    name="Public survey intake",
                    category="public intake",
                    status="active",
                    sourceType="public web page",
                    target="Conversation, vote, and comment graph",
                    purpose="Capture participant views, votes, and comments from survey links.",
                    powers=["read", "write"],
                    endpoints=["/conversations/{conversation_id}/view", "/vote", "/conversations/{conversation_id}/comments"],
                ),
                ConnectorOut(
                    connectorId="deliberation-reports",
                    name="Public report sharing",
                    category="publishing",
                    status="active",
                    sourceType="shared report link",
                    target="Report graph",
                    purpose="Publish live deliberation results as shareable public dashboards.",
                    powers=["read", "publish"],
                    endpoints=["/reports/public/{share_id}"],
                ),
                ConnectorOut(
                    connectorId="deliberation-import-export",
                    name="Dataset import and exports",
                    category="data ops",
                    status="active",
                    sourceType="csv / zip",
                    target="Conversation datasets",
                    purpose="Seed conversations with imported datasets and export analytics snapshots.",
                    powers=["read", "write", "export"],
                    endpoints=[
                        "/conversations/{conversation_id}/dataset:bulk",
                        "/conversations/{conversation_id}/votes:bulk",
                    ],
                ),
            ],
        ),
        ConnectorModuleOut(
            moduleId="due-diligence",
            moduleLabel="Due Diligence",
            description="Connectors for external watchlists, public intelligence sources, and report generation.",
            status="pilot",
            connectors=[
                ConnectorOut(
                    connectorId="dd-watchlists",
                    name="Open-source screening feeds",
                    category="screening",
                    status="active",
                    sourceType="public sanctions / entity feeds",
                    target="Due diligence graph",
                    purpose="Screen people or entities against public risk and sanctions datasets.",
                    powers=["read", "enrich"],
                    endpoints=[],
                ),
                ConnectorOut(
                    connectorId="dd-report-pdf",
                    name="PDF report output",
                    category="publishing",
                    status="active",
                    sourceType="report generation",
                    target="PDF stream",
                    purpose="Render diligence findings into shareable PDF reports.",
                    powers=["export"],
                    endpoints=[],
                ),
            ],
        ),
        ConnectorModuleOut(
            moduleId="audience-discovery",
            moduleLabel="Audience Discovery",
            description="Connectors for crawlers, embeddings, LLMs, and graph writes used in audience discovery runs.",
            status="pilot",
            connectors=[
                ConnectorOut(
                    connectorId="audience-web-crawl",
                    name="Website crawl intake",
                    category="ingest",
                    status="active",
                    sourceType="web crawler",
                    target="Audience discovery pipeline",
                    purpose="Pull product and site content into discovery runs.",
                    powers=["read", "crawl"],
                    endpoints=[],
                ),
                ConnectorOut(
                    connectorId="audience-embeddings",
                    name="Embeddings provider",
                    category="ai enrichment",
                    status="active",
                    sourceType="embedding api",
                    target="Chunk vectors + cluster analysis",
                    purpose="Generate vector representations for clustering and evidence search.",
                    powers=["enrich", "cluster"],
                    endpoints=[],
                ),
                ConnectorOut(
                    connectorId="audience-llm",
                    name="Messaging and segment generation",
                    category="ai enrichment",
                    status="active",
                    sourceType="llm api",
                    target="Segment drafts + messaging outputs",
                    purpose="Generate segment summaries, evidence synthesis, and messaging ideas.",
                    powers=["generate"],
                    endpoints=[],
                ),
            ],
        ),
        ConnectorModuleOut(
            moduleId="data-hub",
            moduleLabel="Data Hub",
            description="Connectors and orchestration tools that stage, validate, and expose data across modules.",
            status="active",
            connectors=[
                ConnectorOut(
                    connectorId="datahub-neo4j-snapshot",
                    name="Neo4j graph snapshot",
                    category="core graph",
                    status="active",
                    sourceType="neo4j",
                    target="Explorer + diagnostics",
                    purpose="Inspect graph structure, labels, and relationships across the platform.",
                    powers=["read", "explore"],
                    endpoints=["/data-hub/graph"],
                ),
                ConnectorOut(
                    connectorId="datahub-module-connectors",
                    name="Connector registry",
                    category="orchestration",
                    status="active",
                    sourceType="backend catalog",
                    target="Data Hub workspace",
                    purpose="Expose the connector inventory needed by every module and page.",
                    powers=["read", "catalog"],
                    endpoints=["/data-hub/connectors"],
                ),
            ],
        ),
        ConnectorModuleOut(
            moduleId="admin",
            moduleLabel="Admin / Platform",
            description="Cross-platform connectors used for health monitoring, feedback, and operator workflows.",
            status="active",
            connectors=[
                ConnectorOut(
                    connectorId="admin-feedback-email",
                    name="Feedback inbox",
                    category="ops",
                    status="active",
                    sourceType="smtp",
                    target="Feedback entry graph + inbox",
                    purpose="Route user feedback into email and store a platform record in Neo4j.",
                    powers=["deliver", "write"],
                    endpoints=["/crm/feedback", "/crm/admin/feedback"],
                ),
                ConnectorOut(
                    connectorId="admin-health",
                    name="Platform health probes",
                    category="ops",
                    status="active",
                    sourceType="internal service checks",
                    target="Admin dashboards",
                    purpose="Expose backend, Neo4j, and connector readiness for operators.",
                    powers=["read", "monitor"],
                    endpoints=["/healthz", "/crm/admin/status", "/platform/auth/status"],
                ),
            ],
        ),
    ]

    connector_count = sum(len(module.connectors) for module in modules)
    active_connector_count = sum(
        1 for module in modules for connector in module.connectors if connector.status == "active"
    )
    planned_connector_count = sum(
        1 for module in modules for connector in module.connectors if connector.status != "active"
    )
    return ConnectorCatalogOut(
        summary=ConnectorCatalogSummaryOut(
            moduleCount=len(modules),
            connectorCount=connector_count,
            activeConnectorCount=active_connector_count,
            plannedConnectorCount=planned_connector_count,
        ),
        modules=modules,
    )


def _get_intake_module(module_id: str) -> ConnectorModuleOut:
    for module in _build_connector_catalog().modules:
        if module.module_id == module_id and module_id in INTAKE_MODULE_IDS:
            return module
    raise HTTPException(status_code=400, detail="Unsupported module for CSV intake.")


def _sanitize_column_name(value: str, index: int) -> str:
    text = re.sub(r"[^0-9a-zA-Z_]+", "_", (value or "").strip()).strip("_").lower()
    if not text:
        text = f"column_{index + 1}"
    if text[0].isdigit():
        text = f"field_{text}"
    return text[:80]


def _normalize_csv_rows(content: bytes) -> tuple[list[str], list[dict]]:
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Could not decode CSV file: {exc}")

    reader = csv.DictReader(io.StringIO(decoded))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file must include a header row.")

    column_map = {}
    columns: list[str] = []
    seen = set()
    for index, field_name in enumerate(reader.fieldnames):
        base_name = _sanitize_column_name(field_name or "", index)
        next_name = base_name
        suffix = 2
        while next_name in seen:
            next_name = f"{base_name}_{suffix}"
            suffix += 1
        seen.add(next_name)
        column_map[field_name] = next_name
        columns.append(next_name)

    rows: list[dict] = []
    for row_number, raw_row in enumerate(reader, start=1):
        properties = {}
        for original_name, safe_name in column_map.items():
            value = raw_row.get(original_name)
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            properties[safe_name] = text[:2000]
        if properties:
            rows.append({"rowNumber": row_number, "properties": properties})

    if not rows:
        raise HTTPException(status_code=400, detail="No valid rows found in CSV.")

    return columns, rows


@router.get("/connectors", response_model=ConnectorCatalogOut)
def get_connector_catalog():
    return _build_connector_catalog()


@router.post("/uploads/csv", response_model=CsvImportOut)
async def upload_module_csv(
    module_id: str = Form(..., alias="moduleId"),
    source_location: str = Form(default="", alias="sourceLocation"),
    owner: str = Form(default=""),
    notes: str = Form(default=""),
    file: UploadFile = File(...),
):
    module = _get_intake_module(module_id)
    if not file.filename:
        raise HTTPException(status_code=400, detail="CSV file name is required.")
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV uploads are supported right now.")

    content = await file.read()
    columns, rows = _normalize_csv_rows(content)
    import_id = str(uuid4())

    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            MERGE (module:PlatformModule {moduleId: $moduleId})
            ON CREATE SET module.createdAt = datetime()
            SET module.label = $moduleLabel,
                module.lastCsvImportAt = datetime(),
                module.updatedAt = datetime()
            CREATE (batch:CsvImport {
                importId: $importId,
                moduleId: $moduleId,
                moduleLabel: $moduleLabel,
                fileName: $fileName,
                rowCount: $rowCount,
                columnCount: $columnCount,
                columns: $columns,
                sourceLocation: $sourceLocation,
                owner: $owner,
                notes: $notes,
                importedAt: datetime()
            })
            MERGE (module)-[:HAS_IMPORT]->(batch)
            WITH module, batch
            UNWIND $rows AS row
            CREATE (record:CsvRow {
                recordId: randomUUID(),
                importId: $importId,
                moduleId: $moduleId,
                moduleLabel: $moduleLabel,
                fileName: $fileName,
                rowNumber: row.rowNumber,
                importedAt: datetime()
            })
            SET record += row.properties
            MERGE (batch)-[:IMPORTED_ROW]->(record)
            MERGE (module)-[:OWNS_ROW]->(record)
            """,
            {
                "importId": import_id,
                "moduleId": module.module_id,
                "moduleLabel": module.module_label,
                "fileName": file.filename,
                "rowCount": len(rows),
                "columnCount": len(columns),
                "columns": columns,
                "sourceLocation": source_location.strip()[:320],
                "owner": owner.strip()[:160],
                "notes": notes.strip()[:1000],
                "rows": rows,
            },
        )

    return CsvImportOut(
        importId=import_id,
        moduleId=module.module_id,
        moduleLabel=module.module_label,
        fileName=file.filename,
        rowCount=len(rows),
        columnCount=len(columns),
        columns=columns,
        createdNodes=len(rows),
        target="Neo4j",
        message=f"Imported {len(rows)} CSV rows into Neo4j for {module.module_label}.",
    )


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


class SupportersCsvImportOut(BaseModel):
    import_id: str = Field(alias="importId")
    file_name: str = Field(alias="fileName")
    row_count: int = Field(alias="rowCount")
    skipped: int
    default_type: str = Field(alias="defaultType")
    message: str


@router.post("/uploads/supporters-csv", response_model=SupportersCsvImportOut)
async def upload_supporters_csv(
    file: UploadFile = File(...),
    default_type: str = Form(default="Supporter", alias="defaultType"),
    owner: str = Form(default=""),
    notes: str = Form(default=""),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="CSV file name is required.")
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV uploads are supported.")

    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}")

    safe_type = _normalize_supporter_type(default_type, "Supporter")
    rows = _build_import_rows(df, safe_type)
    skipped = max(0, len(df) - len(rows))

    if not rows:
        raise HTTPException(
            status_code=400,
            detail="No valid rows found. CSV must have an email column (email, primary_email, e_mail, or email_address).",
        )

    import_id = str(uuid4())
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            UNWIND $rows AS row
            WITH row
            WHERE row.email IS NOT NULL AND trim(row.email) <> ""
            MERGE (p:Person {email: row.email})
            ON CREATE SET p.personId = randomUUID(), p.createdAt = datetime()
            SET p.firstName    = row.firstName,
                p.lastName     = row.lastName,
                p.gender       = row.gender,
                p.age          = row.age,
                p.phone        = row.phone,
                p.lat          = row.lat,
                p.lon          = row.lon,
                p.effortHours          = coalesce(row.effortHours, p.effortHours),
                p.eventsAttendedCount  = coalesce(row.eventsAttendedCount, p.eventsAttendedCount),
                p.referralCount        = coalesce(row.referralCount, p.referralCount),
                p.tasksCompleted       = coalesce(row.tasksCompleted, p.tasksCompleted),
                p.timeAvailability     = coalesce(row.timeAvailability, p.timeAvailability),
                p.importId     = $importId,
                p.importedAt   = datetime(),
                p.importOwner  = $owner,
                p.importNotes  = $notes
            WITH p, row
            FOREACH (_ IN CASE WHEN row.education IS NULL OR row.education = '' THEN [] ELSE [1] END |
                MERGE (ed:EducationLevel {name: row.education})
                MERGE (p)-[:HAS_EDUCATION]->(ed)
            )
            FOREACH (skill IN coalesce(row.skills, []) |
                MERGE (sk:Skill {name: skill})
                MERGE (p)-[:CAN_CONTRIBUTE_WITH]->(sk)
            )
            MERGE (st:SupporterType {name: coalesce(row.supporterType, 'Supporter')})
            MERGE (p)-[:CLASSIFIED_AS]->(st)
            WITH p, row
            FOREACH (_ IN CASE WHEN row.address IS NULL OR row.address = '' THEN [] ELSE [1] END |
                MERGE (a:Address {fullAddress: row.address})
                ON CREATE SET a.latitude = row.lat, a.longitude = row.lon
                ON MATCH  SET a.latitude = coalesce(row.lat, a.latitude),
                              a.longitude = coalesce(row.lon, a.longitude)
                MERGE (p)-[:LIVES_AT]->(a)
            )
            """,
            {"rows": rows, "importId": import_id, "owner": owner.strip()[:160], "notes": notes.strip()[:1000]},
        )

    return SupportersCsvImportOut(
        importId=import_id,
        fileName=file.filename,
        rowCount=len(rows),
        skipped=skipped,
        defaultType=safe_type,
        message=f"Imported {len(rows)} supporters into Neo4j as Person nodes.{f' {skipped} rows skipped (no email).' if skipped else ''}",
    )
