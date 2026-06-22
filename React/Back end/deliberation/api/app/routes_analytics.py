"""
Metrics, clustering, insights, stats, and moderation log endpoints.
"""
import random
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from .analytics import compute_cluster_insights, compute_metrics, run_clustering
from .db import get_driver
from .services.sentiment_service import score_sentiment
from .routes_helpers import (
    _db_session,
    _execute_read,
    _execute_write,
    _get_conversation,
    _node_to_dict,
)
from .schemas import MetricsOut, ReportOut

router = APIRouter()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


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
    WHERE coalesce(p.isSynthetic, false) = false
      AND NOT p.id =~ '(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    RETURN p.id AS participant_id, cm.id AS comment_id, v.choice AS choice, v.important AS important, v.votedAt AS voted_at
    """
    discussion_query = """
    MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(cm:Comment)
    OPTIONAL MATCH (sc:StatementComment)-[:ON_STATEMENT]->(cm)
    WITH cm.id AS comment_id, sc
    WHERE sc IS NOT NULL
    RETURN comment_id, sc.text AS text, sc.sentimentScore AS sentiment_score
    """
    with _db_session(driver) as session:
        comment_records = _execute_read(session, comments_query, {"cid": conversation_id})
        vote_records = _execute_read(session, votes_query, {"cid": conversation_id})
        discussion_records = _execute_read(session, discussion_query, {"cid": conversation_id})
    discussion_scores = {}
    for record in discussion_records:
        comment_id = record.get("comment_id")
        if not comment_id:
            continue
        score = record.get("sentiment_score")
        if score is None:
            score = score_sentiment(record.get("text") or "").score
        score = float(score or 0)
        bucket = discussion_scores.setdefault(
            comment_id,
            {"discussion_sentiment_score": 0.0, "negative_comment_weight": 0.0},
        )
        bucket["discussion_sentiment_score"] += score
        if score < 0:
            bucket["negative_comment_weight"] += abs(score)
    comments = []
    for record in comment_records:
        comment = _node_to_dict(record["cm"])
        comment.update(
            discussion_scores.get(
                comment.get("id"),
                {"discussion_sentiment_score": 0.0, "negative_comment_weight": 0.0},
            )
        )
        comments.append(comment)
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


def _build_metrics(conversation_id: str):
    convo = _get_conversation(conversation_id)
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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


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
            WHERE p IS NULL OR (coalesce(p.isSynthetic, false) = false
              AND NOT p.id =~ '(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
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
            MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(cm:Comment)<-[v:VOTED]-(p:Participant)
            WHERE coalesce(p.isSynthetic, false) = false
              AND NOT p.id =~ '(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
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

