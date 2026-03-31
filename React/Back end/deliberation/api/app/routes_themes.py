"""
Theme CRUD, assignment to comments, and theme summary.
"""
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from .db import get_driver
from .routes_helpers import (
    _db_session,
    _execute_read,
    _execute_write,
    _get_conversation,
    _node_to_dict,
)
from .schemas import (
    ThemeAssignRequest,
    ThemeCreate,
    ThemeUpdate,
)

router = APIRouter()


def _collect_comments_and_votes(conversation_id: str):
    """Collect all comments and votes for a conversation (used by theme_summary)."""
    driver = get_driver()
    comments_query = """
    MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(cm:Comment)
    RETURN cm
    ORDER BY cm.createdAt
    """
    votes_query = """
    MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(cm:Comment)
    MATCH (p:Participant)-[v:VOTED]->(cm)
    RETURN p.id AS participant_id, cm.id AS comment_id, v.choice AS choice, v.important AS important, v.votedAt AS voted_at
    """
    with _db_session(driver) as session:
        comment_records = _execute_read(session, comments_query, {"cid": conversation_id})
        vote_records = _execute_read(session, votes_query, {"cid": conversation_id})
    comments = [_node_to_dict(record["cm"]) for record in comment_records]
    votes = [record.data() for record in vote_records]
    return comments, votes


@router.post("/conversations/{conversation_id}/themes")
def create_theme(conversation_id: str, payload: ThemeCreate):
    _get_conversation(conversation_id)
    theme_id = str(uuid4())
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            MATCH (c:Conversation {id: $cid})
            CREATE (t:Theme {
              id: $id,
              name: $name,
              description: $description,
              createdAt: datetime(),
              updatedAt: datetime()
            })
            CREATE (t)-[:FOR_CONVERSATION]->(c)
            """,
            {
                "cid": conversation_id,
                "id": theme_id,
                "name": payload.name,
                "description": payload.description,
            },
        )
    return {"id": theme_id, "name": payload.name, "description": payload.description}


@router.get("/conversations/{conversation_id}/themes")
def list_themes(conversation_id: str):
    _get_conversation(conversation_id)
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            """
            MATCH (t:Theme)-[:FOR_CONVERSATION]->(c:Conversation {id: $cid})
            OPTIONAL MATCH (cm:Comment)-[:IN_THEME]->(t)
            RETURN t, count(cm) AS comment_count
            ORDER BY t.createdAt DESC
            """,
            {"cid": conversation_id},
        )
    themes = []
    for record in records:
        theme = _node_to_dict(record["t"])
        themes.append(
            {
                "id": theme.get("id"),
                "name": theme.get("name"),
                "description": theme.get("description"),
                "comment_count": int(record.get("comment_count") or 0),
            }
        )
    return {"themes": themes}


@router.patch("/themes/{theme_id}")
def update_theme(theme_id: str, payload: ThemeUpdate):
    updates = {}
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.description is not None:
        updates["description"] = payload.description
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            """
            MATCH (t:Theme {id: $id})
            SET t += $updates,
                t.updatedAt = datetime()
            RETURN t
            """,
            {"id": theme_id, "updates": updates},
        )
    if not records:
        raise HTTPException(status_code=404, detail="Theme not found")
    theme = _node_to_dict(records[0]["t"])
    return {"id": theme.get("id"), "name": theme.get("name"), "description": theme.get("description")}


@router.delete("/themes/{theme_id}")
def delete_theme(theme_id: str):
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            """
            MATCH (t:Theme {id: $id})
            DETACH DELETE t
            RETURN $id AS deleted_id
            """,
            {"id": theme_id},
        )
    if not records:
        raise HTTPException(status_code=404, detail="Theme not found")
    return {"deleted": True, "theme_id": theme_id}


@router.post("/comments/{comment_id}/themes")
def assign_comment_themes(comment_id: str, payload: ThemeAssignRequest):
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            MATCH (cm:Comment {id: $id})
            OPTIONAL MATCH (cm)-[r:IN_THEME]->(:Theme)
            DELETE r
            WITH cm
            UNWIND $theme_ids AS tid
            MATCH (t:Theme {id: tid})
            MERGE (cm)-[:IN_THEME]->(t)
            """,
            {"id": comment_id, "theme_ids": payload.theme_ids},
        )
    return {"comment_id": comment_id, "theme_ids": payload.theme_ids}


@router.get("/conversations/{conversation_id}/themes/summary")
def theme_summary(conversation_id: str):
    _get_conversation(conversation_id)
    comments, votes = _collect_comments_and_votes(conversation_id)
    vote_counts = {}
    for vote in votes:
        cid = vote["comment_id"]
        vote_counts.setdefault(cid, {"agree": 0, "disagree": 0, "pass": 0, "important": 0})
        if vote["choice"] == 1:
            vote_counts[cid]["agree"] += 1
        elif vote["choice"] == -1:
            vote_counts[cid]["disagree"] += 1
        else:
            vote_counts[cid]["pass"] += 1
        if vote.get("important"):
            vote_counts[cid]["important"] += 1

    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            """
            MATCH (t:Theme)-[:FOR_CONVERSATION]->(c:Conversation {id: $cid})
            OPTIONAL MATCH (cm:Comment)-[:IN_THEME]->(t)
            RETURN t, collect(cm.id) AS comment_ids
            """,
            {"cid": conversation_id},
        )
    summaries = []
    comment_lookup = {comment["id"]: comment for comment in comments}
    for record in records:
        theme = _node_to_dict(record["t"])
        comment_ids = [cid for cid in record.get("comment_ids", []) if cid]
        comment_metrics = []
        for cid in comment_ids:
            counts = vote_counts.get(cid, {"agree": 0, "disagree": 0, "pass": 0, "important": 0})
            participation = counts["agree"] + counts["disagree"] + counts["pass"]
            ratio = (
                counts["agree"] / (counts["agree"] + counts["disagree"])
                if (counts["agree"] + counts["disagree"]) > 0
                else 0.0
            )
            comment_metrics.append(
                {
                    "id": cid,
                    "text": comment_lookup.get(cid, {}).get("text", ""),
                    "participation": participation,
                    "agreement_ratio": ratio,
                    "important_count": counts["important"],
                }
            )
        top_consensus = sorted(
            comment_metrics, key=lambda item: (-item["agreement_ratio"], -item["participation"])
        )[:3]
        top_important = sorted(
            comment_metrics, key=lambda item: (-item["important_count"], -item["participation"])
        )[:3]
        summaries.append(
            {
                "id": theme.get("id"),
                "name": theme.get("name"),
                "description": theme.get("description"),
                "comment_count": len(comment_ids),
                "top_consensus": top_consensus,
                "top_important": top_important,
            }
        )
    return {"themes": summaries}
