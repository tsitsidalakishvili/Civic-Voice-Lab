"""
Conversation CRUD, queue endpoint, seeding, invite waves.
"""
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Query

from .db import get_driver
from .routes_helpers import (
    _contains_profanity,
    _conversation_out,
    _db_session,
    _enforce_rate_limit,
    _execute_read,
    _execute_write,
    _generate_invite_code,
    _get_conversation,
    _hash_participant,
    _node_to_dict,
    _validate_invite,
)
from .schemas import (
    CommentCreate,
    CommentOut,
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    InviteWaveCreate,
    QueueRequest,
    SeedCommentsRequest,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Conversation CRUD
# ---------------------------------------------------------------------------


@router.post("/conversations", response_model=ConversationOut)
def create_conversation(payload: ConversationCreate):
    convo_id = str(uuid4())
    moderation_profile = payload.moderation_profile or "lazy"
    moderation_required = payload.moderation_required or moderation_profile == "strict"
    initial_statements = [str(text).strip() for text in (payload.initial_statements or [])]
    initial_statements = [text for text in initial_statements if text]
    statement_rows = [{"id": str(uuid4()), "text": text} for text in initial_statements]
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
        if statement_rows:
            _execute_write(
                session,
                """
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
                """,
                {"cid": convo_id, "items": statement_rows},
            )
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
    WHERE p IS NULL OR (coalesce(p.isSynthetic, false) = false
      AND NOT p.id =~ '(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
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


# ---------------------------------------------------------------------------
# Seed comments (bulk)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Queue endpoint
# ---------------------------------------------------------------------------


@router.post("/conversations/{conversation_id}/queue")
def get_comment_queue(
    conversation_id: str,
    payload: QueueRequest,
    x_participant_id: Optional[str] = Header(None),
):
    from datetime import datetime as _dt

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
                    (_dt.utcnow() - _dt.fromisoformat(str(created_at))).days,
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


# ---------------------------------------------------------------------------
# View recording
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Invite waves
# ---------------------------------------------------------------------------


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

