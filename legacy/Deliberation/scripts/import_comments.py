import argparse
import csv
import os
import uuid

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(
    dotenv_path=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")),
    override=True,
)


def parse_bool(value: str) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y"}


def normalize_status(raw_status: str, is_seed: bool) -> str:
    status = (raw_status or "").strip().lower()
    if status in {"pending", "approved", "rejected"}:
        return status
    return "approved" if is_seed else "pending"


def load_comments(csv_path: str):
    comments = []
    with open(csv_path, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            text = (row.get("comment_text") or "").strip()
            if not text:
                continue
            is_seed = parse_bool(row.get("is_seed", "false"))
            status = normalize_status(row.get("status"), is_seed)
            comments.append(
                {
                    "id": str(uuid.uuid4()),
                    "text": text,
                    "status": status,
                    "is_seed": is_seed,
                    "author_hash": "seed" if is_seed else "import",
                }
            )
    return comments


def main():
    parser = argparse.ArgumentParser(description="Import comments into Neo4j.")
    parser.add_argument("--csv", default="georgian_politics_comments.csv", help="CSV file path")
    parser.add_argument("--topic", default="Georgian Politics Deliberation", help="Conversation topic")
    parser.add_argument("--description", default="Seeded from CSV import", help="Conversation description")
    parser.add_argument("--conversation-id", default=None, help="Use existing conversation id")
    args = parser.parse_args()

    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "change-this")
    neo4j_database = os.getenv("NEO4J_DATABASE", "neo4j")

    comments = load_comments(args.csv)
    if not comments:
        raise SystemExit("No comments found to import.")

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    try:
        with driver.session(database=neo4j_database) as session:
            if args.conversation_id:
                convo_id = args.conversation_id
                record = session.run(
                    "MATCH (c:Conversation {id: $id}) RETURN c",
                    {"id": convo_id},
                ).single()
                if record is None:
                    session.run(
                        """
                        CREATE (c:Conversation {
                            id: $id,
                            topic: $topic,
                            description: $description,
                            isOpen: true,
                            allowCommentSubmission: true,
                            allowViz: true,
                            moderationRequired: false,
                            createdAt: datetime()
                        })
                        """,
                        {
                            "id": convo_id,
                            "topic": args.topic,
                            "description": args.description,
                        },
                    )
            else:
                convo_id = str(uuid.uuid4())
                session.run(
                    """
                    CREATE (c:Conversation {
                        id: $id,
                        topic: $topic,
                        description: $description,
                        isOpen: true,
                        allowCommentSubmission: true,
                        allowViz: true,
                        moderationRequired: false,
                        createdAt: datetime()
                    })
                    """,
                    {"id": convo_id, "topic": args.topic, "description": args.description},
                )

            result = session.run(
                """
                MATCH (c:Conversation {id: $cid})
                UNWIND $comments AS cm
                CREATE (comment:Comment {
                    id: cm.id,
                    text: cm.text,
                    status: cm.status,
                    isSeed: cm.is_seed,
                    authorHash: cm.author_hash,
                    createdAt: datetime()
                })
                CREATE (c)-[:HAS_COMMENT]->(comment)
                RETURN count(comment) AS created
                """,
                {"cid": convo_id, "comments": comments},
            )
            created = result.single()["created"]
    finally:
        driver.close()

    print(f"Imported {created} comments into conversation {convo_id}")


if __name__ == "__main__":
    main()
