"""
Vote submission endpoints — single vote, bulk import, bulk dataset import, simulate votes.
"""
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException

from .db import get_driver
from .routes_helpers import (
    _db_session,
    _enforce_rate_limit,
    _execute_read,
    _execute_write,
    _get_conversation,
    _hash_participant,
    _normalize_optional_bool,
    _normalize_optional_timestamp,
    _normalize_vote_choice,
    _validate_invite,
)
from .schemas import (
    ConversationDatasetImportRequest,
    SimulateVotesRequest,
    VoteCreate,
    VotesImportRequest,
)

import random

router = APIRouter()


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
