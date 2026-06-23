"""
Comment creation, listing, moderation, status updates, and deletion.
"""
import re
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Query

from .db import get_driver
from .services.sentiment_service import score_sentiment
from .routes_helpers import (
    _contains_profanity,
    _db_session,
    _enforce_rate_limit,
    _execute_read,
    _execute_write,
    _get_conversation,
    _hash_participant,
    _node_to_dict,
    _validate_invite,
)
from .schemas import (
    CommentCreate,
    CommentOut,
    CommentStatusUpdate,
    CommentUpdate,
    IngestRequest,
    StatementDiscussionCommentCreate,
    StatementDiscussionCommentOut,
    StatementDiscussionReactionCreate,
)

router = APIRouter()


def _serialize_statement_discussion_comment(record, my_participant_hash: Optional[str] = None):
    comment = _node_to_dict(record["sc"])
    my_reaction = record.get("my_reaction")
    if not my_reaction and my_participant_hash:
        my_reaction = None
    sentiment_score = comment.get("sentimentScore")
    sentiment_label = comment.get("sentimentLabel")
    if sentiment_score is None or not sentiment_label:
        sentiment = score_sentiment(comment.get("text") or "")
        sentiment_score = sentiment.score
        sentiment_label = sentiment.label
        comment["sentimentConfidence"] = sentiment.confidence
        comment["sentimentProvider"] = sentiment.provider
    like_count = int(record.get("like_count") or 0)
    agree_count = int(record.get("agree_count") or 0)
    disagree_count = int(record.get("disagree_count") or 0)
    consensus_impact = like_count + agree_count - disagree_count + float(sentiment_score or 0)
    return {
        "id": comment["id"],
        "statement_id": comment.get("statementId") or "",
        "conversation_id": comment.get("conversationId") or "",
        "text": comment.get("text") or "",
        "created_at": str(comment.get("createdAt")) if comment.get("createdAt") else None,
        "updated_at": str(comment.get("updatedAt")) if comment.get("updatedAt") else None,
        "author_hash": comment.get("authorHash"),
        "like_count": like_count,
        "agree_count": agree_count,
        "disagree_count": disagree_count,
        "insightful_count": int(record.get("insightful_count") or 0),
        "sentiment_score": round(float(sentiment_score or 0), 3),
        "sentiment_label": sentiment_label or "neutral",
        "sentiment_confidence": round(float(comment.get("sentimentConfidence") or 0), 3),
        "sentiment_provider": comment.get("sentimentProvider") or "unavailable",
        "consensus_impact": round(consensus_impact, 3),
        "my_reaction": my_reaction,
    }


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
    include_stats: bool = Query(
        True,
        description="Include vote aggregates per comment. Disable for faster moderation queues.",
    ),
):
    driver = get_driver()
    if include_stats:
        query = """
        MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(cm:Comment)
        WHERE $status IS NULL OR cm.status = $status
        OPTIONAL MATCH (p:Participant)-[v:VOTED]->(cm)
        WHERE p IS NULL OR (coalesce(p.isSynthetic, false) = false
          AND NOT p.id =~ '(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
        WITH cm,
            sum(CASE WHEN v.choice = 1 THEN 1 ELSE 0 END) AS agree_count,
            sum(CASE WHEN v.choice = -1 THEN 1 ELSE 0 END) AS disagree_count,
            sum(CASE WHEN v.choice = 0 THEN 1 ELSE 0 END) AS pass_count,
            sum(CASE WHEN coalesce(v.important, false) THEN 1 ELSE 0 END) AS important_count
        RETURN cm, agree_count, disagree_count, pass_count, important_count
        ORDER BY cm.createdAt
        """
    else:
        query = """
        MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(cm:Comment)
        WHERE $status IS NULL OR cm.status = $status
        RETURN
          cm,
          0 AS agree_count,
          0 AS disagree_count,
          0 AS pass_count,
          0 AS important_count
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


@router.get(
    "/conversations/{conversation_id}/statements/{statement_id}/discussion-comments",
    response_model=List[StatementDiscussionCommentOut],
)
def list_statement_discussion_comments(
    conversation_id: str,
    statement_id: str,
    x_participant_id: Optional[str] = Header(None),
):
    participant_hash = _hash_participant(x_participant_id) if x_participant_id else "__anon__"
    driver = get_driver()
    query = """
    MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(st:Comment {id: $sid})
    OPTIONAL MATCH (sc:StatementComment)-[:ON_STATEMENT]->(st)
    WITH c, st, sc
    WHERE sc IS NOT NULL
    OPTIONAL MATCH (p:Participant)-[r:REACTED_TO]->(sc)
    WITH sc,
        sum(CASE WHEN r.reaction = 'like' THEN 1 ELSE 0 END) AS like_count,
        sum(CASE WHEN r.reaction = 'agree' THEN 1 ELSE 0 END) AS agree_count,
        sum(CASE WHEN r.reaction = 'disagree' THEN 1 ELSE 0 END) AS disagree_count,
        sum(CASE WHEN r.reaction = 'insightful' THEN 1 ELSE 0 END) AS insightful_count,
        head(
            [value IN collect(CASE WHEN p.id = $pid THEN r.reaction ELSE null END) WHERE value IS NOT NULL]
        ) AS my_reaction
    RETURN sc, like_count, agree_count, disagree_count, insightful_count, my_reaction
    ORDER BY sc.createdAt DESC
    """
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            query,
            {"cid": conversation_id, "sid": statement_id, "pid": participant_hash},
        )
    return [
        _serialize_statement_discussion_comment(record, participant_hash)
        for record in records
        if record.get("sc") is not None
    ]


@router.post(
    "/conversations/{conversation_id}/statements/{statement_id}/discussion-comments",
    response_model=StatementDiscussionCommentOut,
)
def create_statement_discussion_comment(
    conversation_id: str,
    statement_id: str,
    payload: StatementDiscussionCommentCreate,
    x_participant_id: Optional[str] = Header(None),
    x_invite_code: Optional[str] = Header(None),
):
    convo = _get_conversation(conversation_id)
    if not bool(convo.get("isOpen", True)):
        raise HTTPException(status_code=400, detail="Conversation is closed")
    identity_mode = convo.get("identityMode") or "anonymous"
    if identity_mode == "xid_required" and not (payload.author_id or x_participant_id):
        raise HTTPException(status_code=400, detail="Identity is required to comment")
    raw_id = payload.author_id or x_participant_id or str(uuid4())
    author_hash = _hash_participant(raw_id)
    if bool(convo.get("inviteOnly", False)):
        _validate_invite(conversation_id, x_invite_code, author_hash)
    _enforce_rate_limit(convo, author_hash, "comment")

    cleaned_text = payload.text.strip()
    if not cleaned_text:
        raise HTTPException(status_code=400, detail="Comment text is required")
    discussion_comment_id = str(uuid4())
    sentiment = score_sentiment(cleaned_text)
    driver = get_driver()
    query = """
    MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(st:Comment {id: $sid})
    CREATE (sc:StatementComment {
        id: $id,
        statementId: $sid,
        conversationId: $cid,
        text: $text,
        authorHash: $author_hash,
        sentimentScore: $sentiment_score,
        sentimentLabel: $sentiment_label,
        sentimentConfidence: $sentiment_confidence,
        sentimentProvider: $sentiment_provider,
        sentimentProcessedText: $sentiment_processed_text,
        createdAt: datetime(),
        updatedAt: datetime()
    })
    CREATE (sc)-[:ON_STATEMENT]->(st)
    CREATE (c)-[:HAS_STATEMENT_COMMENT]->(sc)
    RETURN sc
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "cid": conversation_id,
                "sid": statement_id,
                "id": discussion_comment_id,
                "text": cleaned_text,
                "author_hash": author_hash,
                "sentiment_score": sentiment.score,
                "sentiment_label": sentiment.label,
                "sentiment_confidence": sentiment.confidence,
                "sentiment_provider": sentiment.provider,
                "sentiment_processed_text": sentiment.processed_text,
            },
        )
    if not records:
        raise HTTPException(status_code=404, detail="Statement not found in conversation")
    return _serialize_statement_discussion_comment(
        {
            "sc": records[0]["sc"],
            "like_count": 0,
            "agree_count": 0,
            "disagree_count": 0,
            "insightful_count": 0,
            "my_reaction": None,
        },
        author_hash,
    )


@router.post(
    "/conversations/{conversation_id}/statements/{statement_id}/discussion-comments/{discussion_comment_id}/reactions",
    response_model=StatementDiscussionCommentOut,
)
def react_to_statement_discussion_comment(
    conversation_id: str,
    statement_id: str,
    discussion_comment_id: str,
    payload: StatementDiscussionReactionCreate,
    x_participant_id: Optional[str] = Header(None),
    x_invite_code: Optional[str] = Header(None),
):
    convo = _get_conversation(conversation_id)
    if not bool(convo.get("isOpen", True)):
        raise HTTPException(status_code=400, detail="Conversation is closed")
    raw_id = payload.author_id or x_participant_id or str(uuid4())
    participant_hash = _hash_participant(raw_id)
    if bool(convo.get("inviteOnly", False)):
        _validate_invite(conversation_id, x_invite_code, participant_hash)
    _enforce_rate_limit(convo, participant_hash, "vote")

    driver = get_driver()
    mutation = """
    MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(st:Comment {id: $sid})
    MATCH (sc:StatementComment {id: $dcid})-[:ON_STATEMENT]->(st)
    MERGE (p:Participant {id: $pid})
    ON CREATE SET p.createdAt = datetime()
    MERGE (p)-[:PARTICIPATED_IN]->(c)
    MERGE (p)-[r:REACTED_TO]->(sc)
    ON CREATE SET r.createdAt = datetime()
    SET r.reaction = $reaction,
        r.updatedAt = datetime()
    RETURN sc
    """
    summary = """
    MATCH (sc:StatementComment {id: $dcid})
    OPTIONAL MATCH (p:Participant)-[r:REACTED_TO]->(sc)
    WITH sc,
        sum(CASE WHEN r.reaction = 'like' THEN 1 ELSE 0 END) AS like_count,
        sum(CASE WHEN r.reaction = 'agree' THEN 1 ELSE 0 END) AS agree_count,
        sum(CASE WHEN r.reaction = 'disagree' THEN 1 ELSE 0 END) AS disagree_count,
        sum(CASE WHEN r.reaction = 'insightful' THEN 1 ELSE 0 END) AS insightful_count,
        head(
            [value IN collect(CASE WHEN p.id = $pid THEN r.reaction ELSE null END) WHERE value IS NOT NULL]
        ) AS my_reaction
    RETURN sc, like_count, agree_count, disagree_count, insightful_count, my_reaction
    """
    with _db_session(driver) as session:
        mutation_records = _execute_write(
            session,
            mutation,
            {
                "cid": conversation_id,
                "sid": statement_id,
                "dcid": discussion_comment_id,
                "pid": participant_hash,
                "reaction": payload.reaction,
            },
        )
        if not mutation_records:
            raise HTTPException(status_code=404, detail="Statement comment not found")
        summary_records = _execute_read(
            session,
            summary,
            {"dcid": discussion_comment_id, "pid": participant_hash},
        )
    if not summary_records:
        raise HTTPException(status_code=404, detail="Statement comment not found")
    return _serialize_statement_discussion_comment(summary_records[0], participant_hash)


# ---------------------------------------------------------------------------
# Ingest text as proposed comments
# ---------------------------------------------------------------------------


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

