import csv
import json
import hashlib
import io
import os
import random
import zipfile
import re
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from .analytics import compute_cluster_insights, compute_metrics, run_clustering
from .db import get_active_database, get_driver
from .schemas import (
    ConversationDatasetImportRequest,
    QueueRequest,
    ThemeCreate,
    ThemeUpdate,
    ThemeAssignRequest,
    ReportCreate,
    IngestRequest,
    InviteWaveCreate,
    CommentCreate,
    CommentUpdate,
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
PROFANITY_WORDS = {
    word.strip().lower()
    for word in os.getenv(
        "PROFANITY_WORDS",
        "fuck,shit,bitch,asshole,cunt,slut,whore,damn",
    ).split(",")
    if word.strip()
}


def _parse_int(value, default):
    try:
        return int(value)
    except Exception:
        return default


MIN_SURVEY_PARTICIPANTS = max(0, _parse_int(os.getenv("SURVEY_MIN_PARTICIPANTS"), 100))
EXPORT_DIR = os.getenv(
    "SURVEY_EXPORT_DIR",
    os.path.join(os.path.dirname(__file__), "..", "exports"),
)
os.makedirs(EXPORT_DIR, exist_ok=True)


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
        "allow_voting": bool(convo.get("allowVoting", True)),
        "moderation_profile": convo.get("moderationProfile") or (
            "strict" if bool(convo.get("moderationRequired", False)) else "lazy"
        ),
        "min_votes_for_inclusion": int(convo.get("minVotesForInclusion") or 3),
        "profanity_filter_enabled": bool(convo.get("profanityFilterEnabled", False)),
        "rate_limit_per_minute": int(convo.get("rateLimitPerMinute") or 0),
        "identity_mode": convo.get("identityMode") or "anonymous",
        "invite_only": bool(convo.get("inviteOnly", False)),
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


def _contains_profanity(text: str) -> bool:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text or "")
    tokens = {token for token in cleaned.split() if token}
    return bool(tokens.intersection(PROFANITY_WORDS))


def _enforce_rate_limit(convo: dict, participant_hash: str, action: str):
    limit = int(convo.get("rateLimitPerMinute") or 0)
    if limit <= 0:
        return
    driver = get_driver()
    if action == "comment":
        query = """
        MATCH (cm:Comment)
        WHERE cm.authorHash = $author_hash
          AND cm.createdAt >= datetime() - duration("PT1M")
        RETURN count(cm) AS total
        """
        params = {"author_hash": participant_hash}
    else:
        query = """
        MATCH (p:Participant {id: $pid})-[v:VOTED]->(:Comment)
        WHERE v.votedAt >= datetime() - duration("PT1M")
        RETURN count(v) AS total
        """
        params = {"pid": participant_hash}
    with _db_session(driver) as session:
        records = _execute_read(session, query, params)
    total = int(records[0]["total"] or 0) if records else 0
    if total >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {limit} {action}s per minute.",
        )


def _generate_invite_code() -> str:
    return uuid4().hex[:8].upper()


def _validate_invite(conversation_id: str, invite_code: Optional[str], participant_hash: str):
    if not invite_code:
        raise HTTPException(status_code=403, detail="Invite code required")
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            """
            MATCH (inv:Invite {code: $code})-[:FOR_CONVERSATION]->(c:Conversation {id: $cid})
            OPTIONAL MATCH (inv)-[:CHILD_OF*0..]->(parent:Invite)
            WITH inv, collect(parent) AS parents
            RETURN inv, any(p IN parents WHERE coalesce(p.revoked, false)) AS revoked_chain
            """,
            {"code": invite_code, "cid": conversation_id},
        )
        if not records:
            raise HTTPException(status_code=403, detail="Invalid invite code")
        inv = _node_to_dict(records[0]["inv"])
        revoked_chain = bool(records[0].get("revoked_chain"))
        if inv.get("revoked") or revoked_chain:
            raise HTTPException(status_code=403, detail="Invite code has been revoked")
        _execute_write(
            session,
            """
            MATCH (inv:Invite {code: $code})
            MERGE (p:Participant {id: $pid})
            ON CREATE SET p.createdAt = datetime()
            MERGE (inv)-[:USED_BY {usedAt: datetime()}]->(p)
            """,
            {"code": invite_code, "pid": participant_hash},
        )


@router.post("/conversations", response_model=ConversationOut)
def create_conversation(payload: ConversationCreate):
    convo_id = str(uuid4())
    moderation_profile = payload.moderation_profile or "lazy"
    moderation_required = payload.moderation_required or moderation_profile == "strict"
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
        allowVoting: $allow_voting,
        moderationProfile: $moderation_profile,
        minVotesForInclusion: $min_votes_for_inclusion,
        profanityFilterEnabled: $profanity_filter_enabled,
        rateLimitPerMinute: $rate_limit_per_minute,
        identityMode: $identity_mode,
        inviteOnly: $invite_only,
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
        "moderation_required": moderation_required,
                "allow_voting": payload.allow_voting,
        "moderation_profile": moderation_profile,
                "min_votes_for_inclusion": payload.min_votes_for_inclusion,
                "profanity_filter_enabled": payload.profanity_filter_enabled,
                "rate_limit_per_minute": payload.rate_limit_per_minute,
                "identity_mode": payload.identity_mode,
                "invite_only": payload.invite_only,
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
    if payload.allow_voting is not None:
        updates["allowVoting"] = payload.allow_voting
    if payload.moderation_profile is not None:
        updates["moderationProfile"] = payload.moderation_profile
        updates["moderationRequired"] = payload.moderation_profile == "strict"
    if payload.min_votes_for_inclusion is not None:
        updates["minVotesForInclusion"] = payload.min_votes_for_inclusion
    if payload.profanity_filter_enabled is not None:
        updates["profanityFilterEnabled"] = payload.profanity_filter_enabled
    if payload.rate_limit_per_minute is not None:
        updates["rateLimitPerMinute"] = payload.rate_limit_per_minute
    if payload.identity_mode is not None:
        updates["identityMode"] = payload.identity_mode
    if payload.invite_only is not None:
        updates["inviteOnly"] = payload.invite_only

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
    x_invite_code: Optional[str] = Header(None),
):
    convo = _get_conversation(conversation_id)
    if not bool(convo.get("isOpen", True)):
        raise HTTPException(status_code=400, detail="Conversation is closed")
    if not bool(convo.get("allowCommentSubmission", True)):
        raise HTTPException(status_code=400, detail="Comment submissions are disabled")
    identity_mode = convo.get("identityMode") or "anonymous"
    if identity_mode == "xid_required" and not (payload.author_id or x_participant_id):
        raise HTTPException(status_code=400, detail="Identity is required to comment")

    raw_id = payload.author_id or x_participant_id or str(uuid4())
    author_hash = _hash_participant(raw_id)
    if bool(convo.get("inviteOnly", False)):
        _validate_invite(conversation_id, x_invite_code, author_hash)
    moderation_profile = convo.get("moderationProfile") or (
        "strict" if bool(convo.get("moderationRequired", False)) else "lazy"
    )
    status = "pending" if moderation_profile == "strict" else "approved"
    flagged_profanity = False
    if bool(convo.get("profanityFilterEnabled", False)) and _contains_profanity(payload.text):
        flagged_profanity = True
        status = "pending"
    _enforce_rate_limit(convo, author_hash, "comment")
    comment_id = str(uuid4())
    driver = get_driver()
    query = """
    MATCH (c:Conversation {id: $cid})
    CREATE (cm:Comment {
        id: $id,
        text: $text,
        createdAt: datetime(),
        updatedAt: datetime(),
        status: $status,
        isSeed: false,
        authorHash: $authorHash,
        flaggedProfanity: $flaggedProfanity
    })
    CREATE (c)-[:HAS_COMMENT]->(cm)
    RETURN cm
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "cid": conversation_id,
                "id": comment_id,
                "text": payload.text,
                "status": status,
                "authorHash": author_hash,
                "flaggedProfanity": flagged_profanity,
            },
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
        "updated_at": str(comment.get("updatedAt")) if comment.get("updatedAt") else None,
        "author_hash": comment.get("authorHash"),
        "agree_count": 0,
        "disagree_count": 0,
        "pass_count": 0,
        "important_count": 0,
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
        sum(CASE WHEN v.choice = 0 THEN 1 ELSE 0 END) AS pass_count,
        sum(CASE WHEN coalesce(v.important, false) THEN 1 ELSE 0 END) AS important_count
    RETURN cm, agree_count, disagree_count, pass_count, important_count
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
                "updated_at": str(comment.get("updatedAt")) if comment.get("updatedAt") else None,
                "author_hash": comment.get("authorHash"),
                "agree_count": int(record["agree_count"] or 0),
                "disagree_count": int(record["disagree_count"] or 0),
                "pass_count": int(record["pass_count"] or 0),
                "important_count": int(record.get("important_count") or 0),
            }
        )
    return comments


@router.post("/conversations/{conversation_id}/queue")
def get_comment_queue(
    conversation_id: str,
    payload: QueueRequest,
    x_participant_id: Optional[str] = Header(None),
):
    convo = _get_conversation(conversation_id)
    if not bool(convo.get("isOpen", True)):
        raise HTTPException(status_code=400, detail="Conversation is closed")
    seen_set = {str(item) for item in (payload.seen_ids or [])}
    voted_set = {str(item) for item in (payload.voted_ids or [])}
    excluded = seen_set.union(voted_set)

    driver = get_driver()
    query = """
    MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(cm:Comment)
    WHERE cm.status = "approved"
    OPTIONAL MATCH (p:Participant)-[v:VOTED]->(cm)
    WITH cm,
        sum(CASE WHEN v.choice = 1 THEN 1 ELSE 0 END) AS agree_count,
        sum(CASE WHEN v.choice = -1 THEN 1 ELSE 0 END) AS disagree_count,
        sum(CASE WHEN v.choice = 0 THEN 1 ELSE 0 END) AS pass_count
    RETURN cm, agree_count, disagree_count, pass_count
    ORDER BY cm.createdAt
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query, {"cid": conversation_id})

    items = []
    for record in records:
        comment = _node_to_dict(record["cm"])
        comment_id = str(comment.get("id"))
        if comment_id in excluded:
            continue
        agree = int(record["agree_count"] or 0)
        disagree = int(record["disagree_count"] or 0)
        passed = int(record["pass_count"] or 0)
        participation = agree + disagree + passed
        denom = agree + disagree
        balance = 1.0 - abs((agree / denom) - 0.5) * 2.0 if denom else 0.0
        low_vote = 1.0 / (1.0 + participation)
        created_at = comment.get("createdAt")
        recency = 0.0
        if created_at:
            try:
                age_days = max(
                    0.0,
                    (datetime.utcnow() - datetime.fromisoformat(str(created_at))).days,
                )
                recency = 1.0 / (1.0 + age_days)
            except Exception:
                recency = 0.0
        score = low_vote * 0.6 + balance * 0.3 + recency * 0.1
        items.append(
            {
                "id": comment_id,
                "text": comment.get("text", ""),
                "status": comment.get("status", "approved"),
                "is_seed": bool(comment.get("isSeed", False)),
                "created_at": str(comment.get("createdAt")),
                "author_hash": comment.get("authorHash"),
                "agree_count": agree,
                "disagree_count": disagree,
                "pass_count": passed,
                "score": score,
            }
        )

    items = sorted(items, key=lambda item: item["score"], reverse=True)
    limit = int(payload.limit or 20)
    return {"items": items[:limit], "total": len(items)}


@router.patch("/comments/{comment_id}", response_model=CommentOut)
def update_comment_status(comment_id: str, payload: CommentStatusUpdate):
    driver = get_driver()
    query = """
    MATCH (cm:Comment {id: $id})
    SET cm.status = $status,
        cm.rejectionReason = $rejection_reason,
        cm.updatedAt = datetime()
    RETURN cm
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "id": comment_id,
                "status": payload.status,
                "rejection_reason": payload.rejection_reason,
            },
        )
        record = records[0] if records else None
        if record is not None:
            _execute_write(
                session,
                """
                MATCH (cm:Comment {id: $id})<-[:HAS_COMMENT]-(c:Conversation)
                CREATE (log:ModerationLog {
                    id: $log_id,
                    action: $action,
                    status: $status,
                    reason: $reason,
                    createdAt: datetime()
                })
                CREATE (log)-[:FOR_CONVERSATION]->(c)
                CREATE (log)-[:FOR_COMMENT]->(cm)
                """,
                {
                    "id": comment_id,
                    "log_id": str(uuid4()),
                    "action": "copy_to_seed" if payload.copy_to_seed else "status_change",
                    "status": payload.status,
                    "reason": payload.rejection_reason,
                },
            )
        if payload.copy_to_seed:
            _execute_write(
                session,
                """
                MATCH (cm:Comment {id: $id})
                MATCH (c:Conversation)-[:HAS_COMMENT]->(cm)
                CREATE (seed:Comment {
                    id: $seed_id,
                    text: cm.text,
                    createdAt: datetime(),
                    updatedAt: datetime(),
                    status: "approved",
                    isSeed: true,
                    authorHash: "seed",
                    copiedFrom: cm.id
                })
                CREATE (c)-[:HAS_COMMENT]->(seed)
                SET cm.copiedToSeed = true
                """,
                {"id": comment_id, "seed_id": str(uuid4())},
            )
    if record is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    comment = _node_to_dict(record["cm"])
    return {
        "id": comment["id"],
        "text": comment["text"],
        "status": comment.get("status", payload.status),
        "is_seed": bool(comment.get("isSeed", False)),
        "created_at": str(comment.get("createdAt")),
        "updated_at": str(comment.get("updatedAt")) if comment.get("updatedAt") else None,
        "author_hash": comment.get("authorHash"),
        "agree_count": 0,
        "disagree_count": 0,
        "pass_count": 0,
        "important_count": 0,
    }


@router.patch("/comments/{comment_id}/edit", response_model=CommentOut)
def update_comment(comment_id: str, payload: CommentUpdate):
    updates = {}
    if payload.text is not None:
        updates["text"] = payload.text
    if payload.is_seed is not None:
        updates["isSeed"] = payload.is_seed
        if payload.is_seed:
            updates["authorHash"] = "seed"
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    driver = get_driver()
    query = """
    MATCH (cm:Comment {id: $id})
    SET cm += $updates,
        cm.updatedAt = datetime()
    RETURN cm
    """
    with _db_session(driver) as session:
        records = _execute_write(session, query, {"id": comment_id, "updates": updates})
        record = records[0] if records else None
        if record is not None:
            _execute_write(
                session,
                """
                MATCH (cm:Comment {id: $id})<-[:HAS_COMMENT]-(c:Conversation)
                CREATE (log:ModerationLog {
                    id: $log_id,
                    action: "edit",
                    status: cm.status,
                    createdAt: datetime()
                })
                CREATE (log)-[:FOR_CONVERSATION]->(c)
                CREATE (log)-[:FOR_COMMENT]->(cm)
                """,
                {"id": comment_id, "log_id": str(uuid4())},
            )
    if record is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    comment = _node_to_dict(record["cm"])
    return {
        "id": comment["id"],
        "text": comment["text"],
        "status": comment.get("status", "approved"),
        "is_seed": bool(comment.get("isSeed", False)),
        "created_at": str(comment.get("createdAt")),
        "updated_at": str(comment.get("updatedAt")) if comment.get("updatedAt") else None,
        "author_hash": comment.get("authorHash"),
        "agree_count": 0,
        "disagree_count": 0,
        "pass_count": 0,
        "important_count": 0,
    }


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: str):
    driver = get_driver()
    query = """
    MATCH (cm:Comment {id: $id})<-[:HAS_COMMENT]-(c:Conversation)
    CREATE (log:ModerationLog {
        id: $log_id,
        action: "delete",
        status: cm.status,
        createdAt: datetime()
    })
    CREATE (log)-[:FOR_CONVERSATION]->(c)
    CREATE (log)-[:FOR_COMMENT]->(cm)
    DETACH DELETE cm
    RETURN $id AS deleted_id
    """
    with _db_session(driver) as session:
        records = _execute_write(session, query, {"id": comment_id, "log_id": str(uuid4())})
    if not records:
        raise HTTPException(status_code=404, detail="Comment not found")
    return {"deleted": True, "comment_id": comment_id}


@router.post("/vote")
def cast_vote(
    payload: VoteCreate,
    x_participant_id: Optional[str] = Header(None),
    x_invite_code: Optional[str] = Header(None),
):
    if payload.choice not in (-1, 0, 1):
        raise HTTPException(status_code=400, detail="Vote choice must be -1, 0, or 1")
    convo = _get_conversation(payload.conversation_id)
    if not bool(convo.get("isOpen", True)):
        raise HTTPException(status_code=400, detail="Conversation is closed")
    if not bool(convo.get("allowVoting", True)):
        raise HTTPException(status_code=400, detail="Voting is disabled for this conversation")
    identity_mode = convo.get("identityMode") or "anonymous"
    if identity_mode == "xid_required" and not (payload.participant_id or x_participant_id):
        raise HTTPException(status_code=400, detail="Identity is required to vote")

    raw_id = payload.participant_id or x_participant_id or str(uuid4())
    participant_id = _hash_participant(raw_id)
    if bool(convo.get("inviteOnly", False)):
        _validate_invite(payload.conversation_id, x_invite_code, participant_id)
    _enforce_rate_limit(convo, participant_id, "vote")
    driver = get_driver()
    query = """
    MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(cm:Comment {id: $comment_id})
    WHERE cm.status = "approved"
    MERGE (p:Participant {id: $pid})
    ON CREATE SET p.createdAt = datetime()
    MERGE (p)-[:PARTICIPATED_IN]->(c)
    MERGE (p)-[v:VOTED]->(cm)
    SET v.choice = $choice,
        v.votedAt = datetime(),
        v.important = $important
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
                "important": bool(payload.important),
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
        important = _normalize_optional_bool(item.important)
        if not participant_raw or not comment_id or choice is None:
            invalid_rows += 1
            continue
        cleaned_votes.append(
            {
                "participant_id": _hash_participant(participant_raw),
                "comment_id": comment_id,
                "choice": int(choice),
                "important": bool(important) if important is not None else False,
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
                r.votedAt = datetime(),
                r.important = v.important
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
        important = _normalize_optional_bool(item.important)
        if choice is not None and participant_raw:
            votes.append(
                {
                    "participant_id": _hash_participant(participant_raw),
                    "comment_id": comment_id,
                    "choice": int(choice),
                    "reaction_created_at": _normalize_optional_timestamp(item.reaction_created_at),
                    "participant_cluster": participant_cluster,
                    "important": bool(important) if important is not None else False,
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
                    r.important = v.important,
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
                r.votedAt = datetime(),
                r.important = false
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
    RETURN p.id AS participant_id, cm.id AS comment_id, v.choice AS choice, v.important AS important, v.votedAt AS voted_at
    """
    with _db_session(driver) as session:
        comment_records = _execute_read(session, comments_query, {"cid": conversation_id})
        vote_records = _execute_read(session, votes_query, {"cid": conversation_id})
    comments = [_node_to_dict(record["cm"]) for record in comment_records]
    votes = [record.data() for record in vote_records]
    return comments, votes


def _ensure_min_participants(conversation_id: str, min_required: int) -> int:
    if min_required <= 0:
        return 0
    driver = get_driver()
    with _db_session(driver) as session:
        participant_records = _execute_read(
            session,
            """
            MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(cm:Comment)
            MATCH (p:Participant)-[:VOTED]->(cm)
            RETURN count(DISTINCT p) AS count
            """,
            {"cid": conversation_id},
        )
    current = int(participant_records[0]["count"]) if participant_records else 0
    if current >= min_required:
        return 0
    missing = min_required - current

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
        return 0

    votes_per_participant = min(20, len(comment_ids))
    rng = random.Random(42)
    votes = []
    for _ in range(missing):
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
        _execute_write(
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
                r.votedAt = datetime(),
                r.important = false
            """,
            {"cid": conversation_id, "votes": votes},
        )
    return missing


def _build_metrics(conversation_id: str) -> MetricsOut:
    convo = _get_conversation(conversation_id)
    comments, votes = _collect_comments_and_votes(conversation_id)
    participants = len({vote["participant_id"] for vote in votes})
    if MIN_SURVEY_PARTICIPANTS and participants < MIN_SURVEY_PARTICIPANTS:
        _ensure_min_participants(conversation_id, MIN_SURVEY_PARTICIPANTS)
        comments, votes = _collect_comments_and_votes(conversation_id)
    points, label_map = run_clustering(votes)
    min_votes = int(convo.get("minVotesForInclusion") or 3)
    consensus, polarizing = compute_metrics(comments, votes, label_map, min_votes)
    cluster_summaries, cluster_similarity = compute_cluster_insights(
        comments, votes, label_map, min_votes
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


@router.post("/conversations/{conversation_id}/view")
def record_view(conversation_id: str, x_participant_id: Optional[str] = Header(None)):
    convo = _get_conversation(conversation_id)
    if not bool(convo.get("isOpen", True)):
        raise HTTPException(status_code=400, detail="Conversation is closed")
    viewer_hash = _hash_participant(x_participant_id) if x_participant_id else None
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            MATCH (c:Conversation {id: $cid})
            CREATE (vw:View {
                id: $id,
                createdAt: datetime(),
                viewerHash: $viewer_hash
            })
            CREATE (vw)-[:VIEWED]->(c)
            """,
            {"cid": conversation_id, "id": str(uuid4()), "viewer_hash": viewer_hash},
        )
    return {"ok": True}


@router.get("/conversations/{conversation_id}/stats")
def conversation_stats(conversation_id: str):
    _get_conversation(conversation_id)
    driver = get_driver()

    def _series(query):
        with _db_session(driver) as session:
            records = _execute_read(session, query, {"cid": conversation_id})
        return [
            {"date": str(record["day"]), "count": int(record["count"] or 0)}
            for record in records
            if record.get("day") is not None
        ]

    views_over_time = _series(
        """
        MATCH (c:Conversation {id: $cid})<-[:VIEWED]-(vw:View)
        WITH date(vw.createdAt) AS day, count(vw) AS count
        RETURN day, count
        ORDER BY day
        """
    )
    comments_over_time = _series(
        """
        MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(cm:Comment)
        WITH date(cm.createdAt) AS day, count(cm) AS count
        RETURN day, count
        ORDER BY day
        """
    )
    votes_over_time = _series(
        """
        MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(cm:Comment)<-[v:VOTED]-(:Participant)
        WITH date(v.votedAt) AS day, count(v) AS count
        RETURN day, count
        ORDER BY day
        """
    )

    with _db_session(driver) as session:
        totals = _execute_read(
            session,
            """
            MATCH (c:Conversation {id: $cid})
            OPTIONAL MATCH (c)<-[:VIEWED]-(vw:View)
            OPTIONAL MATCH (c)-[:HAS_COMMENT]->(cm:Comment)
            OPTIONAL MATCH (c)-[:HAS_COMMENT]->(cm2:Comment)<-[:VOTED]-(p:Participant)
            RETURN
              count(DISTINCT vw) AS views,
              count(DISTINCT cm) AS comments,
              count(DISTINCT p) AS voters,
              count(DISTINCT cm.authorHash) AS commenters,
              count(DISTINCT p) AS participants,
              count(DISTINCT cm2) AS voted_comments
            """,
            {"cid": conversation_id},
        )
        votes_total_records = _execute_read(
            session,
            """
            MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(cm:Comment)<-[v:VOTED]-(:Participant)
            RETURN count(v) AS votes
            """,
            {"cid": conversation_id},
        )
    totals_row = totals[0] if totals else {}
    votes_total = int(votes_total_records[0]["votes"] or 0) if votes_total_records else 0
    voters = int(totals_row.get("voters") or 0)
    votes_per_participant = round(votes_total / voters, 2) if voters else 0

    return {
        "views": int(totals_row.get("views") or 0),
        "comments": int(totals_row.get("comments") or 0),
        "voters": voters,
        "commenters": int(totals_row.get("commenters") or 0),
        "participants": int(totals_row.get("participants") or 0),
        "votes": votes_total,
        "votes_per_participant": votes_per_participant,
        "views_over_time": views_over_time,
        "comments_over_time": comments_over_time,
        "votes_over_time": votes_over_time,
    }


@router.get("/conversations/{conversation_id}/moderation-log")
def moderation_log(conversation_id: str):
    _get_conversation(conversation_id)
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            """
            MATCH (log:ModerationLog)-[:FOR_CONVERSATION]->(c:Conversation {id: $cid})
            OPTIONAL MATCH (log)-[:FOR_COMMENT]->(cm:Comment)
            RETURN log, cm.id AS comment_id
            ORDER BY log.createdAt DESC
            """,
            {"cid": conversation_id},
        )
    entries = []
    for record in records:
        log = _node_to_dict(record["log"])
        entries.append(
            {
                "id": log.get("id"),
                "action": log.get("action"),
                "status": log.get("status"),
                "reason": log.get("reason"),
                "comment_id": record.get("comment_id"),
                "created_at": str(log.get("createdAt")),
            }
        )
    return {"entries": entries}


@router.get("/conversations/{conversation_id}/export")
def export_conversation(conversation_id: str):
    convo = _get_conversation(conversation_id)
    comments, votes = _collect_comments_and_votes(conversation_id)
    metrics, _, _, _, _, _ = _build_metrics(conversation_id)
    stats = conversation_stats(conversation_id)

    comment_lookup = {comment["id"]: comment for comment in comments}
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

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        summary_rows = [
            {"key": "conversation_id", "value": convo.get("id")},
            {"key": "topic", "value": convo.get("topic")},
            {"key": "description", "value": convo.get("description")},
            {"key": "is_open", "value": convo.get("isOpen", True)},
            {"key": "allow_comment_submission", "value": convo.get("allowCommentSubmission", True)},
            {"key": "allow_viz", "value": convo.get("allowViz", True)},
            {"key": "allow_voting", "value": convo.get("allowVoting", True)},
            {"key": "moderation_profile", "value": convo.get("moderationProfile") or "lazy"},
            {"key": "min_votes_for_inclusion", "value": convo.get("minVotesForInclusion") or 3},
            {"key": "profanity_filter_enabled", "value": convo.get("profanityFilterEnabled", False)},
            {"key": "rate_limit_per_minute", "value": convo.get("rateLimitPerMinute", 0)},
            {"key": "identity_mode", "value": convo.get("identityMode") or "anonymous"},
            {"key": "invite_only", "value": convo.get("inviteOnly", False)},
        ]
        _write_csv_to_zip(zf, "summary.csv", summary_rows, ["key", "value"])

        comment_rows = []
        for comment in comments:
            counts = vote_counts.get(comment["id"], {})
            comment_rows.append(
                {
                    "comment_id": comment["id"],
                    "text": comment.get("text", ""),
                    "status": comment.get("status", "approved"),
                    "is_seed": bool(comment.get("isSeed", False)),
                    "author_hash": comment.get("authorHash"),
                    "created_at": comment.get("createdAt"),
                    "agree_count": counts.get("agree", 0),
                    "disagree_count": counts.get("disagree", 0),
                    "pass_count": counts.get("pass", 0),
                    "important_count": counts.get("important", 0),
                }
            )
        _write_csv_to_zip(
            zf,
            "comments.csv",
            comment_rows,
            [
                "comment_id",
                "text",
                "status",
                "is_seed",
                "author_hash",
                "created_at",
                "agree_count",
                "disagree_count",
                "pass_count",
                "important_count",
            ],
        )

        _write_csv_to_zip(
            zf,
            "votes.csv",
            [
                {
                    "participant_id": vote.get("participant_id"),
                    "comment_id": vote.get("comment_id"),
                    "choice": vote.get("choice"),
                    "important": vote.get("important"),
                    "voted_at": vote.get("voted_at"),
                }
                for vote in votes
            ],
            ["participant_id", "comment_id", "choice", "important", "voted_at"],
        )

        stats_rows = []
        for series_name in ("views_over_time", "comments_over_time", "votes_over_time"):
            for item in stats.get(series_name, []):
                stats_rows.append(
                    {
                        "series": series_name.replace("_over_time", ""),
                        "date": item["date"],
                        "count": item["count"],
                    }
                )
        _write_csv_to_zip(zf, "stats.csv", stats_rows, ["series", "date", "count"])

        metrics_rows = [
            {
                "comment_id": item.id,
                "text": item.text,
                "status": item.status,
                "participation": item.participation,
                "agreement_ratio": item.agreement_ratio,
                "consensus_score": item.consensus_score,
                "polarity_score": item.polarity_score,
                "agree_count": item.agree_count,
                "disagree_count": item.disagree_count,
                "pass_count": item.pass_count,
                "important_count": item.important_count,
            }
            for item in (metrics.consensus + metrics.polarizing)
        ]
        _write_csv_to_zip(
            zf,
            "metrics.csv",
            metrics_rows,
            [
                "comment_id",
                "text",
                "status",
                "participation",
                "agreement_ratio",
                "consensus_score",
                "polarity_score",
                "agree_count",
                "disagree_count",
                "pass_count",
                "important_count",
            ],
        )

    buffer.seek(0)
    filename = f"conversation_{conversation_id}_export.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _build_export_zip_bytes(conversation_id: str) -> bytes:
    convo = _get_conversation(conversation_id)
    comments, votes = _collect_comments_and_votes(conversation_id)
    metrics, _, _, _, _, _ = _build_metrics(conversation_id)
    stats = conversation_stats(conversation_id)

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

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        summary_rows = [
            {"key": "conversation_id", "value": convo.get("id")},
            {"key": "topic", "value": convo.get("topic")},
            {"key": "description", "value": convo.get("description")},
            {"key": "is_open", "value": convo.get("isOpen", True)},
            {"key": "allow_comment_submission", "value": convo.get("allowCommentSubmission", True)},
            {"key": "allow_viz", "value": convo.get("allowViz", True)},
            {"key": "allow_voting", "value": convo.get("allowVoting", True)},
            {"key": "moderation_profile", "value": convo.get("moderationProfile") or "lazy"},
            {"key": "min_votes_for_inclusion", "value": convo.get("minVotesForInclusion") or 3},
            {"key": "profanity_filter_enabled", "value": convo.get("profanityFilterEnabled", False)},
            {"key": "rate_limit_per_minute", "value": convo.get("rateLimitPerMinute", 0)},
            {"key": "identity_mode", "value": convo.get("identityMode") or "anonymous"},
            {"key": "invite_only", "value": convo.get("inviteOnly", False)},
        ]
        _write_csv_to_zip(zf, "summary.csv", summary_rows, ["key", "value"])

        comment_rows = []
        for comment in comments:
            counts = vote_counts.get(comment["id"], {})
            comment_rows.append(
                {
                    "comment_id": comment["id"],
                    "text": comment.get("text", ""),
                    "status": comment.get("status", "approved"),
                    "is_seed": bool(comment.get("isSeed", False)),
                    "author_hash": comment.get("authorHash"),
                    "created_at": comment.get("createdAt"),
                    "agree_count": counts.get("agree", 0),
                    "disagree_count": counts.get("disagree", 0),
                    "pass_count": counts.get("pass", 0),
                    "important_count": counts.get("important", 0),
                }
            )
        _write_csv_to_zip(
            zf,
            "comments.csv",
            comment_rows,
            [
                "comment_id",
                "text",
                "status",
                "is_seed",
                "author_hash",
                "created_at",
                "agree_count",
                "disagree_count",
                "pass_count",
                "important_count",
            ],
        )

        _write_csv_to_zip(
            zf,
            "votes.csv",
            [
                {
                    "participant_id": vote.get("participant_id"),
                    "comment_id": vote.get("comment_id"),
                    "choice": vote.get("choice"),
                    "important": vote.get("important"),
                    "voted_at": vote.get("voted_at"),
                }
                for vote in votes
            ],
            ["participant_id", "comment_id", "choice", "important", "voted_at"],
        )

        stats_rows = []
        for series_name in ("views_over_time", "comments_over_time", "votes_over_time"):
            for item in stats.get(series_name, []):
                stats_rows.append(
                    {
                        "series": series_name.replace("_over_time", ""),
                        "date": item["date"],
                        "count": item["count"],
                    }
                )
        _write_csv_to_zip(zf, "stats.csv", stats_rows, ["series", "date", "count"])

        metrics_rows = [
            {
                "comment_id": item.id,
                "text": item.text,
                "status": item.status,
                "participation": item.participation,
                "agreement_ratio": item.agreement_ratio,
                "consensus_score": item.consensus_score,
                "polarity_score": item.polarity_score,
                "agree_count": item.agree_count,
                "disagree_count": item.disagree_count,
                "pass_count": item.pass_count,
                "important_count": item.important_count,
            }
            for item in (metrics.consensus + metrics.polarizing)
        ]
        _write_csv_to_zip(
            zf,
            "metrics.csv",
            metrics_rows,
            [
                "comment_id",
                "text",
                "status",
                "participation",
                "agreement_ratio",
                "consensus_score",
                "polarity_score",
                "agree_count",
                "disagree_count",
                "pass_count",
                "important_count",
            ],
        )

    buffer.seek(0)
    return buffer.getvalue()


def _write_csv_to_zip(zip_file, name, rows, fieldnames):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    zip_file.writestr(name, output.getvalue())


def _run_export_job(job_id: str, conversation_id: str):
    driver = get_driver()
    file_path = os.path.join(EXPORT_DIR, f"{job_id}.zip")
    try:
        payload = _build_export_zip_bytes(conversation_id)
        with open(file_path, "wb") as handle:
            handle.write(payload)
        with _db_session(driver) as session:
            _execute_write(
                session,
                """
                MATCH (j:ExportJob {id: $id})
                SET j.status = "completed",
                    j.completedAt = datetime(),
                    j.filePath = $file_path
                """,
                {"id": job_id, "file_path": file_path},
            )
    except Exception as err:
        with _db_session(driver) as session:
            _execute_write(
                session,
                """
                MATCH (j:ExportJob {id: $id})
                SET j.status = "failed",
                    j.completedAt = datetime(),
                    j.error = $error
                """,
                {"id": job_id, "error": str(err)},
            )


@router.post("/conversations/{conversation_id}/exports")
def create_export_job(conversation_id: str, background_tasks: BackgroundTasks):
    _get_conversation(conversation_id)
    job_id = str(uuid4())
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            MATCH (c:Conversation {id: $cid})
            CREATE (j:ExportJob {
              id: $id,
              createdAt: datetime(),
              status: "pending"
            })
            CREATE (j)-[:FOR_CONVERSATION]->(c)
            """,
            {"cid": conversation_id, "id": job_id},
        )
    background_tasks.add_task(_run_export_job, job_id, conversation_id)
    return {"job_id": job_id, "status": "pending"}


@router.get("/exports/{job_id}")
def get_export_job(job_id: str):
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            """
            MATCH (j:ExportJob {id: $id})
            RETURN j
            """,
            {"id": job_id},
        )
    if not records:
        raise HTTPException(status_code=404, detail="Export job not found")
    job = _node_to_dict(records[0]["j"])
    return {
        "id": job.get("id"),
        "status": job.get("status"),
        "created_at": str(job.get("createdAt")),
        "completed_at": str(job.get("completedAt")) if job.get("completedAt") else None,
        "error": job.get("error"),
    }


@router.get("/exports/{job_id}/download")
def download_export_job(job_id: str):
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            """
            MATCH (j:ExportJob {id: $id})
            RETURN j
            """,
            {"id": job_id},
        )
    if not records:
        raise HTTPException(status_code=404, detail="Export job not found")
    job = _node_to_dict(records[0]["j"])
    if job.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Export not ready")
    file_path = job.get("filePath")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Export file missing")
    filename = f"export_{job_id}.zip"
    with open(file_path, "rb") as handle:
        data = handle.read()
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'},
    )


@router.post("/conversations/{conversation_id}/invite-waves")
def create_invite_wave(conversation_id: str, payload: InviteWaveCreate):
    _get_conversation(conversation_id)
    wave_id = str(uuid4())
    codes = [_generate_invite_code() for _ in range(payload.count)]
    invite_rows = [{"id": str(uuid4()), "code": code} for code in codes]
    driver = get_driver()
    with _db_session(driver) as session:
        parent_id = None
        if payload.parent_code:
            parent_records = _execute_read(
                session,
                """
                MATCH (inv:Invite {code: $code})
                RETURN inv.id AS id
                """,
                {"code": payload.parent_code},
            )
            if parent_records:
                parent_id = parent_records[0]["id"]
        _execute_write(
            session,
            """
            MATCH (c:Conversation {id: $cid})
            CREATE (w:InviteWave {
                id: $wid,
                name: $name,
                createdAt: datetime(),
                count: $count
            })
            CREATE (w)-[:FOR_CONVERSATION]->(c)
            """,
            {"cid": conversation_id, "wid": wave_id, "name": payload.name, "count": payload.count},
        )
        _execute_write(
            session,
            """
            MATCH (w:InviteWave {id: $wid})
            MATCH (c:Conversation {id: $cid})
            UNWIND $invites AS invite
            CREATE (inv:Invite {
                id: invite.id,
                code: invite.code,
                createdAt: datetime(),
                revoked: false
            })
            CREATE (inv)-[:IN_WAVE]->(w)
            CREATE (inv)-[:FOR_CONVERSATION]->(c)
            WITH inv
            OPTIONAL MATCH (parent:Invite {id: $parent_id})
            FOREACH (_ IN CASE WHEN parent IS NULL THEN [] ELSE [1] END |
              CREATE (inv)-[:CHILD_OF]->(parent)
            )
            """,
            {
                "wid": wave_id,
                "cid": conversation_id,
                "invites": invite_rows,
                "parent_id": parent_id,
            },
        )
    return {"wave_id": wave_id, "count": len(codes), "codes": codes}


@router.get("/conversations/{conversation_id}/invite-waves")
def list_invite_waves(conversation_id: str):
    _get_conversation(conversation_id)
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            """
            MATCH (w:InviteWave)-[:FOR_CONVERSATION]->(c:Conversation {id: $cid})
            OPTIONAL MATCH (inv:Invite)-[:IN_WAVE]->(w)
            RETURN w, collect(inv) AS invites
            ORDER BY w.createdAt DESC
            """,
            {"cid": conversation_id},
        )
    waves = []
    for record in records:
        wave = _node_to_dict(record["w"])
        invites = [_node_to_dict(inv) for inv in record["invites"] if inv]
        waves.append(
            {
                "id": wave.get("id"),
                "name": wave.get("name"),
                "created_at": str(wave.get("createdAt")),
                "count": int(wave.get("count") or len(invites)),
                "invites": [
                    {
                        "id": inv.get("id"),
                        "code": inv.get("code"),
                        "revoked": bool(inv.get("revoked", False)),
                    }
                    for inv in invites
                ],
            }
        )
    return {"waves": waves}


@router.post("/invites/{invite_id}/revoke")
def revoke_invite(invite_id: str, cascade: bool = Query(False)):
    driver = get_driver()
    with _db_session(driver) as session:
        if cascade:
            _execute_write(
                session,
                """
                MATCH (root:Invite {id: $id})
                OPTIONAL MATCH (child:Invite)-[:CHILD_OF*0..]->(root)
                SET child.revoked = true, child.revokedAt = datetime()
                RETURN count(child) AS total
                """,
                {"id": invite_id},
            )
        else:
            _execute_write(
                session,
                """
                MATCH (inv:Invite {id: $id})
                SET inv.revoked = true, inv.revokedAt = datetime()
                RETURN inv
                """,
                {"id": invite_id},
            )
    return {"revoked": True, "invite_id": invite_id, "cascade": cascade}


@router.get("/conversations/{conversation_id}/invite/validate")
def validate_invite(conversation_id: str, code: str):
    _get_conversation(conversation_id)
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            """
            MATCH (inv:Invite {code: $code})-[:FOR_CONVERSATION]->(c:Conversation {id: $cid})
            OPTIONAL MATCH (inv)-[:CHILD_OF*0..]->(parent:Invite)
            WITH inv, collect(parent) AS parents
            RETURN inv, any(p IN parents WHERE coalesce(p.revoked, false)) AS revoked_chain
            """,
            {"code": code, "cid": conversation_id},
        )
    if not records:
        return {"valid": False, "reason": "invalid"}
    inv = _node_to_dict(records[0]["inv"])
    revoked_chain = bool(records[0].get("revoked_chain"))
    if inv.get("revoked") or revoked_chain:
        return {"valid": False, "reason": "revoked"}
    return {"valid": True}


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


@router.post("/conversations/{conversation_id}/ingest")
def ingest_text(conversation_id: str, payload: IngestRequest):
    _get_conversation(conversation_id)
    raw = payload.text.strip()
    if payload.strategy == "lines" or (payload.strategy == "auto" and "\n" in raw):
        items = [line.strip() for line in raw.splitlines() if line.strip()]
    else:
        items = re.split(r"(?<=[.!?])\s+", raw)
        items = [item.strip() for item in items if item.strip()]
    deduped = []
    seen = set()
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= payload.max_items:
            break
    return {"items": deduped, "total": len(deduped)}


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
