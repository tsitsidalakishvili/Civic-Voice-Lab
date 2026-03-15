from __future__ import annotations

import csv
from pathlib import Path

from fastapi import HTTPException

from app.db import db_health
from app.routes import create_conversation, import_conversation_dataset
from app.routes_crm import (
    EventCreate,
    EventCreateWithPeopleRequest,
    PeopleBulkImport,
    PersonImportRow,
    SegmentCreate,
    SegmentFilter,
    TaskCreate,
    WhatsAppGroupCreate,
    bulk_upsert_people,
    create_event_for_people,
    create_segment,
    create_task,
    upsert_whatsapp_group,
)
from app.routes_due_diligence import CompetitorCreate, upsert_competitor
from app.schemas import (
    ConversationCreate,
    ConversationDatasetImportRequest,
    ConversationDatasetImportRow,
)


def _find_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "React").exists() and (parent / "Streamlit").exists():
            return parent
    return current.parents[4]


def _read_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [row for row in reader if any(str(v or "").strip() for v in row.values())]


def _to_int(value):
    try:
        text = str(value).strip()
        return int(float(text)) if text else None
    except Exception:
        return None


def _to_float(value):
    try:
        text = str(value).strip()
        return float(text) if text else None
    except Exception:
        return None


def _split_list(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def seed_people(repo_root: Path) -> list[dict]:
    csv_path = repo_root / "React" / "Front end" / "public" / "data" / "simulated_crm_people.csv"
    rows = _read_csv_rows(csv_path)
    payload_rows = []
    for row in rows:
        payload_rows.append(
            PersonImportRow(
                email=str(row.get("email") or "").strip(),
                firstName=str(row.get("first_name") or "").strip(),
                lastName=str(row.get("last_name") or "").strip(),
                gender=str(row.get("gender") or "").strip() or None,
                age=_to_int(row.get("age")),
                phone=str(row.get("phone") or "").strip() or None,
                address=str(row.get("address") or "").strip() or None,
                lat=_to_float(row.get("lat")),
                lon=_to_float(row.get("lon")),
                effortHours=_to_float(row.get("effort_hours")),
                eventsAttendedCount=_to_int(row.get("events_attended")),
                referralCount=_to_int(row.get("referral_count")),
                tasksCompleted=_to_int(row.get("tasks_completed")),
                education=str(row.get("education") or "").strip() or None,
                skills=_split_list(row.get("skills")),
                supporterType=str(row.get("supporter_type") or "").strip() or "Supporter",
                timeAvailability=str(row.get("time_availability") or "").strip() or None,
            )
        )
    result = bulk_upsert_people(PeopleBulkImport(rows=payload_rows, defaultType="Supporter"))
    print(f"Seeded people: {result.get('created')}")
    return rows


def seed_segments() -> None:
    create_segment(
        SegmentCreate(
            name="High effort supporters",
            description="Supporters with effort > 20 hours",
            filterSpec=SegmentFilter(group="Supporter", minEffortHours=20),
        )
    )
    create_segment(
        SegmentCreate(
            name="Weekend volunteers",
            description="Members or supporters available on weekends",
            filterSpec=SegmentFilter(timeAvailability=["Weekend"]),
        )
    )
    print("Seeded segments.")


def seed_whatsapp_groups() -> None:
    upsert_whatsapp_group(
        WhatsAppGroupCreate(
            name="FS Outreach",
            inviteLink="https://chat.whatsapp.com/demo-fs-outreach",
            notes="Demo outreach group",
        )
    )
    upsert_whatsapp_group(
        WhatsAppGroupCreate(
            name="FS Events",
            inviteLink="https://chat.whatsapp.com/demo-fs-events",
            notes="Demo events group",
        )
    )
    print("Seeded WhatsApp groups.")


def seed_tasks(people_rows: list[dict]) -> None:
    for idx, row in enumerate(people_rows[:6]):
        create_task(
            TaskCreate(
                email=str(row.get("email") or "").strip(),
                title=f"Follow up #{idx + 1}",
                description="Demo task from seed script.",
                dueDate="2026-03-20",
                status="Open" if idx % 2 == 0 else "In Progress",
            )
        )
    print("Seeded tasks.")


def seed_event_with_people(people_rows: list[dict]) -> None:
    event = EventCreate(
        name="Freedom Square Townhall",
        startDate="2026-03-22",
        endDate="2026-03-22",
        location="Freedom Square, Tbilisi",
        status="Scheduled",
        capacity=200,
        notes="Demo event generated for React app.",
    )
    rows = []
    for row in people_rows[:10]:
        rows.append(
            {
                "email": row.get("email"),
                "firstName": row.get("first_name"),
                "lastName": row.get("last_name"),
                "phone": row.get("phone"),
                "group": row.get("supporter_type"),
            }
        )
    create_event_for_people(EventCreateWithPeopleRequest(event=event, rows=rows))
    print("Seeded event + registrations.")


def seed_competitors(repo_root: Path) -> None:
    csv_path = repo_root / "React" / "Front end" / "public" / "data" / "due_diligence_watchlist_simulated.csv"
    rows = _read_csv_rows(csv_path)
    for row in rows:
        upsert_competitor(
            CompetitorCreate(
                name=str(row.get("name") or "").strip(),
                competitorType=str(row.get("competitor_type") or "Person").strip(),
                notes=str(row.get("notes") or "").strip(),
            )
        )
    print("Seeded competitors.")


def seed_deliberation(repo_root: Path) -> None:
    convo = create_conversation(
        ConversationCreate(
            topic="Demo deliberation: City services",
            description="Sample dataset for demo votes and analysis.",
            is_open=True,
            allow_comment_submission=True,
            allow_viz=True,
            moderation_required=False,
        )
    )
    convo_id = convo.get("id") if isinstance(convo, dict) else None
    if not convo_id:
        print("Conversation was not created; skipping deliberation seed.")
        return

    csv_path = repo_root / "React" / "Front end" / "public" / "data" / "simulated_deliberation_dataset.csv"
    rows = _read_csv_rows(csv_path)
    payload_rows = []
    for row in rows:
        payload_rows.append(
            ConversationDatasetImportRow(
                conversation_id=convo_id,
                participant_id=row.get("participant_id"),
                participant_cluster=row.get("participant_cluster"),
                comment_id=row.get("comment_id"),
                comment_text=row.get("comment_text"),
                is_seed=row.get("is_seed"),
                comment_created_at=row.get("comment_created_at"),
                vote=row.get("vote"),
                reaction_created_at=row.get("reaction_created_at"),
            )
        )
    import_conversation_dataset(convo_id, ConversationDatasetImportRequest(rows=payload_rows))
    print(f"Seeded deliberation conversation: {convo_id}")


def main() -> None:
    status = db_health()
    if not status.get("ok"):
        raise RuntimeError(f"Neo4j connection failed: {status}")

    repo_root = _find_repo_root()
    print(f"Using repo root: {repo_root}")

    people_rows = seed_people(repo_root)
    seed_segments()
    seed_whatsapp_groups()
    seed_tasks(people_rows)
    seed_event_with_people(people_rows)
    seed_competitors(repo_root)
    seed_deliberation(repo_root)
    print("Demo seed complete.")


if __name__ == "__main__":
    try:
        main()
    except HTTPException as exc:
        raise SystemExit(f"Seed failed: {exc.detail}") from exc
