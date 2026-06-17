from crm.db.neo4j import run_query, run_write
from crm.utils.text import clean_text


TASK_STATUSES = ["Open", "In Progress", "Done", "Cancelled"]


def create_task(person_email, title, description=None, due_date=None, status="Open"):
    person_email = clean_text(person_email)
    title = clean_text(title)
    if not person_email or not title:
        return False
    due_date = clean_text(due_date)
    status = status if status in TASK_STATUSES else "Open"
    return run_write(
        """
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
        """,
        {
            "email": person_email,
            "title": title,
            "description": clean_text(description),
            "status": status,
            "dueDate": due_date,
        },
    )


def update_task_status(task_id, status):
    task_id = clean_text(task_id)
    status = status if status in TASK_STATUSES else None
    if not task_id or not status:
        return False
    return run_write(
        """
        MATCH (t:Task {taskId: $taskId})
        SET t.status = $status,
            t.updatedAt = datetime()
        """,
        {"taskId": task_id, "status": status},
    )


def delete_task(task_id):
    task_id = clean_text(task_id)
    if not task_id:
        return False
    exists = run_query(
        """
        MATCH (t:Task {taskId: $taskId})
        RETURN t.taskId AS taskId
        LIMIT 1
        """,
        {"taskId": task_id},
        silent=True,
    )
    if exists.empty:
        return False
    return run_write(
        """
        MATCH (t:Task {taskId: $taskId})
        DETACH DELETE t
        """,
        {"taskId": task_id},
    )


def list_tasks(status=None, person_email=None, group=None, limit=300):
    status = clean_text(status)
    person_email = clean_text(person_email)
    group = clean_text(group)
    group = group if group in {"Supporter", "Member"} else None
    try:
        limit = int(limit)
    except Exception:
        limit = 300
    limit = max(10, min(1000, limit))

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
    return run_query(
        query,
        {"status": status, "email": person_email, "group": group, "limit": limit},
        silent=True,
    )


def bulk_create_tasks(rows, default_status="Open"):
    cleaned = []
    for row in rows or []:
        email = clean_text(row.get("email"))
        title = clean_text(row.get("title"))
        if not email or not title:
            continue
        status = row.get("status") or default_status
        status = status if status in TASK_STATUSES else default_status
        cleaned.append(
            {
                "email": email,
                "title": title,
                "description": clean_text(row.get("description")),
                "status": status,
                "dueDate": clean_text(row.get("dueDate")),
            }
        )
    if not cleaned:
        return 0
    run_write(
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
    return len(cleaned)
