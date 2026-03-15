import argparse
import csv
import os
import random
import uuid

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(
    dotenv_path=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")),
    override=True,
)


def get_comments(conversation_id: str):
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "change-this")
    neo4j_database = os.getenv("NEO4J_DATABASE", "neo4j")

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    try:
        with driver.session(database=neo4j_database) as session:
            records = session.run(
                """
                MATCH (c:Conversation {id: $cid})-[:HAS_COMMENT]->(cm:Comment)
                RETURN cm.id AS id, cm.text AS text
                ORDER BY cm.createdAt, cm.id
                """,
                {"cid": conversation_id},
            )
            comments = [record.data() for record in records]
    finally:
        driver.close()
    return comments


def pick_choice(group: int, bucket: int) -> int:
    roll = random.random()
    if group == 0:
        if bucket == 0:
            return 1 if roll < 0.7 else -1
        if bucket == 1:
            return -1 if roll < 0.7 else 1
        return 0 if roll < 0.6 else 1
    if group == 1:
        if bucket == 0:
            return -1 if roll < 0.7 else 1
        if bucket == 1:
            return 1 if roll < 0.7 else -1
        return 0 if roll < 0.6 else -1
    if roll < 0.4:
        return 1
    if roll < 0.8:
        return -1
    return 0


def main():
    parser = argparse.ArgumentParser(description="Generate simulated votes CSV.")
    parser.add_argument("--conversation-id", required=True, help="Conversation id")
    parser.add_argument("--participants", type=int, default=120, help="Number of participants")
    parser.add_argument("--votes-per", type=int, default=20, help="Votes per participant")
    parser.add_argument("--output", default="georgian_politics_votes.csv", help="Output CSV path")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    random.seed(args.seed)
    comments = get_comments(args.conversation_id)
    if not comments:
        raise SystemExit("No comments found for conversation.")

    comment_ids = [comment["id"] for comment in comments]
    votes_per = min(args.votes_per, len(comment_ids))

    rows = []
    for _ in range(args.participants):
        participant_id = str(uuid.uuid4())
        group_roll = random.random()
        group = 0 if group_roll < 0.4 else 1 if group_roll < 0.8 else 2
        selected = random.sample(comment_ids, votes_per)
        for comment_id in selected:
            bucket = comment_ids.index(comment_id) % 3
            choice = pick_choice(group, bucket)
            rows.append(
                {
                    "conversation_id": args.conversation_id,
                    "participant_id": participant_id,
                    "comment_id": comment_id,
                    "choice": choice,
                }
            )

    with open(args.output, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=["conversation_id", "participant_id", "comment_id", "choice"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} votes to {args.output}")


if __name__ == "__main__":
    main()
