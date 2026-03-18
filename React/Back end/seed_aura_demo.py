from __future__ import annotations

import csv
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv
import requests

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv(dotenv_path=ROOT_DIR / ".env", override=True)

from deliberation.api.app.db import db_health  # noqa: E402
from deliberation.api.app.routes import (  # noqa: E402
    create_conversation,
    import_conversation_dataset,
)
from deliberation.api.app.routes_crm import (  # noqa: E402
    EventCreate,
    EventCreateWithPeopleRequest,
    PeopleBulkImport,
    PersonImportRow,
    TaskCreate,
    bulk_upsert_people,
    create_event_for_people,
    create_task,
)
from deliberation.api.app.routes_due_diligence import (  # noqa: E402
    CompetitorCreate,
    DebatePrepRequest,
    DueDiligenceAnalysisRequest,
    analyze_due_diligence,
    debate_prep,
    upsert_competitor,
)
from deliberation.api.app.schemas import (  # noqa: E402
    ConversationCreate,
    ConversationDatasetImportRequest,
    ConversationDatasetImportRow,
)

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
GOOGLE_MAPS_GEOCODE_URL = os.getenv(
    "GOOGLE_MAPS_GEOCODE_URL", "https://maps.googleapis.com/maps/api/geocode/json"
).strip()
CRM_GEOCODE_CITY_HINT = os.getenv("CRM_GEOCODE_CITY_HINT", "Tbilisi, Georgia").strip()


def _find_repo_root() -> Path:
    for parent in ROOT_DIR.parents:
        if (parent / "React").exists() and (parent / "data").exists():
            return parent
    return ROOT_DIR


def _load_addresses() -> list[str]:
    repo_root = _find_repo_root()
    csv_path = repo_root / "data" / "furry_friends" / "dogs_cats_dataset_with_addresses.csv"
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [row.get("address", "").strip() for row in reader if row.get("address")]


def _normalize_geocode_address(address: str) -> str | None:
    cleaned = str(address or "").strip()
    if not cleaned:
        return None
    if CRM_GEOCODE_CITY_HINT and CRM_GEOCODE_CITY_HINT.lower() not in cleaned.lower():
        return f"{cleaned}, {CRM_GEOCODE_CITY_HINT}"
    return cleaned


@lru_cache(maxsize=1024)
def _geocode_address(address: str) -> tuple[float, float] | None:
    if not GOOGLE_MAPS_API_KEY:
        return None
    query = _normalize_geocode_address(address)
    if not query:
        return None
    try:
        response = requests.get(
            GOOGLE_MAPS_GEOCODE_URL,
            params={"address": query, "key": GOOGLE_MAPS_API_KEY},
            timeout=4,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None
    payload = response.json()
    if payload.get("status") != "OK":
        return None
    results = payload.get("results") or []
    if not results:
        return None
    location = (results[0].get("geometry") or {}).get("location") or {}
    lat = location.get("lat")
    lon = location.get("lng")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def _coords_from_address(address: str) -> tuple[float, float]:
    geocoded = _geocode_address(address)
    if geocoded:
        return round(geocoded[0], 6), round(geocoded[1], 6)
    base_lat, base_lon = 41.7151, 44.8271
    seed = abs(hash(address)) % 10000
    rng = random.Random(seed)
    lat = base_lat + rng.uniform(-0.04, 0.04)
    lon = base_lon + rng.uniform(-0.05, 0.05)
    return round(lat, 6), round(lon, 6)


def seed_people(count: int = 500) -> list[dict]:
    addresses = _load_addresses()
    if not addresses:
        raise RuntimeError("No addresses found in dogs_cats_dataset_with_addresses.csv")

    random.seed(41)
    first_names = [
        "Ana",
        "Giorgi",
        "Mariam",
        "Nino",
        "Irakli",
        "Salome",
        "Luka",
        "Tamari",
        "Levan",
        "Elene",
        "Vazha",
        "Keti",
    ]
    last_names = [
        "Beridze",
        "Kiknadze",
        "Gelashvili",
        "Tsiklauri",
        "Kapanadze",
        "Petriashvili",
        "Giorgadze",
        "Kobakhidze",
        "Chikovani",
        "Natsvlishvili",
        "Javakhishvili",
        "Lomidze",
    ]
    skills = [
        "Organizing",
        "Community Outreach",
        "Policy Research",
        "Fundraising",
        "Event Planning",
        "Public Speaking",
        "Social Media",
        "Volunteer Coordination",
        "Data Analysis",
        "Legal",
        "Design",
        "Field Canvassing",
    ]
    educations = ["High School", "Bachelor", "Master", "PhD"]
    time_availability = [
        "1-3 hrs/week",
        "Weekday evenings",
        "Weekend",
        "Flexible",
    ]

    rows = []
    for idx in range(1, count + 1):
        address = addresses[idx % len(addresses)]
        lat, lon = _coords_from_address(address)
        first = random.choice(first_names)
        last = random.choice(last_names)
        email = f"{first}.{last}.{idx}@demo.org".lower()
        row = PersonImportRow(
            email=email,
            firstName=first,
            lastName=last,
            gender=random.choice(["Female", "Male"]),
            age=random.randint(18, 72),
            phone=f"9955{10000000 + idx:08d}",
            address=address,
            lat=lat,
            lon=lon,
            effortHours=round(random.uniform(4, 28), 1),
            eventsAttendedCount=random.randint(0, 6),
            referralCount=random.randint(0, 4),
            tasksCompleted=random.randint(0, 8),
            education=random.choice(educations),
            skills=random.sample(skills, k=random.randint(2, 4)),
            supporterType="Supporter",
            timeAvailability=random.choice(time_availability),
        )
        rows.append(row.model_dump(by_alias=False))

    payload_rows = [PersonImportRow(**row) for row in rows]
    bulk_upsert_people(PeopleBulkImport(rows=payload_rows, defaultType="Supporter"))
    return rows


def seed_tasks(people_rows: list[dict]) -> None:
    tasks = [
        ("Follow up after event", "Send thank-you notes and collect feedback."),
        ("Update supporter profile", "Confirm contact info and availability."),
        ("Invite to volunteer training", "Share the onboarding schedule."),
        ("Survey outreach", "Ask for feedback on recent survey."),
        ("Community visit", "Schedule neighborhood check-in."),
    ]
    sample_people = random.sample(people_rows, k=min(5, len(people_rows)))
    for idx, person in enumerate(sample_people):
        create_task(
            TaskCreate(
                email=person["email"],
                title=tasks[idx][0],
                description=tasks[idx][1],
                status="Done",
                dueDate="2026-02-20",
            )
        )


def seed_events(people_rows: list[dict]) -> None:
    events = [
        EventCreate(
            name="Neighborhood Listening Session",
            startDate="2026-02-12",
            endDate="2026-02-12",
            location="Saburtalo Community Hall, Tbilisi",
            status="Completed",
            capacity=120,
            notes="Demo event - completed.",
        ),
        EventCreate(
            name="Civic Innovation Workshop",
            startDate="2026-02-25",
            endDate="2026-02-25",
            location="Freedom Square, Tbilisi",
            status="Completed",
            capacity=160,
            notes="Demo event - completed.",
        ),
    ]

    for event in events:
        rows = []
        for person in random.sample(people_rows, k=40):
            rows.append(
                {
                    "email": person["email"],
                    "firstName": person["firstName"],
                    "lastName": person["lastName"],
                    "phone": person["phone"],
                    "group": "Supporter",
                }
            )
        create_event_for_people(
            EventCreateWithPeopleRequest(event=event, rows=rows, registrationStatus="Attended")
        )


def _conversation_rows(convo_id: str, topic_seed: list[str], participants: int = 200):
    clusters = [
        ("Community", 0.4),
        ("Safety", 0.35),
        ("Growth", 0.25),
    ]
    cluster_votes = {
        "Community": [0.72, 0.6, 0.55, 0.68, 0.6, 0.7, 0.5, 0.65],
        "Safety": [0.6, 0.7, 0.5, 0.58, 0.65, 0.55, 0.6, 0.5],
        "Growth": [0.55, 0.5, 0.7, 0.6, 0.45, 0.5, 0.7, 0.6],
    }
    participants_labels = []
    for label, share in clusters:
        participants_labels.extend([label] * int(round(participants * share)))
    participants_labels = participants_labels[:participants]
    random.shuffle(participants_labels)

    rows = []
    base_time = datetime(2026, 2, 1, 9, 0, tzinfo=timezone.utc)
    for idx, cluster_label in enumerate(participants_labels, start=1):
        pid = f"{convo_id}-p{idx:03d}"
        for s_idx, statement in enumerate(topic_seed, start=1):
            agree_prob = cluster_votes[cluster_label][s_idx - 1]
            roll = random.random()
            if roll < agree_prob:
                vote = "agree"
            elif roll < agree_prob + 0.2:
                vote = "pass"
            else:
                vote = "disagree"
            created_at = base_time + timedelta(hours=s_idx)
            reacted_at = created_at + timedelta(minutes=random.randint(5, 120))
            rows.append(
                ConversationDatasetImportRow(
                    conversation_id=convo_id,
                    participant_id=pid,
                    participant_cluster=cluster_label,
                    comment_id=f"s{s_idx:02d}",
                    comment_text=statement,
                    is_seed=True,
                    comment_created_at=created_at.isoformat(),
                    vote=vote,
                    reaction_created_at=reacted_at.isoformat(),
                )
            )
    return rows


def seed_conversations() -> list[str]:
    topics = [
        (
            "Community Safety & Services 2026",
            "Improve local safety, services, and public trust.",
            [
                "Expand community policing with neighborhood feedback councils.",
                "Invest in after-school programs to reduce youth crime.",
                "Increase fines for illegal dumping to protect public spaces.",
                "Create a rapid-response team for infrastructure repairs.",
                "Provide rent stabilization support for low-income families.",
                "Launch citywide mental health outreach teams.",
                "Require transparent budgeting for municipal projects.",
                "Introduce a volunteer credit program for civic service.",
            ],
        ),
        (
            "Housing & Affordability",
            "Balance growth with affordability and housing stability.",
            [
                "Offer tax incentives for affordable housing developments.",
                "Limit short-term rentals in dense residential districts.",
                "Expand housing vouchers for low-income families.",
                "Prioritize renovation of aging apartment blocks.",
                "Introduce tenant mediation services citywide.",
                "Create a public registry of vacant properties.",
                "Fund energy efficiency upgrades for older homes.",
                "Provide relocation support for displaced tenants.",
            ],
        ),
        (
            "Mobility & Public Transport",
            "Make transport safer, faster, and more reliable.",
            [
                "Add dedicated bus lanes in high-traffic corridors.",
                "Increase night service coverage for transit routes.",
                "Improve accessibility for people with disabilities.",
                "Launch fare discounts for students and seniors.",
                "Expand bike lanes connecting major districts.",
                "Introduce real-time arrival displays at stops.",
                "Create safer pedestrian crossings near schools.",
                "Coordinate transport with new housing developments.",
            ],
        ),
    ]

    convo_ids = []
    for topic, description, statements in topics:
        convo = create_conversation(
            ConversationCreate(
                topic=topic,
                description=description,
                is_open=False,
                allow_comment_submission=True,
                allow_viz=True,
                moderation_required=False,
            )
        )
        convo_id = convo.get("id") if isinstance(convo, dict) else None
        if not convo_id:
            continue
        convo_ids.append(convo_id)
        rows = _conversation_rows(convo_id, statements, participants=200)
        import_conversation_dataset(convo_id, ConversationDatasetImportRequest(rows=rows))
    return convo_ids


def seed_due_diligence() -> None:
    competitors = [
        ("Tbilisi Civic Alliance", "Company", "Local civic coalition"),
        ("Nika Tsereteli", "Person", "Public spokesperson"),
    ]
    for name, competitor_type, notes in competitors:
        upsert_competitor(
            CompetitorCreate(name=name, competitorType=competitor_type, notes=notes)
        )

    subjects = [
        ("Tbilisi Civic Alliance", "Company"),
        ("Nika Tsereteli", "Person"),
    ]
    for subject, subject_type in subjects:
        analyze_due_diligence(
            DueDiligenceAnalysisRequest(
                subject=subject,
                subjectType=subject_type,
                useWikidata=True,
                useOpenSanctions=True,
                useNews=True,
                maxNews=6,
                demo=True,
            )
        )

    for opponent, topic in [
        ("Nika Tsereteli", "public safety"),
        ("Tbilisi Civic Alliance", "housing policy"),
    ]:
        debate_prep(
            DebatePrepRequest(
                opponent=opponent,
                topic=topic,
                yearsBack=2,
                maxResults=25,
                useWikipedia=True,
                useGoogle=False,
                useLocalMedia=True,
                demo=True,
            )
        )


def main() -> None:
    status = db_health()
    if not status.get("ok"):
        raise RuntimeError(f"Neo4j connection failed: {status}")

    people_rows = seed_people(500)
    seed_tasks(people_rows)
    seed_events(people_rows)
    convo_ids = seed_conversations()
    seed_due_diligence()

    print("Seed completed.")
    print(f"People: {len(people_rows)}")
    print("Tasks: 5")
    print("Events: 2")
    print(f"Conversations: {len(convo_ids)}")
    print("Due diligence reports: 2")
    print("Debate prep runs: 2 (not persisted)")


if __name__ == "__main__":
    main()
