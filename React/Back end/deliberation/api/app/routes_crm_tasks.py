"""
CRM – task management endpoints (person tasks and bulk tasks).
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .db import get_driver
from .routes_crm_helpers import (
    TASK_STATUSES,
    _execute_read,
    _execute_write,
    _db_session,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class TaskOut(BaseModel):
    task_id: str = Field(alias="taskId")
    title: str
    description: Optional[str] = ""
    status: str
    due_date: Optional[str] = Field(alias="dueDate", default="")
    first_name: Optional[str] = Field(alias="firstName", default="")
    last_name: Optional[str] = Field(alias="lastName", default="")
    email: Optional[str] = None
    group: Optional[str] = None
    created_at: Optional[str] = Field(alias="createdAt", default=None)
    updated_at: Optional[str] = Field(alias="updatedAt", default=None)


class TaskCreate(BaseModel):
    email: str
    title: str
    description: Optional[str] = None
    status: Optional[str] = "Open"
    dueDate: Optional[str] = None


class TaskStatusUpdate(BaseModel):
    status: str


class TaskBulkCreate(BaseModel):
    rows: List[TaskCreate]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/tasks", response_model=List[TaskOut])
def list_tasks(
    status: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
    group: Optional[str] = Query(None),
    limit: int = Query(300, ge=10, le=1000),
):
    driver = get_driver()
    query = """
    MATCH (p:Person)-[:HAS_TASK]->(t:Task)
    OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(st:SupporterType)
    WITH p, t, collect(DISTINCT st.name) AS types
    WITH p, t,
      CASE WHEN any(x IN types WHERE toLower(x) CONTAINS 'member') THEN 'Member' ELSE 'Supporter' END AS group
    WHERE ($status IS NULL OR t.status = $status)
      AND ($email IS NULL OR p.email = $email)
      AND ($group IS NULL OR group = $group)
    RETURN
      t.taskId AS taskId,
      t.title AS title,
      coalesce(t.description, '') AS description,
      coalesce(t.status, 'Open') AS status,
      coalesce(t.dueDate, '') AS dueDate,
      coalesce(p.firstName, '') AS firstName,
      coalesce(p.lastName, '') AS lastName,
      p.email AS email,
      group AS group,
      toString(t.createdAt) AS createdAt,
      toString(t.updatedAt) AS updatedAt
    ORDER BY
      CASE WHEN t.status = 'Done' THEN 1 WHEN t.status = 'Cancelled' THEN 2 ELSE 0 END,
      coalesce(t.dueDate, '9999-12-31') ASC,
      t.createdAt DESC
    LIMIT $limit
    """
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            query,
            {"status": status, "email": email, "group": group, "limit": int(limit)},
        )
    return [record.data() for record in records]


@router.post("/tasks", response_model=TaskOut)
def create_task(payload: TaskCreate):
    status = payload.status if payload.status in TASK_STATUSES else "Open"
    driver = get_driver()
    query = """
    MATCH (p:Person {email: $email})
    CREATE (t:Task {
      taskId: randomUUID(),
      title: $title,
      description: $description,
      status: $status,
      dueDate: $dueDate,
      createdAt: datetime(),
      updatedAt: datetime()
    })
    MERGE (p)-[:HAS_TASK]->(t)
    RETURN
      t.taskId AS taskId,
      t.title AS title,
      coalesce(t.description, '') AS description,
      coalesce(t.status, 'Open') AS status,
      coalesce(t.dueDate, '') AS dueDate,
      coalesce(p.firstName, '') AS firstName,
      coalesce(p.lastName, '') AS lastName,
      p.email AS email,
      'Supporter' AS group,
      toString(t.createdAt) AS createdAt,
      toString(t.updatedAt) AS updatedAt
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "email": payload.email,
                "title": payload.title,
                "description": payload.description or "",
                "status": status,
                "dueDate": payload.dueDate or "",
            },
        )
    if not records:
        raise HTTPException(status_code=400, detail="Task could not be created")
    return records[0].data()


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task_status(task_id: str, payload: TaskStatusUpdate):
    if payload.status not in TASK_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    driver = get_driver()
    query = """
    MATCH (p:Person)-[:HAS_TASK]->(t:Task {taskId: $taskId})
    SET t.status = $status,
        t.updatedAt = datetime()
    RETURN
      t.taskId AS taskId,
      t.title AS title,
      coalesce(t.description, '') AS description,
      coalesce(t.status, 'Open') AS status,
      coalesce(t.dueDate, '') AS dueDate,
      coalesce(p.firstName, '') AS firstName,
      coalesce(p.lastName, '') AS lastName,
      p.email AS email,
      'Supporter' AS group,
      toString(t.createdAt) AS createdAt,
      toString(t.updatedAt) AS updatedAt
    """
    with _db_session(driver) as session:
        records = _execute_write(session, query, {"taskId": task_id, "status": payload.status})
    if not records:
        raise HTTPException(status_code=404, detail="Task not found")
    return records[0].data()


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            "MATCH (t:Task {taskId: $taskId}) DETACH DELETE t",
            {"taskId": task_id},
        )
    return {"deleted": True, "task_id": task_id}


@router.post("/tasks/bulk")
def bulk_create_tasks(payload: TaskBulkCreate):
    cleaned = []
    for row in payload.rows or []:
        email = (row.email or "").strip()
        title = (row.title or "").strip()
        if not email or not title:
            continue
        status = row.status if row.status in TASK_STATUSES else "Open"
        cleaned.append(
            {
                "email": email,
                "title": title,
                "description": row.description or "",
                "status": status,
                "dueDate": row.dueDate or "",
            }
        )
    if not cleaned:
        raise HTTPException(status_code=400, detail="No valid tasks provided")
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            UNWIND $rows AS row
            MATCH (p:Person {email: row.email})
            CREATE (t:Task {
              taskId: randomUUID(),
              title: row.title,
              description: row.description,
              status: row.status,
              dueDate: row.dueDate,
              createdAt: datetime(),
              updatedAt: datetime()
            })
            MERGE (p)-[:HAS_TASK]->(t)
            """,
            {"rows": cleaned},
        )
    return {"created": len(cleaned)}
