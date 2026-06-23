"""Recalculate sentiment fields for statement discussion comments.

Usage:
  python -m app.scripts.backfill_statement_sentiment
  python -m app.scripts.backfill_statement_sentiment --apply
  python -m app.scripts.backfill_statement_sentiment --conversation-id <id> --apply
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from app.core.env import load_backend_env

load_backend_env(Path(__file__).resolve().parents[2])

from app.db import get_active_database, get_driver
from app.services.sentiment_service import score_sentiment


def _fetch_comments(session, conversation_id: str | None) -> list[dict]:
    where = "WHERE $conversation_id IS NULL OR sc.conversationId = $conversation_id"
    query = f"""
    MATCH (sc:StatementComment)
    {where}
    RETURN
      sc.id AS id,
      sc.conversationId AS conversation_id,
      sc.text AS text,
      sc.sentimentScore AS old_score,
      sc.sentimentLabel AS old_label
    ORDER BY sc.createdAt DESC
    """
    return [record.data() for record in session.run(query, {"conversation_id": conversation_id})]


def _apply_updates(session, rows: list[dict]) -> int:
    if not rows:
        return 0
    result = session.run(
        """
        UNWIND $rows AS row
        MATCH (sc:StatementComment {id: row.id})
        SET sc.sentimentScore = row.score,
            sc.sentimentLabel = row.label,
            sc.sentimentConfidence = row.confidence,
            sc.sentimentProvider = row.provider,
            sc.sentimentProcessedText = row.processed_text,
            sc.sentimentUpdatedAt = datetime()
        RETURN count(sc) AS updated
        """,
        {"rows": rows},
    ).single()
    return int(result["updated"] if result else 0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--conversation-id", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-unavailable", action="store_true")
    args = parser.parse_args()

    driver = get_driver()
    database = get_active_database()
    with driver.session(database=database) as session:
        comments = _fetch_comments(session, args.conversation_id)
        updates = []
        changed = []
        for comment in comments:
            sentiment = score_sentiment(comment.get("text") or "")
            provider_unavailable = (
                sentiment.provider == "unavailable"
                or sentiment.provider.startswith("transformer-load-failed")
                or sentiment.provider == "model-not-configured"
                or sentiment.provider == "transformer-disabled-on-windows"
            )
            if provider_unavailable and not args.allow_unavailable:
                continue
            row = {
                "id": comment.get("id"),
                "conversation_id": comment.get("conversation_id"),
                "text": comment.get("text") or "",
                **asdict(sentiment),
                "old_score": comment.get("old_score"),
                "old_label": comment.get("old_label"),
            }
            if row["id"] and (
                row["old_label"] != row["label"]
                or round(float(row["old_score"] or 0), 3) != row["score"]
            ):
                updates.append({
                    "id": row["id"],
                    "score": row["score"],
                    "label": row["label"],
                    "confidence": row["confidence"],
                    "provider": row["provider"],
                    "processed_text": row["processed_text"],
                })
                changed.append(row)

        updated = _apply_updates(session, updates) if args.apply else 0

    print(f"Database: {database}")
    print(f"Comments scanned: {len(comments)}")
    print(f"Comments needing update: {len(updates)}")
    print(f"Comments updated: {updated}")
    for row in changed[:20]:
        text = row["text"].replace("\n", " ")[:90]
        print(
            f"- {row['id']}: {row['old_label']}:{row['old_score']} -> "
            f"{row['label']}:{row['score']} | {text}"
        )
    if len(changed) > 20:
        print(f"... {len(changed) - 20} more")


if __name__ == "__main__":
    main()

