#!/usr/bin/env python3
"""Remove legacy CRM Person nodes after importing the current source-of-truth people batch.

This keeps Aura aligned with the latest CSV files and prevents old CRM people from
being counted beside the current import.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "React" / "Back end"
API_ROOT = BACKEND_ROOT / "deliberation" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

BATCH_ID = "crm_people_2026_06"
BATCH_DIR = ROOT / "data" / "import_batches" / "2026_06_crm_people"


def load_connection():
    load_dotenv(BACKEND_ROOT / ".env")
    from app.db import get_active_database, get_driver

    return get_driver(), get_active_database()


def summarize(session) -> dict:
    current = session.run(
        """
        MATCH (p:Person)
        WHERE p.importBatch = $batchId
        OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(st:SupporterType)
        RETURN count(DISTINCT p) AS currentPeople,
               count(DISTINCT CASE WHEN st.name = 'Member' THEN p END) AS members,
               count(DISTINCT CASE WHEN st.name = 'Supporter' THEN p END) AS supporters
        """,
        batchId=BATCH_ID,
    ).single()
    legacy = session.run(
        """
        MATCH (p:Person)
        WHERE coalesce(p.importBatch, '') <> $batchId
        OPTIONAL MATCH (p)-[r]-()
        RETURN count(DISTINCT p) AS legacyPeople, count(r) AS legacyRelationships
        """,
        batchId=BATCH_ID,
    ).single()
    return {
        "batchId": BATCH_ID,
        "currentPeople": int(current["currentPeople"]),
        "members": int(current["members"]),
        "supporters": int(current["supporters"]),
        "legacyPeople": int(legacy["legacyPeople"]),
        "legacyRelationships": int(legacy["legacyRelationships"]),
    }


def cleanup(session) -> dict:
    result = session.run(
        """
        MATCH (p:Person)
        WHERE coalesce(p.importBatch, '') <> $batchId
        WITH collect(p) AS legacyPeople, count(p) AS deletedPeople
        UNWIND legacyPeople AS p
        DETACH DELETE p
        RETURN deletedPeople
        """,
        batchId=BATCH_ID,
    ).single()

    orphan_summary = session.run(
        """
        MATCH (a:Address)
        WHERE NOT (()-[:LIVES_AT]->(a))
        WITH collect(a) AS orphanAddresses
        WITH orphanAddresses, size(orphanAddresses) AS deletedAddresses
        FOREACH (a IN orphanAddresses | DELETE a)
        RETURN deletedAddresses
        """
    ).single()

    return {
        "deletedLegacyPeople": int(result["deletedPeople"]),
        "deletedOrphanAddresses": int(orphan_summary["deletedAddresses"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Delete legacy people. Without this, only prints a preview.")
    args = parser.parse_args()

    driver, database = load_connection()
    with driver:
        with driver.session(database=database) as session:
            before = summarize(session)
            output = {"before": before, "applied": False}
            if args.apply:
                deleted = cleanup(session)
                after = summarize(session)
                output.update({
                    "applied": True,
                    "deleted": deleted,
                    "after": after,
                    "appliedAt": datetime.now().isoformat(timespec="seconds"),
                })
            else:
                output["message"] = "Dry run only. Re-run with --apply to remove legacy CRM people."

    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    output_path = BATCH_DIR / ("replace_legacy_people_applied.json" if args.apply else "replace_legacy_people_preview.json")
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

