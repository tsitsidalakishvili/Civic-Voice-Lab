from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV = ROOT / "data" / "demo" / "generated" / "demo_people.csv"


def env(name: str, fallback: str = "") -> str:
    return os.getenv(name, fallback).strip()


def load_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_bool(value: str) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def parse_int(value: str, default: int = 0) -> int:
    try:
        return int(float(str(value or "").strip()))
    except ValueError:
        return default


def parse_float(value: str, default: float = 0.0) -> float:
    try:
        return float(str(value or "").strip())
    except ValueError:
        return default


def normalize_row(row: dict) -> dict:
    skills = [item.strip() for item in str(row.get("skills") or "").split(",") if item.strip()]
    return {
        "personId": row.get("personId"),
        "email": row.get("email"),
        "rawEmail": row.get("rawEmail"),
        "firstName": row.get("firstName"),
        "lastName": row.get("lastName"),
        "fullName": row.get("fullName"),
        "phone": row.get("phone"),
        "age": parse_int(row.get("age")),
        "gender": row.get("gender") or "Unspecified",
        "supporterType": row.get("supporterType") or "Supporter",
        "address": row.get("address"),
        "city": row.get("neighborhood"),
        "neighborhood": row.get("neighborhood"),
        "neighborhood_id": row.get("neighborhoodId"),
        "location_precision": row.get("locationPrecision"),
        "location_confidence": parse_float(row.get("locationConfidence"), 0.0),
        "location_review_needed": parse_bool(row.get("locationReviewNeeded")),
        "profession": row.get("profession"),
        "timeAvailability": row.get("timeAvailability") or "Flexible/unspecified",
        "skills": skills,
        "agreesWithManifesto": parse_bool(row.get("agreesWithManifesto")),
        "interestedInMembership": parse_bool(row.get("interestedInMembership")),
        "importSource": "demo_seed",
    }


def seed(rows: list[dict], apply: bool) -> None:
    if not apply:
        print(f"Dry run: {len(rows)} demo people ready. Use --apply to write to the configured demo database.")
        return
    uri = env("NEO4J_URI") or env("DELIBERATION_NEO4J_URI")
    user = env("NEO4J_USER") or env("DELIBERATION_NEO4J_USER") or "neo4j"
    password = env("NEO4J_PASSWORD") or env("DELIBERATION_NEO4J_PASSWORD")
    database = env("NEO4J_DATABASE") or env("DELIBERATION_NEO4J_DATABASE") or None
    if not uri or not password:
        raise SystemExit("Set demo NEO4J_URI/NEO4J_PASSWORD before using --apply.")
    query = """
    UNWIND $rows AS row
    MERGE (p:Person {personId: row.personId})
    SET p += row,
        p.updatedAt = datetime(),
        p.createdAt = coalesce(p.createdAt, datetime())
    FOREACH (_ IN CASE WHEN row.supporterType = 'Member' THEN [1] ELSE [] END |
      MERGE (m:Member {personId: row.personId})
      MERGE (p)-[:IS_MEMBER]->(m)
    )
    FOREACH (_ IN CASE WHEN row.supporterType <> 'Member' THEN [1] ELSE [] END |
      MERGE (s:Supporter {personId: row.personId})
      MERGE (p)-[:IS_SUPPORTER]->(s)
    )
    FOREACH (skillName IN row.skills |
      MERGE (skill:InvolvementArea {name: skillName})
      MERGE (p)-[:WANTS_TO_HELP_WITH]->(skill)
    )
    RETURN count(p) AS people
    """
    normalized = [normalize_row(row) for row in rows]
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database) as session:
            result = session.run(query, rows=normalized).single()
        print(f"Seeded {result['people'] if result else len(normalized)} demo people.")
    finally:
        driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed mock CRM people into a separate demo Neo4j database.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--apply", action="store_true", help="Write to the configured database. Defaults to dry-run.")
    args = parser.parse_args()
    rows = load_rows(args.csv)
    seed(rows, args.apply)


if __name__ == "__main__":
    main()
