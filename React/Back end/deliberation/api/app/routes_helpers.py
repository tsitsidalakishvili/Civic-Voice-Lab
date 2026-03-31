"""
Shared helpers, constants, and utility functions used across multiple route modules.
"""
import csv
import hashlib
import io
import os
from datetime import datetime
from typing import Optional

from fastapi import HTTPException

from .db import get_active_database, get_driver

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _db_session(driver):
    return driver.session(database=get_active_database())


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


# ---------------------------------------------------------------------------
# Node / participant helpers
# ---------------------------------------------------------------------------


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


def _hash_participant(raw_id: str) -> str:
    digest = hashlib.sha256(f"{ANON_SALT}:{raw_id}".encode("utf-8")).hexdigest()
    return digest


# ---------------------------------------------------------------------------
# Conversation helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Vote / field normalisation helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Profanity / rate-limit helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Invite helpers
# ---------------------------------------------------------------------------


def _generate_invite_code() -> str:
    from uuid import uuid4
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


# ---------------------------------------------------------------------------
# CSV / ZIP helper
# ---------------------------------------------------------------------------


def _write_csv_to_zip(zip_file, name, rows, fieldnames):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    zip_file.writestr(name, output.getvalue())
