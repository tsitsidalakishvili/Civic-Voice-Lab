import argparse
import csv
import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(
    dotenv_path=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")),
    override=True,
)


def main():
    parser = argparse.ArgumentParser(description="Import votes CSV into Neo4j.")
    parser.add_argument("--csv", default="georgian_politics_votes.csv", help="CSV file path")
    args = parser.parse_args()

    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "change-this")
    neo4j_database = os.getenv("NEO4J_DATABASE", "neo4j")

    votes = []
    with open(args.csv, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            votes.append(
                {
                    "conversation_id": row["conversation_id"],
                    "participant_id": row["participant_id"],
                    "comment_id": row["comment_id"],
                    "choice": int(row["choice"]),
                }
            )

    if not votes:
        raise SystemExit("No votes found to import.")

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    try:
        with driver.session(database=neo4j_database) as session:
            result = session.run(
                """
                UNWIND $votes AS v
                MATCH (c:Conversation {id: v.conversation_id})-[:HAS_COMMENT]->(cm:Comment {id: v.comment_id})
                MERGE (p:Participant {id: v.participant_id})
                ON CREATE SET p.createdAt = datetime()
                MERGE (p)-[:PARTICIPATED_IN]->(c)
                MERGE (p)-[r:VOTED]->(cm)
                SET r.choice = v.choice,
                    r.votedAt = datetime()
                RETURN count(r) AS created
                """,
                {"votes": votes},
            )
            created = result.single()["created"]
    finally:
        driver.close()

    print(f"Imported {created} votes from {args.csv}")


if __name__ == "__main__":
    main()
