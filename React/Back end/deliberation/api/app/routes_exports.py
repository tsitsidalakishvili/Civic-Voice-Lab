"""
CSV/ZIP exports (inline and async job-based) and data imports.
"""
import csv
import io
import os
import zipfile
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from .db import get_driver
from .routes_analytics import _build_metrics, _collect_comments_and_votes, conversation_stats
from .routes_helpers import (
    EXPORT_DIR,
    _db_session,
    _execute_read,
    _execute_write,
    _get_conversation,
    _node_to_dict,
    _write_csv_to_zip,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Shared ZIP-building logic
# ---------------------------------------------------------------------------


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


def _vote_choice_label(choice):
    if choice == 1:
        return "agree"
    if choice == -1:
        return "disagree"
    if choice == 0:
        return "pass"
    return ""


def _build_flat_export_rows(conversation_id: str):
    convo = _get_conversation(conversation_id)
    comments, votes = _collect_comments_and_votes(conversation_id)
    comment_lookup = {comment.get("id"): comment for comment in comments}
    rows = []

    # Statement rows (seed + participant-submitted statements).
    for comment in comments:
        rows.append(
            {
                "conversation_id": convo.get("id"),
                "record_type": "statement",
                "statement_id": comment.get("id"),
                "statement_text": comment.get("text"),
                "statement_status": comment.get("status"),
                "statement_is_seed": bool(comment.get("isSeed", False)),
                "statement_created_at": comment.get("createdAt"),
                "participant_unique_id": "",
                "vote_reaction": "",
                "vote_important": "",
                "vote_created_at": "",
                "discussion_comment_id": "",
                "discussion_comment_text": "",
                "discussion_comment_author_hash": "",
                "discussion_comment_created_at": "",
                "discussion_reaction": "",
                "discussion_reaction_created_at": "",
            }
        )

    # Vote rows (these are reactions to statements).
    for vote in votes:
        statement = comment_lookup.get(vote.get("comment_id")) or {}
        rows.append(
            {
                "conversation_id": convo.get("id"),
                "record_type": "vote_reaction",
                "statement_id": vote.get("comment_id"),
                "statement_text": statement.get("text", ""),
                "statement_status": statement.get("status", ""),
                "statement_is_seed": bool(statement.get("isSeed", False)),
                "statement_created_at": statement.get("createdAt", ""),
                "participant_unique_id": vote.get("participant_id"),
                "vote_reaction": _vote_choice_label(vote.get("choice")),
                "vote_important": bool(vote.get("important", False)),
                "vote_created_at": vote.get("voted_at"),
                "discussion_comment_id": "",
                "discussion_comment_text": "",
                "discussion_comment_author_hash": "",
                "discussion_comment_created_at": "",
                "discussion_reaction": "",
                "discussion_reaction_created_at": "",
            }
        )

    driver = get_driver()
    with _db_session(driver) as session:
        discussion_records = _execute_read(
            session,
            """
            MATCH (c:Conversation {id: $cid})-[:HAS_STATEMENT_COMMENT]->(sc:StatementComment)-[:ON_STATEMENT]->(st:Comment)
            OPTIONAL MATCH (p:Participant)-[r:REACTED_TO]->(sc)
            RETURN
              st.id AS statement_id,
              st.text AS statement_text,
              st.status AS statement_status,
              coalesce(st.isSeed, false) AS statement_is_seed,
              st.createdAt AS statement_created_at,
              sc.id AS discussion_comment_id,
              sc.text AS discussion_comment_text,
              sc.authorHash AS discussion_comment_author_hash,
              sc.createdAt AS discussion_comment_created_at,
              p.id AS participant_unique_id,
              r.reaction AS discussion_reaction,
              coalesce(r.updatedAt, r.createdAt) AS discussion_reaction_created_at
            ORDER BY sc.createdAt ASC
            """,
            {"cid": conversation_id},
        )

    # Discussion rows: one row for each discussion comment reaction; if no reaction,
    # we still output the comment row with empty reaction fields.
    for record in discussion_records:
        rows.append(
            {
                "conversation_id": convo.get("id"),
                "record_type": "discussion_comment_reaction"
                if record.get("discussion_reaction")
                else "discussion_comment",
                "statement_id": record.get("statement_id"),
                "statement_text": record.get("statement_text"),
                "statement_status": record.get("statement_status"),
                "statement_is_seed": bool(record.get("statement_is_seed", False)),
                "statement_created_at": str(record.get("statement_created_at"))
                if record.get("statement_created_at")
                else "",
                "participant_unique_id": record.get("participant_unique_id") or "",
                "vote_reaction": "",
                "vote_important": "",
                "vote_created_at": "",
                "discussion_comment_id": record.get("discussion_comment_id"),
                "discussion_comment_text": record.get("discussion_comment_text"),
                "discussion_comment_author_hash": record.get("discussion_comment_author_hash"),
                "discussion_comment_created_at": str(record.get("discussion_comment_created_at"))
                if record.get("discussion_comment_created_at")
                else "",
                "discussion_reaction": record.get("discussion_reaction") or "",
                "discussion_reaction_created_at": str(record.get("discussion_reaction_created_at"))
                if record.get("discussion_reaction_created_at")
                else "",
            }
        )

    return rows


# ---------------------------------------------------------------------------
# Background job helper
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


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


@router.get("/conversations/{conversation_id}/export.csv")
def export_conversation_flat_csv(conversation_id: str):
    rows = _build_flat_export_rows(conversation_id)
    fieldnames = [
        "conversation_id",
        "record_type",
        "statement_id",
        "statement_text",
        "statement_status",
        "statement_is_seed",
        "statement_created_at",
        "participant_unique_id",
        "vote_reaction",
        "vote_important",
        "vote_created_at",
        "discussion_comment_id",
        "discussion_comment_text",
        "discussion_comment_author_hash",
        "discussion_comment_created_at",
        "discussion_reaction",
        "discussion_reaction_created_at",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    payload = output.getvalue().encode("utf-8")
    filename = f"conversation_{conversation_id}_dataset.csv"
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
