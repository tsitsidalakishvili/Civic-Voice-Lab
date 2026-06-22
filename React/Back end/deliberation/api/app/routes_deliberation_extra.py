from fastapi import APIRouter

from .db import get_active_database, get_driver

router = APIRouter()


def _execute_read(session, query: str, params=None):
    if hasattr(session, "execute_read"):
        return session.execute_read(lambda tx: list(tx.run(query, params or {})))
    return session.read_transaction(lambda tx: list(tx.run(query, params or {})))


def _db_session(driver):
    return driver.session(database=get_active_database())


@router.get("/summary")
def deliberation_summary():
    driver = get_driver()
    query = """
    MATCH (c:Conversation)
    OPTIONAL MATCH (cm:Comment)
    OPTIONAL MATCH (p:Participant)
    RETURN
      count(DISTINCT c) AS conversations,
      count(DISTINCT cm) AS comments,
      count(DISTINCT p) AS participants
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query)
    row = records[0] if records else {}
    return {
        "conversations": int(row.get("conversations") or 0),
        "comments": int(row.get("comments") or 0),
        "participants": int(row.get("participants") or 0),
    }

