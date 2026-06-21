#!/usr/bin/env python3
"""Import June 2026 Georgian CRM people files into Aura.

Organized workflow:
- inputs:  data/imports/members_2026_06.csv, supporters_2026_06.csv
- outputs: data/import_batches/2026_06_crm_people/*

Rules:
- Valid email is the primary unique key.
- Missing/invalid email receives a stable generated personId based on source row + row content.
- Exact address is stored internally; map display fields use neighborhood-level location data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "React" / "Back end"
APP_ROOT = BACKEND_ROOT / "deliberation" / "api" / "app"
if str(APP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(APP_ROOT.parent))

from app.services.location_service import assign_location_fields  # noqa: E402

INPUT_DIR = ROOT / "data" / "imports"
BATCH_DIR = ROOT / "data" / "import_batches" / "2026_06_crm_people"
MEMBERS_FILE = INPUT_DIR / "members_2026_06.csv"
SUPPORTERS_FILE = INPUT_DIR / "supporters_2026_06.csv"
BATCH_ID = "crm_people_2026_06"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MEMBER_COLS = {
    "joinDate": 2,
    "firstName": 3,
    "lastName": 4,
    "gender": 5,
    "dateOfBirth": 6,
    "phone": 7,
    "email": 8,
    "address": 9,
    "profession": 10,
    "socialMedia": 11,
    "wasPartyMember": 12,
    "partyDetails": 13,
    "about": 14,
    "timeAvailability": 15,
    "topicsOfInterest": 16,
    "involvementAreas": 17,
    "howToHelp": 18,
    "additionalComments": 19,
}

# The supporter file labels columns 2/3 as surname/name, but the observed data is first/last.
SUPPORTER_COLS = {
    "firstName": 2,
    "lastName": 3,
    "dateOfBirth": 4,
    "phone": 5,
    "email": 6,
    "address": 7,
    "profession": 8,
    "socialMedia": 9,
    "wasPartyMember": 10,
    "partyDetails": 11,
    "about": 12,
    "timeAvailability": 13,
    "topicsOfInterest": 14,
    "involvementAreas": 15,
    "howToHelp": 16,
    "additionalComments": 17,
    "agreesWithManifesto": 18,
    "interestedInMembership": 19,
    "personalId": 20,
    "gender": 21,
}


def clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().strip("\ufeff")
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def get(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return clean(row[index])


def split_list(value: str) -> list[str]:
    text = clean(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"[,;\n]", text) if part.strip()]


def parse_bool(value: str) -> bool:
    text = clean(value).lower()
    return text in {"დიახ", "კი", "yes", "true", "1", "თანახმა", "ვეთანხმები"}


def parse_gender(value: str) -> str:
    text = clean(value)
    lower = text.lower()
    if lower in {"female", "f", "ქალი", "მდედრობითი", "1", "1.0"}:
        return "Female"
    if lower in {"male", "m", "კაცი", "მამრობითი", "2", "2.0"}:
        return "Male"
    if lower in {"other", "o", "3", "3.0"}:
        return "Other"
    return text or "Unspecified"


def parse_date(value: str) -> str:
    text = clean(value)
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%Y-%d-%m", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text


def age_from_date(value: str) -> int | None:
    parsed = parse_date(value)
    if not parsed or not re.match(r"^\d{4}-\d{2}-\d{2}$", parsed):
        return None
    dob = datetime.strptime(parsed, "%Y-%m-%d").date()
    today = date.today()
    return max(0, today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day)))


def normalize_email(value: str) -> tuple[str, str]:
    raw = clean(value).lower()
    if not raw or raw in {"-", "_"}:
        return "", raw
    if EMAIL_RE.match(raw):
        return raw, raw
    return "", raw


def phone_digits(phone: str) -> str:
    return re.sub(r"\D", "", clean(phone))


def stable_generated_id(source: str, row_number: int, row_data: dict) -> str:
    basis = "|".join(
        clean(row_data.get(key, ""))
        for key in ("firstName", "lastName", "phone", "dateOfBirth", "address", "rawEmail")
    )
    digest = hashlib.sha1(f"{source}|{row_number}|{basis}".encode("utf-8")).hexdigest()[:14]
    return f"generated:{source}:{row_number}:{digest}"


def read_csv_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return [], []
    return rows[0], rows[1:]

def is_member_summary_footer(row: list[str], cols: dict) -> bool:
    """Skip aggregate rows copied below the member table."""
    join_date = get(row, cols.get("joinDate"))
    first = get(row, cols.get("firstName"))
    last = get(row, cols.get("lastName"))
    email = get(row, cols.get("email"))
    phone = get(row, cols.get("phone"))
    address = get(row, cols.get("address"))
    if any([last, email, phone, address]):
        return False
    if join_date in {"ქალი", "კაცი", "18–35", "18-35", "36–55", "36-55", "55+"}:
        return True
    return bool(re.fullmatch(r"\d+\s*\(\d+%\)", first))


def make_record(source: str, row_number: int, row: list[str], cols: dict, supporter_type: str) -> dict | None:
    email, raw_email = normalize_email(get(row, cols.get("email")))
    first = get(row, cols.get("firstName"))
    last = get(row, cols.get("lastName"))
    phone = get(row, cols.get("phone"))
    address = get(row, cols.get("address"))
    dob = parse_date(get(row, cols.get("dateOfBirth")))

    if not any([email, raw_email, first, last, phone, address, dob]):
        return None
    if source == "members" and is_member_summary_footer(row, cols):
        return None
    if source == "members" and not any([email, phone, first, last, address]) and get(row, cols.get("joinDate")):
        return None

    record = {
        "source": source,
        "sourceRow": row_number,
        "rawEmail": raw_email,
        "email": email,
        "firstName": first,
        "lastName": last,
        "fullName": " ".join(part for part in [first, last] if part),
        "gender": parse_gender(get(row, cols.get("gender"))),
        "age": age_from_date(dob),
        "phone": phone,
        "phoneDigits": phone_digits(phone),
        "address": address,
        "profession": get(row, cols.get("profession")),
        "socialMedia": get(row, cols.get("socialMedia")),
        "wasPartyMember": parse_bool(get(row, cols.get("wasPartyMember"))),
        "partyDetails": get(row, cols.get("partyDetails")),
        "about": get(row, cols.get("about")),
        "timeAvailability": get(row, cols.get("timeAvailability")),
        "topicsOfInterest": split_list(get(row, cols.get("topicsOfInterest"))),
        "skills": split_list(get(row, cols.get("involvementAreas"))),
        "involvementAreas": split_list(get(row, cols.get("involvementAreas"))),
        "howToHelp": get(row, cols.get("howToHelp")),
        "additionalComments": get(row, cols.get("additionalComments")),
        "agreesWithManifesto": True if supporter_type == "Member" else parse_bool(get(row, cols.get("agreesWithManifesto"))),
        "interestedInMembership": True if supporter_type == "Member" else parse_bool(get(row, cols.get("interestedInMembership"))),
        "personalId": get(row, cols.get("personalId")),
        "dateOfBirth": dob,
        "joinDate": get(row, cols.get("joinDate")),
        "supporterType": supporter_type,
        "importBatch": BATCH_ID,
        "idType": "email" if email else "generated",
    }
    record["personId"] = email if email else stable_generated_id(source, row_number, record)

    location = assign_location_fields(record)
    record.update(
        {
            "city": location.get("city", ""),
            "district": location.get("district", ""),
            "area": location.get("area", ""),
            "microArea": location.get("micro_area", ""),
            "neighborhood": location.get("neighborhood", ""),
            "neighborhoodLat": location.get("neighborhood_lat"),
            "neighborhoodLng": location.get("neighborhood_lng"),
            "neighborhoodId": location.get("neighborhood_id", ""),
            "locationPrecision": location.get("location_precision", "unknown"),
            "locationSource": location.get("location_source", ""),
            "locationConfidence": location.get("location_confidence", 0),
            "locationReviewNeeded": bool(location.get("location_review_needed", True)),
            "suggestedLocationMatch": location.get("suggested_match", ""),
        }
    )
    return record


def load_people() -> tuple[list[dict], list[dict]]:
    people = []
    skipped = []
    # Import supporters first and members last. When a valid email appears in both
    # files, the later Member row should be the final classification.
    for source, path, cols, supporter_type in [
        ("supporters", SUPPORTERS_FILE, SUPPORTER_COLS, "Supporter"),
        ("members", MEMBERS_FILE, MEMBER_COLS, "Member"),
    ]:
        _, rows = read_csv_rows(path)
        for index, row in enumerate(rows, start=2):
            record = make_record(source, index, row, cols, supporter_type)
            if record is None:
                skipped.append({"source": source, "sourceRow": index, "reason": "empty_or_section_row"})
                continue
            people.append(record)
    return people, skipped


def write_outputs(people: list[dict], skipped: list[dict]) -> dict:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    preview_path = BATCH_DIR / "normalized_people_preview.csv"
    review_path = BATCH_DIR / "review_needed.csv"
    skipped_path = BATCH_DIR / "skipped_rows.csv"
    summary_path = BATCH_DIR / "summary.json"

    fields = [
        "source", "sourceRow", "personId", "idType", "email", "rawEmail", "firstName", "lastName",
        "phone", "dateOfBirth", "age", "gender", "supporterType", "address", "neighborhood",
        "neighborhoodId", "locationPrecision", "locationConfidence", "locationReviewNeeded",
        "suggestedLocationMatch", "profession", "timeAvailability",
    ]
    with preview_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(people)

    review_rows = [
        p for p in people
        if p["idType"] == "generated" or p["rawEmail"] and not p["email"] or p["locationReviewNeeded"]
    ]
    with review_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(review_rows)

    with skipped_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source", "sourceRow", "reason"])
        writer.writeheader()
        writer.writerows(skipped)

    email_counts = Counter(p["email"] for p in people if p["email"])
    summary = {
        "batchId": BATCH_ID,
        "totalPreparedRows": len(people),
        "membersPrepared": sum(1 for p in people if p["supporterType"] == "Member"),
        "supportersPrepared": sum(1 for p in people if p["supporterType"] == "Supporter"),
        "validEmailRows": sum(1 for p in people if p["idType"] == "email"),
        "generatedIdRows": sum(1 for p in people if p["idType"] == "generated"),
        "invalidRawEmailRows": sum(1 for p in people if p["rawEmail"] and not p["email"]),
        "duplicateValidEmails": sorted([email for email, count in email_counts.items() if count > 1]),
        "locationReviewRows": sum(1 for p in people if p["locationReviewNeeded"]),
        "skippedRows": len(skipped),
        "outputs": {
            "preview": str(preview_path),
            "review": str(review_path),
            "skipped": str(skipped_path),
        },
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def load_env() -> None:
    load_dotenv(BACKEND_ROOT / ".env")


def get_backend_connection():
    from app.db import get_active_database, get_driver

    return get_driver(), get_active_database()


def import_people(people: list[dict]) -> dict:
    driver, database = get_backend_connection()
    query = """
    UNWIND $rows AS row
    OPTIONAL MATCH (candidate:Person)
    WHERE candidate.personId = row.personId OR (row.email <> '' AND toLower(candidate.email) = row.email)
    WITH row, collect(candidate)[0] AS existing
    CALL (row, existing) {
      WITH row WHERE existing IS NULL
      CREATE (p:Person {personId: row.personId})
      SET p.createdAt = datetime()
      RETURN p
      UNION
      WITH existing AS p WHERE p IS NOT NULL
      RETURN p
    }
    SET p.personId = coalesce(p.personId, row.personId),
        p.importBatch = row.importBatch,
        p.importSource = row.source,
        p.importSourceRow = row.sourceRow,
        p.importIdType = row.idType,
        p.email = CASE WHEN row.email = '' THEN p.email ELSE row.email END,
        p.rawEmail = row.rawEmail,
        p.generatedId = CASE WHEN row.idType = 'generated' THEN row.personId ELSE p.generatedId END,
        p.firstName = row.firstName,
        p.lastName = row.lastName,
        p.fullName = row.fullName,
        p.gender = row.gender,
        p.age = row.age,
        p.phone = row.phone,
        p.phoneDigits = row.phoneDigits,
        p.address = row.address,
        p.profession = row.profession,
        p.socialMedia = row.socialMedia,
        p.wasPartyMember = row.wasPartyMember,
        p.partyDetails = row.partyDetails,
        p.about = row.about,
        p.timeAvailability = row.timeAvailability,
        p.howToHelp = row.howToHelp,
        p.additionalComments = row.additionalComments,
        p.agreesWithManifesto = row.agreesWithManifesto,
        p.interestedInMembership = row.interestedInMembership,
        p.personalId = row.personalId,
        p.dateOfBirth = row.dateOfBirth,
        p.joinDate = row.joinDate,
        p.supporterType = row.supporterType,
        p.city = row.city,
        p.district = row.district,
        p.area = row.area,
        p.micro_area = row.microArea,
        p.neighborhood = row.neighborhood,
        p.neighbourhood = row.neighborhood,
        p.neighborhood_lat = row.neighborhoodLat,
        p.neighborhood_lng = row.neighborhoodLng,
        p.neighborhood_id = row.neighborhoodId,
        p.location_precision = row.locationPrecision,
        p.location_source = row.locationSource,
        p.location_confidence = row.locationConfidence,
        p.location_review_needed = row.locationReviewNeeded,
        p.suggested_location_match = row.suggestedLocationMatch,
        p.updatedAt = datetime()
    WITH p, row
    OPTIONAL MATCH (p)-[oldAddress:LIVES_AT]->(:Address)
    DELETE oldAddress
    WITH p, row
    FOREACH (_ IN CASE WHEN row.address = '' THEN [] ELSE [1] END |
      MERGE (a:Address {fullAddress: row.address})
      SET a.city = row.city,
          a.district = row.district,
          a.area = row.area,
          a.micro_area = row.microArea,
          a.neighborhood = row.neighborhood,
          a.neighborhood_lat = row.neighborhoodLat,
          a.neighborhood_lng = row.neighborhoodLng
      MERGE (p)-[:LIVES_AT]->(a)
    )
    WITH p, row
    OPTIONAL MATCH (p)-[oldSupporter:CLASSIFIED_AS]->(:SupporterType {name: 'Supporter'})
    FOREACH (_ IN CASE WHEN row.supporterType = 'Member' AND oldSupporter IS NOT NULL THEN [1] ELSE [] END | DELETE oldSupporter)
    WITH p, row
    MERGE (st:SupporterType {name: row.supporterType})
    MERGE (p)-[:CLASSIFIED_AS]->(st)
    WITH p, row
    FOREACH (topic IN coalesce(row.topicsOfInterest, []) |
      MERGE (t:Topic {name: topic})
      MERGE (p)-[:INTERESTED_IN]->(t)
    )
    FOREACH (skill IN coalesce(row.skills, []) |
      MERGE (ia:InvolvementArea {name: skill})
      MERGE (p)-[:WANTS_TO_HELP_WITH]->(ia)
    )
    RETURN count(DISTINCT p) AS touched
    """
    batch_size = 75
    with driver:
        with driver.session(database=database) as session:
            for start in range(0, len(people), batch_size):
                batch = people[start:start + batch_size]
                session.run(query, rows=batch).consume()
                print(f"Imported batch {start // batch_size + 1}: {len(batch)} rows")
            verified = session.run(
                """
                MATCH (p:Person)
                WHERE p.importBatch = $batchId
                OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(st:SupporterType)
                WITH collect(DISTINCT p) AS people,
                     count(DISTINCT CASE WHEN st.name = 'Member' THEN p END) AS members,
                     count(DISTINCT CASE WHEN st.name = 'Supporter' THEN p END) AS supporters
                RETURN size(people) AS distinctImportedPeople,
                       members AS verifiedMembers,
                       supporters AS verifiedSupporters
                """,
                batchId=BATCH_ID,
            ).single()
    return {
        "processedRows": len(people),
        "distinctImportedPeople": int(verified["distinctImportedPeople"]),
        "verifiedMembers": int(verified["verifiedMembers"]),
        "verifiedSupporters": int(verified["verifiedSupporters"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write rows to Aura. Without this, only preview files are generated.")
    args = parser.parse_args()

    load_env()
    people, skipped = load_people()
    summary = write_outputs(people, skipped)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if not args.apply:
        print("Dry run complete. Re-run with --apply to update Aura.")
        return 0

    result = import_people(people)
    applied_summary = {**summary, **result, "appliedAt": datetime.now().isoformat(timespec="seconds")}
    (BATCH_DIR / "summary_applied.json").write_text(
        json.dumps(applied_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(applied_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())







