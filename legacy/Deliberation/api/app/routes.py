import hashlib
import os
import random
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Query

from .analytics import compute_cluster_insights, compute_metrics, run_clustering
from .db import get_active_database, get_driver
from .schemas import (
    ConversationDatasetImportRequest,
    CommentCreate,
    CommentOut,
    CommentStatusUpdate,
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    MetricsOut,
    ReportOut,
    SeedCommentsRequest,
    SimulateVotesRequest,
    VotesImportRequest,
    VoteCreate,
)

router = APIRouter()

ANON_SALT = os.getenv("ANON_SALT", "dev-salt")


def _hash_participant(raw_id: str) -> str:
    digest = hashlib.sha256(f"{ANON_SALT}:{raw_id}".encode("utf-8")).hexdigest()
    return digest


def _node_to_dict(node):
    data = dict(node)
    for key, value in data.items():
        if hasattr(value, "to_native"):
            data[key] = value.to_native()
        elif hasattr(value, "isoformat"):
            data[key] = value.isoformat()
        else:
            data[key] = value
    return data


def _execute_read(session, query, params=None):
    if hasattr(session, "execute_read"):
        return session.execute_read(lambda tx: list(tx.run(query, params or {})))
    return session.read_transaction(lambda tx: list(tx.run(query, params or {})))


def _execute_write(session, query, params=None):
    def _run(tx):
        result = tx.run(query, params or {})
        return list(result)

    if hasattr(session, "execute_write"):
        return session.execute_write(_run)
    return session.write_transaction(_run)


def _db_session(driver):
    return driver.session(database=get_active_database())


def _get_conversation(conversation_id: str) -> dict:
    driver = get_driver()
    query = "MATCH (c:Conversation {id: $id}) RETURN c"
    with _db_session(driver) as session:
        records = _execute_read(session, query, {"id": conversation_id})
    if not records:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _node_to_dict(records[0]["c"])


def _conversation_out(convo: dict, comments=None, participants=None) -> dict:
    return {
        "id": convo["id"],
        "topic": convo["topic"],
        "description": convo.get("description"),
        "is_open": bool(convo.get("isOpen", True)),
        "allow_comment_submission": bool(convo.get("allowCommentSubmission", True)),
        "allow_viz": bool(convo.get("allowViz", True)),
        "moderation_required": bool(convo.get("moderationRequired", False)),
        "created_at": str(convo.get("createdAt")),
        "comments": comments,
        "participants": participants,
    }


def _normalize_vote_choice(value) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        as_int = int(value)
        if float(value) == float(as_int) and as_int in (-1, 0, 1):
            return as_int
        return None
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    mapping = {
        "agree": 1,
        "yes": 1,
        "1": 1,
        "disagree": -1,
        "no": -1,
        "-1": -1,
        "pass": 0,
        "skip": 0,
        "neutral": 0,
        "0": 0,
    }
    return mapping.get(normalized)


def _normalize_optional_bool(value) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        as_int = int(value)
        if float(value) == float(as_int):
            if as_int == 1:
                return True
            if as_int == 0:
                return False
        return None
    normalized = str(value or "").strip().lower()
    if normalized in {"true", "t", "yes", "y", "1"}:
        return True
    if normalized in {"false", "f", "no", "n", "0"}:
        return False
    return None


def _normalize_optional_timestamp(value) -> Optional[str]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw or raw.lower() in {"nan", "none", "null"}:
        return None
    candidate = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(candidate)
    except Exception:
        return None
    return parsed.isoformat()


@router.post("/conversations", response_model=ConversationOut)
def create_conversation(payload: ConversationCreate):
    convo_id = str(uuid4())
    driver = get_driver()
    query = """
    CREATE (c:Conversation {
        id: $id,
        topic: $topic,
        description: $description,
        isOpen: $is_open,
        allowCommentSubmission: $allow_comment_submission,
        allowViz: $allow_viz,
        moderationRequired: $moderation_required,
        createdAt: datetime()
    })
    RETURN c
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "id": convo_id,
                "topic": payload.topic,
                "description": payload.description,
                "is_open": payload.is_open,
                "allow_comment_submission": payload.allow_comment_submission,
                "allow_viz": payload.allow_viz,
                "moderation_required": payload.moderation_required,
            },
        )
        record = records[0] if records else None
        if record is None:
            raise HTTPException(status_code=500, detail="Conversation creation failed")
        convo = _node_to_dict(record["c"])
    return _conversation_out(convo)


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def update_conversation(conversation_id: str, payload: ConversationUpdate):
    updates = {}
    if payload.topic is not None:
        updates["topic"] = payload.topic
    if payload.description is not None:
        updates["description"] = payload.description
    if payload.is_open is not None:
        updates["isOpen"] = payload.is_open
    if payload.allow_comment_submission is not None:
        updates["allowCommentSubmission"] = payload.allow_comment_submission
    if payload.allow_viz is not None:
        updates["allowViz"] = payload.allow_viz
    if payload.moderation_required is not None:
        updates["moderationRequired"] = payload.moderation_required

    driver = get_driver()
    query = """
    MATCH (c:Conversation {id: $id})
    SET c += $updates
    RETURN c
    """
    with _db_session(driver) as session:
        records = _execute_write(session, query, {"id": conversation_id, "updates": updates})
        record = records[0] if records else None
    if record is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _conversation_out(_node_to_dict(record["c"]))


@router.get("/conversations", response_model=List[ConversationOut])
def list_conversations():
    driver = get_driver()
    query = "MATCH (c:Conversation) RETURN c ORDER BY c.createdAt DESC"
    with _db_session(driver) as session:
        records = _execute_read(session, query)
    conversations = []
    for record in records:
        convo = _node_to_dict(record["c"])
        conversations.append(_conversation_out(convo))
    return conversations


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def get_conversation(conversation_id: str):
    driver = get_driver()
    query = """
    MATCH (c:Conversation {id: $id})
    OPTIONAL MATCH (c)-[:HAS_COMMENT]->(cm:Comment)
    WITH c, count(cm) AS comments
    OPTIONAL MATCH (p:Participant)-[:PARTICIPATED_IN]->(c)
    RETURN c, comments, count(DISTINCT p) AS participants
    """
    with _db_session(driver) as session:
        record = _execute_read(session, query, {"id": conversation_id})
    if not record:
        raise HTTPException(status_code=404, detail="Conversation not found")
    row = record[0]
    convo = _node_to_dict(row["c"])
    return _conversation_out(convo, comments=row["comments"], participants=row["participants"])


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    _get_conversation(conversation_id)
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            MATCH (c:Conversation {id: $id})
            OPTIONAL MATCH (c)-[:HAS_COMMENT]->(cm:Comment)
            WITH c, collect(DISTINCT cm) AS comments
            FOREACH (comment IN comments | DETACH DELETE comment)
            WITH c
            OPTIONAL MATCH (ar:AnalysisRun)-[:FOR_CONVERSATION]->(c)
            WITH c, collect(DISTINCT ar) AS runs
            FOREACH (run IN runs | DETACH DELETE run)
            WITH c
            OPTIONAL MATCH (cl:Cluster)-[:OF_CONVERSATION]->(c)
            WITH c, collect(DISTINCT cl) AS clusters
            FOREACH (cluster IN clusters | DETACH DELETE cluster)
            WITH c
            DETACH DELETE c
            """,
            {"id": conversation_id},
        )
        _execute_write(
            session,
            """
            MATCH (p:Participant)
            WHERE NOT (p)-[:PARTICIPATED_IN]->(:Conversation)
              AND NOT (p)-[:VOTED]->(:Comment)
            DETACH DELETE p
            """,
        )
    return {"deleted": True, "conversation_id": conversation_id}


@router.post("/conversations/{conversation_id}/seed-comments:bulk")
def seed_comments(conversation_id: str, payload: SeedCommentsRequest):
    if not payload.comments:
        raise HTTPException(status_code=400, detail="No comments provided")
    convo = _get_conversation(conversation_id)
    if not bool(convo.get("isOpen", True)):
        raise HTTPException(status_code=400, detail="Conversation is closed")

    seed_items = [{"id": str(uuid4()), "text": text} for text in payload.comments if text.strip()]
    if not seed_items:
        raise HTTPException(status_code=400, detail="No valid comment text provided")

    driver = get_driver()
    query = """
    MATCH (c:Conversation {id: $cid})
    UNWIND $items AS item
    CREATE (cm:Comment {
        id: item.id,
        text: item.text,
        createdAt: datetime(),
        status: "approved",
        isSeed: true,
        authorHash: "seed"
    })
    CREATE (c)-[:HAS_COMMENT]->(cm)
    RETURN count(cm) AS created
    """
    with _db_session(driver) as session:
        records = _execute_write(session, query, {"cid": conversation_id, "items": seed_items})
        created = records[0]["created"] if records else 0
    return {"created": int(created)}


@router.post("/conversations/{conversation_id}/comments", response_model=CommentOut)
def create_comment(
    conversation_id: str,
    payload: CommentCreate,
    x_participant_id: Optional[str] = Header(None),
):
    convo = _get_conversation(conversation_id)
    if not bool(convo.get("isOpen", True)):
        raise HTTPException(status_code=400, detail="Conversation is closed")
    if not bool(convo.get("allowCommentSubmission", True)):
        raise HTTPException(status_code=400, detail="Comment submissions are disabled")

    raw_id = payload.author_id or x_participant_id or str(uuid4())
    author_hash = _hash_participant(raw_id)
    status = "pending" if bool(convo.get("moderationRequired", False)) else "approved"
    comment_id = str(uuid4())
    driver = get_driver()
    query = """
    MATCH (c:Conversation {id: $cid})
    CREATE (cm:Comment {
        id: $id,
        text: $text,
        createdAt: datetime(),
        status: $status,
        isSeed: false,
        authorHash: $authorHash
    })
    CREATE (c)-[:HAS_COMMENT]->(cm)
    RETURN cm
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {"cid": conversation_id, "id": comment_id, "text": payload.text, "status": status, "authorHash": author_hash},
        )
        record = records[0] if records else None
        if record is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        comment = _node_to_dict(record["cm"])
    return {
        "id": comment["id"],
        "text": comment["text"],
        "status": comment.get("status", status),
        "is_seed": bool(comment.get("isSeed", False)),
        "created_at": str(comment.get("createdAt")),
        "author_hash": comment.get("authorHash"),
        "agree_count": 0,
        "disagree_count": 0,
        "pass_count": 0,
    }


@router.get("/conversations/{conversation_id}/comments", response_model=List[CommentOut])
def list_comments(
    conversation_id: str,
    status: Optional[str] = Query(None, pattern="^(pending|approved|rejected)$"),
):
    driver = get_driver()
    query = """
    MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(cm:Comment)
    WHERE $status IS NULL OR cm.status = $status
    OPTIONAL MATCH (p:Participant)-[v:VOTED]->(cm)
    WITH cm,
        sum(CASE WHEN v.choice = 1 THEN 1 ELSE 0 END) AS agree_count,
        sum(CASE WHEN v.choice = -1 THEN 1 ELSE 0 END) AS disagree_count,
        sum(CASE WHEN v.choice = 0 THEN 1 ELSE 0 END) AS pass_count
    RETURN cm, agree_count, disagree_count, pass_count
    ORDER BY cm.createdAt
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query, {"cid": conversation_id, "status": status})
    comments = []
    for record in records:
        comment = _node_to_dict(record["cm"])
        comments.append(
            {
                "id": comment["id"],
                "text": comment["text"],
                "status": comment.get("status", "approved"),
                "is_seed": bool(comment.get("isSeed", False)),
                "created_at": str(comment.get("createdAt")),
                "author_hash": comment.get("authorHash"),
                "agree_count": int(record["agree_count"] or 0),
                "disagree_count": int(record["disagree_count"] or 0),
                "pass_count": int(record["pass_count"] or 0),
            }
        )
    return comments


@router.patch("/comments/{comment_id}", response_model=CommentOut)
def update_comment_status(comment_id: str, payload: CommentStatusUpdate):
    driver = get_driver()
    query = """
    MATCH (cm:Comment {id: $id})
    SET cm.status = $status
    RETURN cm
    """
    with _db_session(driver) as session:
        records = _execute_write(session, query, {"id": comment_id, "status": payload.status})
        record = records[0] if records else None
    if record is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    comment = _node_to_dict(record["cm"])
    return {
        "id": comment["id"],
        "text": comment["text"],
        "status": comment.get("status", payload.status),
        "is_seed": bool(comment.get("isSeed", False)),
        "created_at": str(comment.get("createdAt")),
        "author_hash": comment.get("authorHash"),
        "agree_count": 0,
        "disagree_count": 0,
        "pass_count": 0,
    }


@router.post("/vote")
def cast_vote(payload: VoteCreate, x_participant_id: Optional[str] = Header(None)):
    if payload.choice not in (-1, 0, 1):
        raise HTTPException(status_code=400, detail="Vote choice must be -1, 0, or 1")
    convo = _get_conversation(payload.conversation_id)
    if not bool(convo.get("isOpen", True)):
        raise HTTPException(status_code=400, detail="Conversation is closed")

    raw_id = payload.participant_id or x_participant_id or str(uuid4())
    participant_id = _hash_participant(raw_id)
    driver = get_driver()
    query = """
    MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(cm:Comment {id: $comment_id})
    WHERE cm.status = "approved"
    MERGE (p:Participant {id: $pid})
    ON CREATE SET p.createdAt = datetime()
    MERGE (p)-[:PARTICIPATED_IN]->(c)
    MERGE (p)-[v:VOTED]->(cm)
    SET v.choice = $choice,
        v.votedAt = datetime()
    RETURN v
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "cid": payload.conversation_id,
                "comment_id": payload.comment_id,
                "pid": participant_id,
                "choice": payload.choice,
            },
        )
        record = records[0] if records else None
    if record is None:
        raise HTTPException(status_code=404, detail="Conversation or comment not found")
    return {"participant_id": participant_id, "comment_id": payload.comment_id, "choice": payload.choice}


@router.post("/conversations/{conversation_id}/votes:bulk")
def import_votes_bulk(conversation_id: str, payload: VotesImportRequest):
    if not payload.votes:
        raise HTTPException(status_code=400, detail="No votes provided")

    _get_conversation(conversation_id)
    cleaned_votes = []
    invalid_rows = 0
    for item in payload.votes:
        participant_raw = str(item.participant_id or "").strip()
        comment_id = str(item.comment_id or "").strip()
        choice = _normalize_vote_choice(item.vote)
        if not participant_raw or not comment_id or choice is None:
            invalid_rows += 1
            continue
        cleaned_votes.append(
            {
                "participant_id": _hash_participant(participant_raw),
                "comment_id": comment_id,
                "choice": int(choice),
            }
        )

    if not cleaned_votes:
        raise HTTPException(
            status_code=400,
            detail="No valid votes found. Use participant_id, comment_id, and vote=agree|disagree|pass.",
        )

    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            """
            MATCH (c:Conversation {id: $cid})
            UNWIND $votes AS v
            MATCH (c)-[:HAS_COMMENT]->(cm:Comment {id: v.comment_id})
            WHERE cm.status = "approved"
            MERGE (p:Participant {id: v.participant_id})
            ON CREATE SET p.createdAt = datetime()
            MERGE (p)-[:PARTICIPATED_IN]->(c)
            MERGE (p)-[r:VOTED]->(cm)
            SET r.choice = v.choice,
                r.votedAt = datetime()
            WITH count(*) AS imported_rows, count(DISTINCT r) AS unique_votes
            RETURN imported_rows, unique_votes
            """,
            {"cid": conversation_id, "votes": cleaned_votes},
        )
    row = records[0] if records else None
    imported_rows = int(row["imported_rows"]) if row else 0
    unique_votes = int(row["unique_votes"]) if row else 0
    unmatched_rows = max(0, len(cleaned_votes) - imported_rows)
    skipped_rows = invalid_rows + unmatched_rows
    return {
        "received_rows": len(payload.votes),
        "valid_rows": len(cleaned_votes),
        "imported_rows": imported_rows,
        "unique_votes": unique_votes,
        "skipped_rows": skipped_rows,
    }


@router.post("/conversations/{conversation_id}/dataset:bulk")
def import_conversation_dataset(conversation_id: str, payload: ConversationDatasetImportRequest):
    if not payload.rows:
        raise HTTPException(status_code=400, detail="No rows provided")
    _get_conversation(conversation_id)

    comments_map = {}
    votes = []
    invalid_rows = 0
    conversation_mismatch_rows = 0

    for item in payload.rows:
        row_conversation_id = str(item.conversation_id or "").strip()
        if row_conversation_id and row_conversation_id != conversation_id:
            conversation_mismatch_rows += 1

        comment_id = str(item.comment_id or "").strip()
        if not comment_id:
            invalid_rows += 1
            continue
        comment_text = str(item.comment_text or "").strip() or None
        is_seed = _normalize_optional_bool(item.is_seed)
        comment_created_at = _normalize_optional_timestamp(item.comment_created_at)
        existing = comments_map.get(comment_id)
        if existing is None:
            comments_map[comment_id] = {
                "comment_id": comment_id,
                "comment_text": comment_text,
                "is_seed": bool(is_seed) if is_seed is not None else False,
                "comment_created_at": comment_created_at,
            }
        else:
            if comment_text and not existing.get("comment_text"):
                existing["comment_text"] = comment_text
            if is_seed is True:
                existing["is_seed"] = True
            if comment_created_at and not existing.get("comment_created_at"):
                existing["comment_created_at"] = comment_created_at

        choice = _normalize_vote_choice(item.vote)
        participant_raw = str(item.participant_id or "").strip()
        participant_cluster_raw = str(item.participant_cluster or "").strip()
        participant_cluster = (
            participant_cluster_raw
            if participant_cluster_raw and participant_cluster_raw.lower() not in {"nan", "none", "null"}
            else None
        )
        if choice is not None and participant_raw:
            votes.append(
                {
                    "participant_id": _hash_participant(participant_raw),
                    "comment_id": comment_id,
                    "choice": int(choice),
                    "reaction_created_at": _normalize_optional_timestamp(item.reaction_created_at),
                    "participant_cluster": participant_cluster,
                }
            )
        elif item.vote is not None or participant_raw:
            invalid_rows += 1

    comments = list(comments_map.values())
    driver = get_driver()
    created_comments = 0
    updated_comments = 0

    if comments:
        with _db_session(driver) as session:
            records = _execute_write(
                session,
                """
                MATCH (c:Conversation {id: $cid})
                UNWIND $comments AS row
                OPTIONAL MATCH (existing:Comment {id: row.comment_id})
                WITH c, row, existing IS NOT NULL AS existed
                MERGE (cm:Comment {id: row.comment_id})
                ON CREATE SET
                  cm.text = coalesce(row.comment_text, row.comment_id),
                  cm.createdAt = CASE
                    WHEN row.comment_created_at IS NULL THEN datetime()
                    ELSE datetime(row.comment_created_at)
                  END,
                  cm.status = "approved",
                  cm.isSeed = coalesce(row.is_seed, false),
                  cm.authorHash = CASE WHEN coalesce(row.is_seed, false) THEN "seed" ELSE "import" END
                ON MATCH SET
                  cm.text = coalesce(row.comment_text, cm.text),
                  cm.status = coalesce(cm.status, "approved"),
                  cm.isSeed = CASE
                    WHEN row.is_seed = true THEN true
                    ELSE coalesce(cm.isSeed, false)
                  END
                MERGE (c)-[:HAS_COMMENT]->(cm)
                RETURN
                  sum(CASE WHEN existed THEN 0 ELSE 1 END) AS created_comments,
                  sum(CASE WHEN existed THEN 1 ELSE 0 END) AS updated_comments
                """,
                {"cid": conversation_id, "comments": comments},
            )
            row = records[0] if records else None
            created_comments = int(row["created_comments"]) if row else 0
            updated_comments = int(row["updated_comments"]) if row else 0

    imported_rows = 0
    unique_votes = 0
    if votes:
        with _db_session(driver) as session:
            records = _execute_write(
                session,
                """
                MATCH (c:Conversation {id: $cid})
                UNWIND $votes AS v
                MATCH (c)-[:HAS_COMMENT]->(cm:Comment {id: v.comment_id})
                WHERE cm.status = "approved"
                MERGE (p:Participant {id: v.participant_id})
                ON CREATE SET p.createdAt = datetime()
                SET p.importedCluster = coalesce(v.participant_cluster, p.importedCluster)
                MERGE (p)-[:PARTICIPATED_IN]->(c)
                MERGE (p)-[r:VOTED]->(cm)
                SET r.choice = v.choice,
                    r.votedAt = CASE
                      WHEN v.reaction_created_at IS NULL THEN datetime()
                      ELSE datetime(v.reaction_created_at)
                    END
                WITH count(*) AS imported_rows, count(DISTINCT r) AS unique_votes
                RETURN imported_rows, unique_votes
                """,
                {"cid": conversation_id, "votes": votes},
            )
            row = records[0] if records else None
            imported_rows = int(row["imported_rows"]) if row else 0
            unique_votes = int(row["unique_votes"]) if row else 0

    unmatched_vote_rows = max(0, len(votes) - imported_rows)
    skipped_rows = invalid_rows + unmatched_vote_rows
    return {
        "received_rows": len(payload.rows),
        "comments_received": len(comments),
        "comments_created": created_comments,
        "comments_updated": updated_comments,
        "votes_valid": len(votes),
        "votes_imported": imported_rows,
        "unique_votes": unique_votes,
        "conversation_mismatch_rows": conversation_mismatch_rows,
        "skipped_rows": skipped_rows,
    }


@router.post("/conversations/{conversation_id}/simulate-votes")
def simulate_votes(conversation_id: str, payload: SimulateVotesRequest):
    _get_conversation(conversation_id)
    participants = max(1, min(int(payload.participants), 1000))
    requested_votes_per = max(1, min(int(payload.votes_per_participant), 200))
    rng = random.Random(payload.seed if payload.seed is not None else 42)

    driver = get_driver()
    with _db_session(driver) as session:
        comment_records = _execute_read(
            session,
            """
            MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(cm:Comment)
            WHERE cm.status = "approved"
            RETURN cm.id AS id
            ORDER BY cm.createdAt, cm.id
            """,
            {"cid": conversation_id},
        )

    comment_ids = [record["id"] for record in comment_records if record.get("id")]
    if not comment_ids:
        raise HTTPException(status_code=400, detail="No approved comments available")

    votes_per_participant = min(requested_votes_per, len(comment_ids))
    votes = []
    for _ in range(participants):
        participant_id = str(uuid4())
        selected_comments = (
            rng.sample(comment_ids, votes_per_participant)
            if votes_per_participant < len(comment_ids)
            else list(comment_ids)
        )
        for comment_id in selected_comments:
            roll = rng.random()
            if roll < 0.44:
                choice = 1
            elif roll < 0.88:
                choice = -1
            else:
                choice = 0
            votes.append(
                {
                    "participant_id": participant_id,
                    "comment_id": comment_id,
                    "choice": choice,
                }
            )

    with _db_session(driver) as session:
        records = _execute_write(
            session,
            """
            MATCH (c:Conversation {id: $cid})
            UNWIND $votes AS v
            MATCH (c)-[:HAS_COMMENT]->(cm:Comment {id: v.comment_id})
            WHERE cm.status = "approved"
            MERGE (p:Participant {id: v.participant_id})
            ON CREATE SET p.createdAt = datetime()
            MERGE (p)-[:PARTICIPATED_IN]->(c)
            MERGE (p)-[r:VOTED]->(cm)
            SET r.choice = v.choice,
                r.votedAt = datetime()
            RETURN count(r) AS total
            """,
            {"cid": conversation_id, "votes": votes},
        )
    generated_votes = int(records[0]["total"]) if records else 0
    return {
        "participants": participants,
        "votes_per_participant": votes_per_participant,
        "generated_votes": generated_votes,
    }


def _collect_comments_and_votes(conversation_id: str):
    driver = get_driver()
    comments_query = """
    MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(cm:Comment)
    RETURN cm
    ORDER BY cm.createdAt
    """
    votes_query = """
    MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(cm:Comment)
    MATCH (p:Participant)-[v:VOTED]->(cm)
    RETURN p.id AS participant_id, cm.id AS comment_id, v.choice AS choice
    """
    with _db_session(driver) as session:
        comment_records = _execute_read(session, comments_query, {"cid": conversation_id})
        vote_records = _execute_read(session, votes_query, {"cid": conversation_id})
    comments = [_node_to_dict(record["cm"]) for record in comment_records]
    votes = [record.data() for record in vote_records]
    return comments, votes


def _build_metrics(conversation_id: str) -> MetricsOut:
    comments, votes = _collect_comments_and_votes(conversation_id)
    points, label_map = run_clustering(votes)
    consensus, polarizing = compute_metrics(comments, votes, label_map)
    cluster_summaries, cluster_similarity = compute_cluster_insights(
        comments, votes, label_map
    )
    potential_agreements = [item["text"] for item in consensus][:10]
    total_votes = len(votes)
    participants = len({vote["participant_id"] for vote in votes})
    return (
        MetricsOut(
            total_comments=len(comments),
            total_participants=participants,
            total_votes=total_votes,
            consensus=consensus,
            polarizing=polarizing,
        ),
        points,
        label_map,
        cluster_summaries,
        cluster_similarity,
        potential_agreements,
    )


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


@router.get("/conversations/{conversation_id}/report", response_model=ReportOut)
def get_report(conversation_id: str):
    metrics, points, _, cluster_summaries, cluster_similarity, potential_agreements = _build_metrics(
        conversation_id
    )
    clusters = sorted({point["cluster_id"] for point in points})
    return ReportOut(
        metrics=metrics,
        clusters=clusters,
        points=points,
        cluster_summaries=cluster_summaries,
        cluster_similarity=cluster_similarity,
        potential_agreements=potential_agreements,
    )
