"""Seed the Civic Voice Lab DEMO Neo4j Aura instance with simulated data.

Loads env in the same order the app does (.env then .env.local override), so
this only runs against whatever database .env.local currently points at.
Refuses to run unless that target's host matches the known demo instance, so
it can never be accidentally pointed at production.

Usage:
    python seed_demo_civic_voice_lab.py
"""
from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from deliberation.api.app.core.env import load_backend_env

load_backend_env(ROOT_DIR)

from deliberation.api.app.db import db_health  # noqa: E402
from deliberation.api.app.routes_conversations import create_conversation  # noqa: E402
from deliberation.api.app.routes_votes import import_conversation_dataset  # noqa: E402
from deliberation.api.app.routes_crm_events import (  # noqa: E402
    EventCreate,
    EventCreateWithPeopleRequest,
    create_event_for_people,
)
from deliberation.api.app.routes_crm_people import (  # noqa: E402
    PeopleBulkImport,
    PersonImportRow,
    SegmentCreate,
    bulk_upsert_people,
    create_segment,
)
from deliberation.api.app.routes_crm_helpers import SegmentFilter  # noqa: E402
from deliberation.api.app.routes_crm_tasks import TaskCreate, create_task  # noqa: E402
from deliberation.api.app.routes_crm_support import (  # noqa: E402
    WhatsAppGroupCreate,
    upsert_whatsapp_group,
)
from deliberation.api.app.routes_crm_campaigns import (  # noqa: E402
    CampaignContributionCreate,
    CampaignCreate,
    CampaignMilestoneCreate,
    CampaignUpdateCreate,
    create_campaign,
    create_campaign_contribution,
    create_campaign_milestone,
    create_campaign_update,
)
from deliberation.api.app.schemas import (  # noqa: E402
    ConversationCreate,
    ConversationDatasetImportRequest,
    ConversationDatasetImportRow,
)

REPO_ROOT = ROOT_DIR.parents[1]
DEMO_PEOPLE_CSV = REPO_ROOT / "data" / "demo" / "generated" / "demo_people.csv"
SUMMARY_JSON = REPO_ROOT / "data" / "demo" / "generated" / "demo_seed_summary.json"

DEMO_HOST_FRAGMENT = "8896b63f.databases.neo4j.io"


def require_demo_target() -> dict:
    status = db_health()
    if not status.get("ok"):
        raise RuntimeError(f"Neo4j connection failed: {status}")
    target_uri = str(status.get("target_uri") or "")
    if DEMO_HOST_FRAGMENT not in target_uri:
        raise RuntimeError(
            "Refusing to seed: active Neo4j target is not the demo instance "
            f"(expected host containing '{DEMO_HOST_FRAGMENT}', got '{target_uri}'). "
            "Check that .env.local points at the Civic Voice demo Aura database."
        )
    return status


def load_people_rows() -> list[dict]:
    with DEMO_PEOPLE_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def seed_people() -> list[dict]:
    rows = load_people_rows()
    payload_rows = []
    for row in rows:
        skills = [item.strip() for item in str(row.get("skills") or "").split(",") if item.strip()]
        payload_rows.append(
            PersonImportRow(
                email=row["email"],
                firstName=row.get("firstName") or None,
                lastName=row.get("lastName") or None,
                gender=row.get("gender") or None,
                age=int(row["age"]) if row.get("age") else None,
                phone=row.get("phone") or None,
                address=row.get("address") or None,
                skills=skills,
                supporterType=row.get("supporterType") or "Supporter",
                timeAvailability=row.get("timeAvailability") or None,
            )
        )
    result = bulk_upsert_people(PeopleBulkImport(rows=payload_rows, defaultType="Supporter"))
    print(f"Seeded people: {len(payload_rows)} ({result})")
    return rows


def seed_tasks(people_rows: list[dict]) -> int:
    tasks = [
        ("Welcome call", "Confirm interest and answer questions about getting involved.", "Done"),
        ("Update contact info", "Verify phone and address are current.", "Open"),
        ("Invite to volunteer training", "Share the onboarding schedule.", "Open"),
        ("Post-event follow-up", "Send a thank-you note and short survey.", "In Progress"),
        ("Neighborhood check-in", "Schedule a short visit or call.", "Open"),
        ("Membership follow-up", "Discuss membership interest.", "Open"),
    ]
    sample = random.sample(people_rows, k=min(len(tasks), len(people_rows)))
    for (title, description, status), person in zip(tasks, sample):
        create_task(
            TaskCreate(
                email=person["email"],
                title=title,
                description=description,
                status=status,
                dueDate="2026-07-20",
            )
        )
    print(f"Seeded tasks: {len(sample)}")
    return len(sample)


def seed_events(people_rows: list[dict]) -> list[str]:
    events = [
        EventCreate(
            name="Neighborhood Listening Session",
            startDate="2026-07-10",
            endDate="2026-07-10",
            location="Saburtalo Community Hall, Tbilisi",
            status="Completed",
            capacity=120,
            notes="Simulated demo event - completed.",
        ),
        EventCreate(
            name="Civic Innovation Workshop",
            startDate="2026-07-24",
            endDate="2026-07-24",
            location="Vake Culture Center, Tbilisi",
            status="Scheduled",
            capacity=160,
            notes="Simulated demo event - upcoming.",
        ),
    ]
    names = []
    for event in events:
        rows = [
            {
                "email": person["email"],
                "firstName": person.get("firstName"),
                "lastName": person.get("lastName"),
                "phone": person.get("phone"),
                "group": person.get("supporterType") or "Supporter",
            }
            for person in random.sample(people_rows, k=min(40, len(people_rows)))
        ]
        create_event_for_people(
            EventCreateWithPeopleRequest(event=event, rows=rows, registrationStatus="Attended")
        )
        names.append(event.name)
    print(f"Seeded events: {len(names)}")
    return names


def seed_segments() -> int:
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
    print("Seeded segments: 2")
    return 2


def seed_whatsapp_groups() -> int:
    upsert_whatsapp_group(
        WhatsAppGroupCreate(
            name="Civic Voice Lab Outreach",
            inviteLink="https://chat.whatsapp.com/demo-cvl-outreach",
            notes="Simulated demo outreach group.",
        )
    )
    upsert_whatsapp_group(
        WhatsAppGroupCreate(
            name="Civic Voice Lab Events",
            inviteLink="https://chat.whatsapp.com/demo-cvl-events",
            notes="Simulated demo events group.",
        )
    )
    print("Seeded WhatsApp groups: 2")
    return 2


def seed_campaigns() -> list[str]:
    campaigns_spec = [
        dict(
            name="Clean Streets Initiative",
            topic="Neighborhood cleanup and public space upkeep",
            objective="Organize recurring clean-up days across four districts",
            locationCity="Tbilisi",
            beneficiaryType="Community",
            fundingTargetAmount=5000,
            currency="GEL",
            campaignCategory="Community Services",
            status="Active",
            owner="Demo Campaign Team",
            goal=500,
            contributions=[(150, "Nino T."), (300, "Anonymous"), (75, "Levan K.")],
            milestone=("Recruit district coordinators", 1000, "Done", 100),
            update="Four district coordinators confirmed; first clean-up day scheduled.",
        ),
        dict(
            name="Winter Relief Fund",
            topic="Emergency support for vulnerable households",
            objective="Provide heating assistance to 100 households",
            locationCity="Tbilisi",
            beneficiaryType="Low-income households",
            fundingTargetAmount=8000,
            currency="GEL",
            campaignCategory="Social Support",
            status="Planned",
            owner="Demo Campaign Team",
            goal=100,
            contributions=[(500, "Community Partner Co.")],
            milestone=("Identify eligible households", 0, "In Progress", 40),
            update="Outreach team has identified 38 eligible households so far.",
        ),
    ]
    names = []
    for spec in campaigns_spec:
        campaign = create_campaign(
            CampaignCreate(
                name=spec["name"],
                topic=spec["topic"],
                objective=spec["objective"],
                locationCity=spec["locationCity"],
                beneficiaryType=spec["beneficiaryType"],
                fundingTargetAmount=spec["fundingTargetAmount"],
                currency=spec["currency"],
                campaignVisibility="Public",
                campaignCategory=spec["campaignCategory"],
                status=spec["status"],
                owner=spec["owner"],
                goal=spec["goal"],
                notes="Simulated demo campaign for Civic Voice Lab.",
            )
        )
        campaign_id = campaign.get("campaignId") if isinstance(campaign, dict) else None
        if not campaign_id:
            continue
        for amount, contributor in spec["contributions"]:
            create_campaign_contribution(
                campaign_id,
                CampaignContributionCreate(
                    amount=amount,
                    currency=spec["currency"],
                    contributorName=contributor,
                    paymentStatus="succeeded",
                    donorVisibility="public",
                ),
            )
        title, amount_target, status, completion = spec["milestone"]
        create_campaign_milestone(
            campaign_id,
            CampaignMilestoneCreate(
                title=title,
                amountTarget=amount_target,
                status=status,
                completionPercent=completion,
            ),
        )
        create_campaign_update(
            campaign_id,
            CampaignUpdateCreate(message=spec["update"], createdBy=spec["owner"], status="Published"),
        )
        names.append(spec["name"])
    print(f"Seeded campaigns: {len(names)}")
    return names


def _conversation_rows(convo_id: str, statements: list[str], participants: int = 150):
    from datetime import datetime, timedelta, timezone

    clusters = [("Community", 0.4), ("Safety", 0.35), ("Growth", 0.25)]
    cluster_votes = {
        "Community": [0.72, 0.6, 0.55, 0.68, 0.6, 0.7, 0.5, 0.65],
        "Safety": [0.6, 0.7, 0.5, 0.58, 0.65, 0.55, 0.6, 0.5],
        "Growth": [0.55, 0.5, 0.7, 0.6, 0.45, 0.5, 0.7, 0.6],
    }
    labels = []
    for label, share in clusters:
        labels.extend([label] * int(round(participants * share)))
    labels = labels[:participants]
    random.shuffle(labels)

    rows = []
    base_time = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
    for idx, cluster_label in enumerate(labels, start=1):
        pid = f"{convo_id}-p{idx:03d}"
        for s_idx, statement in enumerate(statements, start=1):
            agree_prob = cluster_votes[cluster_label][(s_idx - 1) % len(cluster_votes[cluster_label])]
            roll = random.random()
            vote = "agree" if roll < agree_prob else ("pass" if roll < agree_prob + 0.2 else "disagree")
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
            "Community Safety & Services",
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
        rows = _conversation_rows(convo_id, statements)
        import_conversation_dataset(convo_id, ConversationDatasetImportRequest(rows=rows))
    print(f"Seeded conversations: {len(convo_ids)}")
    return convo_ids


def main() -> None:
    status = require_demo_target()
    print(f"Seeding demo target: {status.get('target_uri')} / {status.get('target_database')}")

    people_rows = seed_people()
    tasks_count = seed_tasks(people_rows)
    event_names = seed_events(people_rows)
    segments_count = seed_segments()
    whatsapp_count = seed_whatsapp_groups()
    campaign_names = seed_campaigns()
    convo_ids = seed_conversations()

    summary = {
        "target_uri": status.get("target_uri"),
        "target_database": status.get("target_database"),
        "people": len(people_rows),
        "tasks": tasks_count,
        "events": event_names,
        "segments": segments_count,
        "whatsapp_groups": whatsapp_count,
        "campaigns": campaign_names,
        "conversations": len(convo_ids),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\nSeed completed.")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
