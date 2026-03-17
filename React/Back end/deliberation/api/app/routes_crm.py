import io
import json
import os
import re
import smtplib
from email.message import EmailMessage
from typing import List, Optional, Tuple
from uuid import uuid4

import numpy as np
import pandas as pd
import requests

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field

from .db import get_active_database, get_driver
from .routes import create_conversation, seed_comments
from .schemas import ConversationCreate, SeedCommentsRequest

router = APIRouter()

TASK_STATUSES = ["Open", "In Progress", "Done", "Cancelled"]
EVENT_STATUSES = ["Planned", "Scheduled", "Completed", "Cancelled"]
EVENT_REGISTRATION_STATUSES = ["Registered", "Attended", "Cancelled", "No Show"]
CAMPAIGN_STATUSES = ["Planned", "Active", "Paused", "Completed"]


class PersonOut(BaseModel):
    email: str
    full_name: str = Field(alias="fullName")
    group: str
    phone: Optional[str] = None
    time_availability: Optional[str] = Field(alias="timeAvailability", default=None)


class CrmSummaryOut(BaseModel):
    total_people: int
    supporters: int
    members: int
    missing_age: int = 0
    missing_gender: int = 0
    missing_time_availability: int = 0


class PersonProfileOut(BaseModel):
    email: str
    first_name: Optional[str] = Field(alias="firstName", default=None)
    last_name: Optional[str] = Field(alias="lastName", default=None)
    phone: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    time_availability: Optional[str] = Field(alias="timeAvailability", default=None)
    about: Optional[str] = None
    agrees_with_manifesto: bool = Field(alias="agreesWithManifesto", default=False)
    interested_in_membership: bool = Field(alias="interestedInMembership", default=False)
    facebook_group_member: bool = Field(alias="facebookGroupMember", default=False)
    supporter_types: List[str] = Field(alias="supporterTypes", default_factory=list)
    tags: List[str] = []
    skills: List[str] = []
    involvement_areas: List[str] = Field(alias="involvementAreas", default_factory=list)


class PersonProfileUpdate(BaseModel):
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    timeAvailability: Optional[str] = None
    about: Optional[str] = None
    agreesWithManifesto: Optional[bool] = None
    interestedInMembership: Optional[bool] = None
    facebookGroupMember: Optional[bool] = None


class TaskOut(BaseModel):
    task_id: str = Field(alias="taskId")
    title: str
    description: Optional[str] = ""
    status: str
    due_date: Optional[str] = Field(alias="dueDate", default="")
    first_name: Optional[str] = Field(alias="firstName", default="")
    last_name: Optional[str] = Field(alias="lastName", default="")
    email: Optional[str] = None
    group: Optional[str] = None
    created_at: Optional[str] = Field(alias="createdAt", default=None)
    updated_at: Optional[str] = Field(alias="updatedAt", default=None)


class TaskCreate(BaseModel):
    email: str
    title: str
    description: Optional[str] = None
    status: Optional[str] = "Open"
    dueDate: Optional[str] = None


class TaskStatusUpdate(BaseModel):
    status: str


class PersonUpsert(BaseModel):
    email: str
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    phone: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    effortHours: Optional[float] = None
    eventsAttendedCount: Optional[int] = None
    referralCount: Optional[int] = None
    tasksCompleted: Optional[int] = None
    supporterType: Optional[str] = "Supporter"
    address: Optional[str] = None
    timeAvailability: Optional[str] = None


class PersonImportRow(BaseModel):
    email: str
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    effortHours: Optional[float] = None
    eventsAttendedCount: Optional[int] = None
    referralCount: Optional[int] = None
    tasksCompleted: Optional[int] = None
    education: Optional[str] = None
    skills: Optional[List[str]] = None
    supporterType: Optional[str] = "Supporter"
    timeAvailability: Optional[str] = None


class PeopleBulkImport(BaseModel):
    rows: List[PersonImportRow]
    defaultType: Optional[str] = "Supporter"


class DashboardOut(BaseModel):
    metrics: dict
    charts: dict


class MapPersonOut(BaseModel):
    full_name: str = Field(alias="fullName")
    email: str
    group: str
    lat: float
    lon: float
    time_availability: str = Field(alias="timeAvailability")
    age_group: str = Field(alias="ageGroup")
    gender: str
    skills: List[str] = []
    skills_label: str = Field(alias="skillsLabel")
    involvement_label: str = Field(alias="involvementLabel")
    involvement_title: str = Field(alias="involvementTitle")
    address_label: str = Field(alias="addressLabel")
    rating_stars: Optional[str] = Field(alias="ratingStars", default=None)
    effort_hours: float = Field(alias="effortHours")
    event_attend_count: int = Field(alias="eventAttendCount")
    referral_count: int = Field(alias="referralCount")
    about: Optional[str] = ""
    point_size: float = Field(alias="pointSize")
    color: List[int]


class EventCreate(BaseModel):
    name: str
    startDate: Optional[str] = ""
    endDate: Optional[str] = ""
    location: Optional[str] = ""
    status: Optional[str] = "Planned"
    capacity: Optional[int] = 0
    notes: Optional[str] = ""


class EventOut(BaseModel):
    event_id: str = Field(alias="eventId")
    event_key: Optional[str] = Field(alias="eventKey", default=None)
    name: str
    start_date: Optional[str] = Field(alias="startDate", default="")
    end_date: Optional[str] = Field(alias="endDate", default="")
    location: Optional[str] = ""
    status: str
    capacity: int = 0
    registrations: int = 0
    notes: Optional[str] = ""


class CampaignCreate(BaseModel):
    name: str
    topic: Optional[str] = ""
    objective: Optional[str] = ""
    legislationText: Optional[str] = ""
    manifestoText: Optional[str] = ""
    expertPrompt: Optional[str] = ""
    status: Optional[str] = "Planned"
    startDate: Optional[str] = ""
    endDate: Optional[str] = ""
    owner: Optional[str] = ""
    targetGroup: Optional[str] = ""
    goal: Optional[int] = 0
    notes: Optional[str] = ""


class CampaignOut(BaseModel):
    campaign_id: str = Field(alias="campaignId")
    name: str
    topic: Optional[str] = ""
    objective: Optional[str] = ""
    status: str
    start_date: Optional[str] = Field(alias="startDate", default="")
    end_date: Optional[str] = Field(alias="endDate", default="")
    owner: Optional[str] = ""
    target_group: Optional[str] = Field(alias="targetGroup", default="")
    goal: int = 0
    notes: Optional[str] = ""
    legislation_text: Optional[str] = Field(alias="legislationText", default="")
    manifesto_text: Optional[str] = Field(alias="manifestoText", default="")
    expert_prompt: Optional[str] = Field(alias="expertPrompt", default="")
    consensus_statements: List[str] = Field(alias="consensusStatements", default_factory=list)
    polarization_statements: List[str] = Field(
        alias="polarizationStatements", default_factory=list
    )
    deliberation_conversation_id: Optional[str] = Field(
        alias="deliberationConversationId", default=""
    )


class CampaignAnalysisRequest(BaseModel):
    topic: Optional[str] = ""
    legislationText: Optional[str] = ""
    manifestoText: Optional[str] = ""
    expertPrompt: Optional[str] = ""


class FurryFriendUpsert(BaseModel):
    furryId: Optional[str] = None
    municipality: Optional[str] = ""
    species: Optional[str] = "Dog"
    name: Optional[str] = ""
    gender: Optional[str] = ""
    age: Optional[int] = None
    neutered: Optional[bool] = None
    breed: Optional[str] = ""
    color: Optional[str] = ""
    chipNumber: Optional[str] = ""
    address: Optional[str] = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    notes: Optional[str] = ""


class FurryFriendOut(BaseModel):
    furry_id: str = Field(alias="furryId")
    municipality: str
    species: str
    name: Optional[str] = ""
    gender: Optional[str] = ""
    age: Optional[int] = None
    neutered: Optional[bool] = None
    breed: Optional[str] = ""
    color: Optional[str] = ""
    chip_number: Optional[str] = Field(alias="chipNumber", default="")
    address: Optional[str] = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    notes: Optional[str] = ""


class EventRegistrationOut(BaseModel):
    email: str
    first_name: Optional[str] = Field(alias="firstName", default="")
    last_name: Optional[str] = Field(alias="lastName", default="")
    phone: Optional[str] = ""
    group: str
    registration_status: str = Field(alias="registrationStatus")
    notes: Optional[str] = ""
    registered_at: Optional[str] = Field(alias="registeredAt", default=None)
    updated_at: Optional[str] = Field(alias="updatedAt", default=None)


class EventRegisterRequest(BaseModel):
    person: dict
    status: Optional[str] = "Registered"
    notes: Optional[str] = ""


class EventBulkRegisterRequest(BaseModel):
    rows: List[dict]
    status: Optional[str] = "Registered"


class EventCreateWithPeopleRequest(BaseModel):
    event: EventCreate
    rows: List[dict]
    registrationStatus: Optional[str] = "Registered"


class EventStatusCountOut(BaseModel):
    event_id: str = Field(alias="eventId")
    event_name: str = Field(alias="eventName")
    registration_status: str = Field(alias="registrationStatus")
    count: int


class AdminStatusOut(BaseModel):
    neo4j_status: str
    deliberation_status: str
    api_urls: List[str] = []
    feedback_configured: bool
    feedback_from: Optional[str] = None
    feedback_to: Optional[str] = None
    whatsapp_configured: bool
    slack_configured: bool
    slack_username: Optional[str] = None


class ClearDbRequest(BaseModel):
    confirm: str = Field(min_length=1)


class TaskBulkCreate(BaseModel):
    rows: List[TaskCreate]


class SegmentFilter(BaseModel):
    group: Optional[str] = None
    timeAvailability: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    skills: Optional[List[str]] = None
    nameContains: Optional[str] = None
    addressContains: Optional[str] = None
    minEffortHours: Optional[float] = None


class SegmentCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    filterSpec: SegmentFilter = Field(default_factory=SegmentFilter)


class SegmentOut(BaseModel):
    segment_id: str = Field(alias="segmentId")
    name: str
    description: str = ""
    updated_at: Optional[str] = Field(alias="updatedAt", default=None)


class SegmentRunRequest(BaseModel):
    filterSpec: SegmentFilter = Field(default_factory=SegmentFilter)
    limit: Optional[int] = 500


class SegmentPersonOut(BaseModel):
    full_name: str = Field(alias="fullName")
    email: str
    group: str
    time_availability: str = Field(alias="timeAvailability")
    address: str = ""
    effort_hours: float = Field(alias="effortHours")
    tags: List[str] = []
    skills: List[str] = []


class WhatsAppGroupCreate(BaseModel):
    name: str
    inviteLink: str
    notes: Optional[str] = ""


class WhatsAppGroupOut(BaseModel):
    group_id: str = Field(alias="groupId")
    name: str
    invite_link: str = Field(alias="inviteLink")
    notes: str = ""
    updated_at: Optional[str] = Field(alias="updatedAt", default=None)


class WhatsAppMessage(BaseModel):
    message: str
    appendInvite: Optional[bool] = False
    source: Optional[str] = "outreach_page"


def _execute_read(session, query: str, params: Optional[dict] = None):
    if hasattr(session, "execute_read"):
        return session.execute_read(lambda tx: list(tx.run(query, params or {})))
    return session.read_transaction(lambda tx: list(tx.run(query, params or {})))


def _execute_write(session, query: str, params: Optional[dict] = None):
    def _run(tx):
        result = tx.run(query, params or {})
        return list(result)

    if hasattr(session, "execute_write"):
        return session.execute_write(_run)
    return session.write_transaction(_run)


def _db_session(driver):
    return driver.session(database=get_active_database())


def _load_profile(email: str) -> Optional[dict]:
    driver = get_driver()
    query = """
    MATCH (p:Person {email: $email})
    OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(st:SupporterType)
    OPTIONAL MATCH (p)-[:HAS_TAG]->(tag:Tag)
    OPTIONAL MATCH (p)-[:CAN_CONTRIBUTE_WITH]->(sk:Skill)
    OPTIONAL MATCH (p)-[:INTERESTED_IN]->(ia:InvolvementArea)
    WITH p,
      collect(DISTINCT st.name) AS supporterTypes,
      collect(DISTINCT tag.name) AS tags,
      collect(DISTINCT sk.name) AS skills,
      collect(DISTINCT ia.name) AS involvementAreas
    RETURN
      p.email AS email,
      p.firstName AS firstName,
      p.lastName AS lastName,
      p.phone AS phone,
      p.gender AS gender,
      p.age AS age,
      coalesce(p.timeAvailability, 'Unspecified') AS timeAvailability,
      coalesce(p.about, '') AS about,
      coalesce(p.agreesWithManifesto, false) AS agreesWithManifesto,
      coalesce(p.interestedInMembership, false) AS interestedInMembership,
      coalesce(p.facebookGroupMember, false) AS facebookGroupMember,
      supporterTypes,
      tags,
      skills,
      involvementAreas
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query, {"email": email})
    if not records:
        return None
    return records[0].data()


def _clean_text(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _normalize_species(value: Optional[str]) -> str:
    text = _clean_text(value)
    if not text:
        return "Dog"
    lowered = text.lower()
    if "cat" in lowered:
        return "Cat"
    if "dog" in lowered:
        return "Dog"
    return text.title()


def _parse_bool(value) -> Optional[bool]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"yes", "true", "1", "y"}:
        return True
    if text in {"no", "false", "0", "n"}:
        return False
    return None


def _extract_municipality(address: Optional[str]) -> Optional[str]:
    text = _clean_text(address)
    if not text:
        return None
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) >= 2:
        return parts[-2]
    return parts[0]


def _strip_markdown(text: str) -> str:
    cleaned = text.replace("**", "").replace("__", "")
    cleaned = cleaned.replace("`", "")
    return cleaned


def _split_statements(text: Optional[str]) -> List[str]:
    if not text:
        return []
    raw = str(text).replace("\r", "\n")
    lines = [line.strip() for line in raw.split("\n")]
    fragments: List[str] = []
    prefix: Optional[str] = None
    for line in lines:
        if not line:
            prefix = None
            continue
        if line.lstrip().startswith("#"):
            prefix = None
            continue
        if re.match(r"^[-*•]\s+", line) or re.match(r"^\d+[.)]\s+", line):
            bullet = re.sub(r"^[-*•]\s+", "", line)
            bullet = re.sub(r"^\d+[.)]\s+", "", bullet)
            bullet = _strip_markdown(_clean_text(bullet))
            if not bullet:
                continue
            if prefix:
                fragments.append(f"{prefix} {bullet}")
            else:
                fragments.append(bullet)
            continue
        cleaned_line = _strip_markdown(_clean_text(line))
        if not cleaned_line:
            prefix = None
            continue
        if cleaned_line.endswith(":") and len(cleaned_line) >= 20:
            prefix = cleaned_line[:-1].strip()
            continue
        prefix = None
        fragments.append(cleaned_line)

    statements: List[str] = []
    for fragment in fragments:
        for part in re.split(r"(?<=[.!?])\s+", fragment):
            cleaned = _clean_text(part)
            if cleaned and len(cleaned) >= 20:
                statements.append(cleaned)
    return statements


def _ensure_period(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return cleaned
    if cleaned[-1] in ".!?":
        return cleaned
    return f"{cleaned}."


def _normalize_campaign_statement(text: str, topic_label: str) -> str:
    cleaned = _strip_markdown(_clean_text(text))
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if lowered.startswith("there is no single comprehensive"):
        return "The policy should consolidate fragmented rules into a single enforceable framework."
    if lowered.startswith("public opinion is divided"):
        return "The policy should balance animal welfare and public safety priorities."
    if lowered.startswith(("there is", "there are", "the problem", "public opinion", "the current conflict", "georgia faces")):
        return ""
    overall_prefix = "the overall goal is to "
    goal_prefix = "the goal is to "
    if lowered.startswith(overall_prefix):
        return f"The policy should aim to {cleaned[len(overall_prefix):]}"
    if lowered.startswith(goal_prefix):
        return f"The policy should aim to {cleaned[len(goal_prefix):]}"
    if " is responsible for " in lowered:
        cleaned = re.sub(
            r"\bis responsible for\b", "should be responsible for", cleaned, flags=re.I
        )
        return cleaned
    if "municipal regulations adopted by" in lowered:
        return f"The policy should align with municipal regulations adopted by {cleaned.split('by', 1)[-1].strip()}."
    if "administrative and criminal laws" in lowered:
        return "The policy should align with national administrative and criminal laws on animal welfare."
    if "law on domestic animals" in lowered:
        return "The policy should incorporate the Law on Domestic Animals and related reforms."
    if "animal monitoring agency" in lowered:
        return "The policy should empower the Tbilisi Animal Monitoring Agency with clear responsibilities."
    if lowered.startswith("stray animals are "):
        return f"The policy should ensure that {cleaned[0].lower() + cleaned[1:]}"
    if lowered.startswith("animals that are "):
        return f"The policy should ensure that {cleaned[0].lower() + cleaned[1:]}"
    if any(
        term in lowered
        for term in [
            "should",
            "must",
            "need to",
            "requires",
            "require ",
            "ban",
            "prohibit",
            "ensure",
            "enforce",
        ]
    ):
        return cleaned
    if re.match(r"^[A-Z][a-z]+ing\b", cleaned):
        return f"The policy should include {cleaned[0].lower() + cleaned[1:]}"
    if re.match(
        r"^(capture|capturing|operate|operating|steriliz|vaccinat|identif|return|respond|register|microchip|adopt|adoption|shelter|enforce|prevent)\b",
        cleaned,
        flags=re.I,
    ):
        return f"The policy should include {cleaned[0].lower() + cleaned[1:]}"
    return f"{topic_label}: {cleaned}"


def _contains_any(text: str, keywords: List[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _prepare_seed_statements(statements: List[str], topic_label: str) -> List[str]:
    cleaned_statements: List[str] = []
    seen = set()
    for statement in statements:
        normalized = _normalize_campaign_statement(statement, topic_label)
        if not normalized:
            normalized = _strip_markdown(_clean_text(statement))
        normalized = _ensure_period(normalized)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned_statements.append(normalized)
    return cleaned_statements


def _classify_statement(text: str) -> str:
    lowered = text.lower()
    polar_terms = [
        "must not",
        "ban",
        "reject",
        "against",
        "illegal",
        "penalt",
        "fine",
        "blacklist",
        "prohibit",
        "stop",
        "defeat",
        "prevent",
        "no ",
        "never",
    ]
    if any(term in lowered for term in polar_terms):
        return "polarization"
    return "consensus"


def _fill_statements(items: List[str], target: int, fallback: List[str]) -> List[str]:
    result = []
    seen = set()
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= target:
            break
    if len(result) < target:
        for item in fallback:
            if len(result) >= target:
                break
            if item.lower() in seen:
                continue
            result.append(item)
            seen.add(item.lower())
    return result[:target]


def _generate_campaign_analysis(
    topic: Optional[str],
    legislation_text: Optional[str],
    manifesto_text: Optional[str],
    expert_prompt: Optional[str],
) -> dict:
    topic_label = _clean_text(topic) or "Campaign"
    raw_candidates: List[str] = []
    for text in [legislation_text, manifesto_text, expert_prompt]:
        raw_candidates.extend(_split_statements(text))

    normalized_candidates: List[str] = []
    seen = set()
    for statement in raw_candidates:
        normalized = _normalize_campaign_statement(statement, topic_label)
        normalized = _ensure_period(normalized)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized_candidates.append(normalized)

    combined_source = " ".join(raw_candidates + [topic_label])
    animal_keywords = [
        "animal",
        "stray",
        "dog",
        "cat",
        "rabies",
        "tnvr",
        "steril",
        "microchip",
        "shelter",
        "adoption",
        "breeding",
        "abandon",
        "vaccin",
    ]
    is_animal_topic = _contains_any(combined_source, animal_keywords)

    if is_animal_topic:
        consensus_fallback = [
            "Mandate microchipping and registration for all owned dogs and cats.",
            "Guarantee stable funding for TNVR sterilization and vaccination programs.",
            "Expand municipal shelters and adoption incentives for stray animals.",
            "Clarify municipal responsibilities with measurable performance targets.",
            "Prioritize rabies vaccination and disease monitoring in high-risk areas.",
        ]
        polarization_fallback = [
            "Introduce stronger fines and penalties for pet abandonment.",
            "Ban unregulated breeding and require breeder licensing.",
            "Allow courts to blacklist repeat animal abusers from ownership.",
            "Create a public safety response unit for aggressive stray reports.",
            "Require mandatory sterilization for unregistered animals.",
        ]
    else:
        consensus_fallback = [
            f"{topic_label}: define clear responsibilities and funding.",
            f"{topic_label}: improve transparency and accountability.",
            f"{topic_label}: use evidence-based targets and timelines.",
            f"{topic_label}: expand citizen engagement and feedback.",
            f"{topic_label}: publish measurable progress updates.",
        ]
        polarization_fallback = [
            f"{topic_label}: enforce strict penalties for noncompliance.",
            f"{topic_label}: ban practices that undermine the policy goals.",
            f"{topic_label}: require mandatory registration or licensing where needed.",
            f"{topic_label}: centralize authority to ensure consistent enforcement.",
            f"{topic_label}: prohibit loopholes that weaken reforms.",
        ]

    consensus = []
    polarization = []
    for statement in normalized_candidates:
        if _classify_statement(statement) == "polarization":
            polarization.append(statement)
        else:
            consensus.append(statement)

    consensus_statements = _fill_statements(consensus, 5, consensus_fallback)
    polarization_statements = _fill_statements(polarization, 5, polarization_fallback)

    return {
        "consensusStatements": consensus_statements,
        "polarizationStatements": polarization_statements,
    }


def _normalize_supporter_type(value, default_type="Supporter") -> str:
    text = _clean_text(value)
    if not text:
        return default_type
    return "Member" if "member" in text.lower() else "Supporter"


def _format_list_label(values, limit=6):
    items = [str(v).strip() for v in values or [] if str(v).strip()]
    items = sorted(set(items))
    if not items:
        return "None"
    if len(items) > limit:
        return ", ".join(items[:limit]) + f" (+{len(items) - limit} more)"
    return ", ".join(items)


def _education_score(level: Optional[str]) -> int:
    if not level:
        return 0
    text = str(level).lower()
    if "phd" in text:
        return 4
    if "master" in text:
        return 3
    if "bachelor" in text:
        return 2
    if "high" in text:
        return 1
    return 0


def _pick_education(levels):
    cleaned = [str(x).strip() for x in levels or [] if str(x).strip()]
    if not cleaned:
        return ("Unspecified", 0)
    scored = [(level, _education_score(level)) for level in cleaned]
    scored = sorted(scored, key=lambda item: item[1], reverse=True)
    return scored[0]


def _calc_rating(effort_score):
    if effort_score is None or pd.isna(effort_score):
        return None
    if effort_score >= 20:
        return 5
    if effort_score >= 15:
        return 4
    if effort_score >= 10:
        return 3
    if effort_score >= 5:
        return 2
    if effort_score > 0:
        return 1
    return None


def _rating_stars(value):
    if value is None or pd.isna(value):
        return "Not rated"
    filled = max(0, min(5, int(value)))
    return "⭐" * filled + "☆" * (5 - filled)


def _rating_color(value):
    if value is None or pd.isna(value):
        return [120, 120, 120, 140]
    if value >= 4:
        return [46, 204, 113, 190]
    if value >= 3:
        return [241, 196, 15, 190]
    return [231, 76, 60, 190]


def _age_group(value):
    if value is None or pd.isna(value):
        return "Unspecified"
    try:
        age = int(value)
    except (TypeError, ValueError):
        return "Unspecified"
    if age < 18:
        return "Under 18"
    if age < 25:
        return "18-24"
    if age < 35:
        return "25-34"
    if age < 45:
        return "35-44"
    if age < 55:
        return "45-54"
    if age < 65:
        return "55-64"
    return "65+"


def _classify_group(types):
    types = types or []
    for t in types:
        if t and "member" in str(t).lower():
            return "Member"
    return "Supporter"


def _query_df(query: str, params: Optional[dict] = None) -> pd.DataFrame:
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_read(session, query, params or {})
    if not records:
        return pd.DataFrame()
    return pd.DataFrame([record.data() for record in records])


def _enrich_people_core(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if "timeAvailability" not in df.columns:
        df["timeAvailability"] = "Unspecified"
    else:
        df["timeAvailability"] = df["timeAvailability"].fillna("Unspecified")
    df["types"] = df["types"].apply(lambda v: v or [])
    df["group"] = df["types"].apply(_classify_group)
    df["age"] = pd.to_numeric(df["age"], errors="coerce")
    df["ageGroup"] = df["age"].apply(_age_group)
    df["activityCount"] = pd.to_numeric(df.get("activityCount"), errors="coerce").fillna(0).astype(int)
    df["eventJoinCount"] = (
        pd.to_numeric(df.get("eventJoinCount"), errors="coerce").fillna(0).astype(int)
    )
    df["eventAttendRelCount"] = (
        pd.to_numeric(df.get("eventAttendRelCount"), errors="coerce").fillna(0).astype(int)
    )
    df["skills"] = df["skills"].apply(lambda v: v or [])
    df["skillCount"] = df["skills"].apply(lambda v: len([x for x in v if x]))
    df["skillsLabel"] = df["skills"].apply(_format_list_label)
    df["eventAttendProp"] = (
        pd.to_numeric(df.get("eventAttendProp"), errors="coerce").fillna(0).astype(int)
    )
    df["referredCount"] = (
        pd.to_numeric(df.get("referredCount"), errors="coerce").fillna(0).astype(int)
    )
    df["recruitedCount"] = (
        pd.to_numeric(df.get("recruitedCount"), errors="coerce").fillna(0).astype(int)
    )
    df["referralProp"] = (
        pd.to_numeric(df.get("referralProp"), errors="coerce").fillna(0).astype(int)
    )
    df["eventAttendCount"] = df["eventAttendRelCount"] + df["eventAttendProp"]
    df["referralCount"] = df["referredCount"] + df["recruitedCount"] + df["referralProp"]
    df["joinCount"] = df["activityCount"] + df["eventJoinCount"]
    df["effortHours"] = pd.to_numeric(df.get("effortHours"), errors="coerce").fillna(0.0)
    df["donationTotal"] = pd.to_numeric(df.get("donationTotal"), errors="coerce").fillna(0.0)
    if "tasksCompleted" not in df.columns:
        df["tasksCompleted"] = 0
    else:
        df["tasksCompleted"] = (
            pd.to_numeric(df.get("tasksCompleted"), errors="coerce").fillna(0).astype(int)
        )
    education_values = df["educationLevels"].apply(_pick_education)
    df["educationLevel"] = education_values.apply(lambda value: value[0])
    df["educationScore"] = education_values.apply(lambda value: value[1])
    df["effortScore"] = df["effortHours"] + df["eventAttendCount"] + df["referralCount"]
    df["hasParticipation"] = (
        df["activityCount"] + df["eventJoinCount"] + df["eventAttendCount"]
    ) > 0
    df["ratingScore"] = df["eventAttendCount"] + df["tasksCompleted"]
    df["rating"] = df["ratingScore"].apply(_calc_rating)
    df.loc[~df["hasParticipation"], "rating"] = pd.NA
    df["ratingStars"] = df["rating"].apply(_rating_stars)
    full_name = (df["firstName"].fillna("") + " " + df["lastName"].fillna("")).str.strip()
    df["fullName"] = full_name.mask(full_name == "", df["email"])
    df["age"] = pd.to_numeric(df["age"], errors="coerce")
    return df


def _load_supporter_summary_df() -> pd.DataFrame:
    df = _query_df(
        """
        MATCH (p:Person)
        OPTIONAL MATCH (p)-[:IS_SUPPORTER]->(s:Supporter)
        OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(st:SupporterType)
        OPTIONAL MATCH (p)-[:HAS_ACTIVITY]->(a:Activity)
        OPTIONAL MATCH (p)-[r:REGISTERED_FOR]->(:Event)
        OPTIONAL MATCH (p)-[:CAN_CONTRIBUTE_WITH]->(sk:Skill)
        OPTIONAL MATCH (p)-[:HAS_EDUCATION]->(ed:EducationLevel)
        OPTIONAL MATCH (p)<-[:REFERRED_BY]-(refP:Person)
        OPTIONAL MATCH (s)-[:RECRUITED]->(sr:Supporter)
        WITH p, s,
             collect(DISTINCT st.name) AS types,
             collect(DISTINCT ed.name) AS educationLevels,
             count(DISTINCT a) AS activityCount,
             count(DISTINCT r) AS eventJoinCount,
             count(DISTINCT CASE WHEN r.status = 'Attended' THEN r ELSE NULL END) AS eventAttendRelCount,
             collect(DISTINCT sk.name) AS skills,
             count(DISTINCT refP) AS referredCount,
             count(DISTINCT sr) AS recruitedCount
        RETURN
          p.email AS email,
          p.firstName AS firstName,
          p.lastName AS lastName,
          coalesce(p.gender, 'Unspecified') AS gender,
          coalesce(p.timeAvailability, 'Unspecified') AS timeAvailability,
          p.age AS age,
          types,
          activityCount,
          eventJoinCount,
          eventAttendRelCount,
          skills,
          educationLevels,
          coalesce(p.eventsAttendedCount, 0) AS eventAttendProp,
          coalesce(p.referralCount, 0) AS referralProp,
          coalesce(p.tasksCompleted, 0) AS tasksCompleted,
          referredCount,
          recruitedCount,
          coalesce(p.effortHours, p.volunteerHours, s.volunteer_hours, s.volunteerHours, 0) AS effortHours,
          coalesce(p.donationTotal, 0) AS donationTotal
        """,
        {},
    )
    if df.empty:
        return df
    return _enrich_people_core(df)


def _load_map_data_df() -> pd.DataFrame:
    df = _query_df(
        """
        MATCH (p:Person)
        OPTIONAL MATCH (p)-[:LIVES_AT]->(a:Address)
        WITH p,
             coalesce(p.lat, a.latitude) AS lat,
             coalesce(p.lon, a.longitude) AS lon,
             coalesce(p.address, a.fullAddress) AS address
        WHERE lat IS NOT NULL AND lon IS NOT NULL
        OPTIONAL MATCH (p)-[:IS_SUPPORTER]->(s:Supporter)
        OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(st:SupporterType)
        OPTIONAL MATCH (p)-[:HAS_ACTIVITY]->(a:Activity)
        OPTIONAL MATCH (p)-[r:REGISTERED_FOR]->(:Event)
        OPTIONAL MATCH (p)-[:CAN_CONTRIBUTE_WITH]->(sk:Skill)
        OPTIONAL MATCH (p)-[:HAS_EDUCATION]->(ed:EducationLevel)
        OPTIONAL MATCH (p)-[:INTERESTED_IN]->(ia:InvolvementArea)
        OPTIONAL MATCH (p)<-[:REFERRED_BY]-(refP:Person)
        OPTIONAL MATCH (s)-[:RECRUITED]->(sr:Supporter)
        WITH p, s, lat, lon, address,
             collect(DISTINCT st.name) AS types,
             collect(DISTINCT ed.name) AS educationLevels,
             collect(DISTINCT ia.name) AS involvementAreas,
             count(DISTINCT a) AS activityCount,
             count(DISTINCT r) AS eventJoinCount,
             count(DISTINCT CASE WHEN r.status = 'Attended' THEN r ELSE NULL END) AS eventAttendRelCount,
             collect(DISTINCT sk.name) AS skills,
             count(DISTINCT refP) AS referredCount,
             count(DISTINCT sr) AS recruitedCount
        RETURN
          lat,
          lon,
          address AS address,
          p.email AS email,
          p.firstName AS firstName,
          p.lastName AS lastName,
          p.age AS age,
          coalesce(p.gender, 'Unspecified') AS gender,
          coalesce(p.timeAvailability, 'Unspecified') AS timeAvailability,
          coalesce(p.about, '') AS about,
          types,
          involvementAreas,
          activityCount,
          eventJoinCount,
          eventAttendRelCount,
          skills,
          educationLevels,
          coalesce(p.eventsAttendedCount, 0) AS eventAttendProp,
          coalesce(p.referralCount, 0) AS referralProp,
          coalesce(p.tasksCompleted, 0) AS tasksCompleted,
          referredCount,
          recruitedCount,
          coalesce(p.effortHours, p.volunteerHours, s.volunteer_hours, s.volunteerHours, 0) AS effortHours,
          coalesce(p.donationTotal, 0) AS donationTotal
        """,
        {},
    )
    if df.empty:
        return df
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])
    df = df[df["lat"].between(-90, 90) & df["lon"].between(-180, 180)]
    df = df[~((df["lat"].abs() < 1e-6) & (df["lon"].abs() < 1e-6))]
    df["timeAvailability"] = df["timeAvailability"].fillna("Unspecified")
    df["about"] = df["about"].fillna("")
    df["address"] = df["address"].fillna("")
    def _format_address_label(row):
        address_value = str(row.get("address") or "").strip()
        if address_value:
            return address_value
        lat = row.get("lat")
        lon = row.get("lon")
        if pd.notna(lat) and pd.notna(lon):
            return f"Lat {lat:.4f}, Lon {lon:.4f}"
        return "Unspecified"

    df["addressLabel"] = df.apply(_format_address_label, axis=1)
    df["involvementAreas"] = df["involvementAreas"].apply(lambda v: v or [])
    df["involvementLabel"] = df["involvementAreas"].apply(_format_list_label)
    df = _enrich_people_core(df)
    df["involvementTitle"] = df["group"].apply(
        lambda value: "Desired involvement" if value == "Supporter" else "Current involvement"
    )
    df["pointSize"] = (6 + df["effortScore"].clip(lower=0) * 0.2).clip(4, 60)
    df["color"] = df["group"].map(
        {"Supporter": [124, 58, 237, 180], "Member": [249, 115, 22, 180]}
    )
    df["color"] = df["color"].apply(
        lambda value: value if isinstance(value, list) else [120, 120, 120, 180]
    )
    df["ratingColor"] = df["rating"].apply(_rating_color)
    return df


def _normalize_column(name: str) -> str:
    return (
        str(name)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace(".", "")
    )


def _get_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    normalized = {_normalize_column(col): col for col in df.columns}
    for cand in candidates:
        key = _normalize_column(cand)
        if key in normalized:
            return normalized[key]
    return None


def _split_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = str(value).split(",")
    cleaned = []
    for item in items:
        text = _clean_text(item)
        if text:
            cleaned.append(text)
    return cleaned


def _build_import_rows(df: pd.DataFrame, default_type: str) -> List[dict]:
    if df.empty:
        return []
    df["age"] = pd.to_numeric(df.get("age"), errors="coerce")
    col_email = _get_column(df, ["email", "primary_email", "e_mail", "e-mail", "email_address"])
    col_email_secondary = _get_column(
        df, ["secondary_email", "alternate_email", "alt_email"]
    )
    if not col_email:
        return []
    col_first = _get_column(df, ["first_name", "firstname", "first"])
    col_last = _get_column(df, ["last_name", "lastname", "last"])
    col_gender = _get_column(df, ["gender", "sex"])
    col_age = _get_column(df, ["age"])
    col_phone = _get_column(df, ["phone", "primary_phone", "mobile"])
    col_phone_secondary = _get_column(df, ["secondary_phone", "alt_phone"])
    col_address = _get_column(df, ["address", "fulladdress", "full_address"])
    col_lat = _get_column(df, ["lat", "latitude"])
    col_lon = _get_column(df, ["lon", "lng", "longitude"])
    col_type = _get_column(df, ["supporter_type", "type", "group"])
    col_effort = _get_column(df, ["effort_hours", "volunteer_hours", "hours", "time_spent"])
    col_events = _get_column(
        df,
        ["events_attended", "events_attended_count", "event_attended", "event_attend_count"],
    )
    col_refs = _get_column(df, ["referral_count", "references", "referrals", "recruits"])
    col_tasks = _get_column(
        df,
        [
            "tasks_completed",
            "tasks_done",
            "tasks_complete",
            "completed_tasks",
            "tasks_count",
            "task_count",
        ],
    )
    col_education = _get_column(df, ["education", "education_level"])
    col_skills = _get_column(df, ["skills", "skill_list", "skill"])
    col_time = _get_column(
        df,
        [
            "time_availability",
            "time_available",
            "time_avail",
            "availability",
            "time",
        ],
    )

    rows = []
    for _, row in df.iterrows():
        email = _clean_text(row.get(col_email))
        if not email and col_email_secondary:
            email = _clean_text(row.get(col_email_secondary))
        if not email:
            continue
        age_val = pd.to_numeric(row.get(col_age), errors="coerce") if col_age else None
        age = (
            int(age_val)
            if age_val is not None and not pd.isna(age_val) and age_val > 0
            else None
        )
        lat_val = pd.to_numeric(row.get(col_lat), errors="coerce") if col_lat else None
        lon_val = pd.to_numeric(row.get(col_lon), errors="coerce") if col_lon else None
        lat = float(lat_val) if lat_val is not None and not pd.isna(lat_val) else None
        lon = float(lon_val) if lon_val is not None and not pd.isna(lon_val) else None
        supporter_type = _clean_text(row.get(col_type)) if col_type else None
        effort_val = pd.to_numeric(row.get(col_effort), errors="coerce") if col_effort else None
        effort_hours = (
            float(effort_val) if effort_val is not None and not pd.isna(effort_val) else None
        )
        events_val = pd.to_numeric(row.get(col_events), errors="coerce") if col_events else None
        events_attended = (
            int(events_val) if events_val is not None and not pd.isna(events_val) else None
        )
        refs_val = pd.to_numeric(row.get(col_refs), errors="coerce") if col_refs else None
        referrals = (
            int(refs_val) if refs_val is not None and not pd.isna(refs_val) else None
        )
        tasks_val = pd.to_numeric(row.get(col_tasks), errors="coerce") if col_tasks else None
        tasks_completed = (
            int(tasks_val) if tasks_val is not None and not pd.isna(tasks_val) else None
        )
        education = _clean_text(row.get(col_education)) if col_education else None
        skills = _split_list(row.get(col_skills)) if col_skills else []
        rows.append(
            {
                "email": email,
                "firstName": _clean_text(row.get(col_first)) if col_first else None,
                "lastName": _clean_text(row.get(col_last)) if col_last else None,
                "gender": _clean_text(row.get(col_gender)) if col_gender else None,
                "age": age,
                "phone": _clean_text(row.get(col_phone))
                if col_phone
                else (_clean_text(row.get(col_phone_secondary)) if col_phone_secondary else None),
                "address": _clean_text(row.get(col_address)) if col_address else None,
                "lat": lat,
                "lon": lon,
                "effortHours": effort_hours,
                "eventsAttendedCount": events_attended,
                "referralCount": referrals,
                "tasksCompleted": tasks_completed,
                "education": education,
                "skills": skills,
                "supporterType": _normalize_supporter_type(supporter_type, default_type),
                "timeAvailability": _clean_text(row.get(col_time)) if col_time else None,
            }
        )
    return rows


def _build_furry_import_rows(df: pd.DataFrame) -> List[dict]:
    if df.empty:
        return []
    col_municipality = _get_column(
        df, ["municipality", "city", "district", "region", "area"]
    )
    col_species = _get_column(df, ["species", "animal", "type", "pet_type"])
    col_name = _get_column(df, ["name", "pet_name"])
    col_gender = _get_column(df, ["gender", "sex"])
    col_age = _get_column(df, ["age", "years"])
    col_neutered = _get_column(df, ["neutered", "sterilized", "spayed"])
    col_breed = _get_column(df, ["breed"])
    col_color = _get_column(df, ["color", "colour"])
    col_chip = _get_column(df, ["chip_number", "chip", "microchip"])
    col_address = _get_column(df, ["address", "location"])
    col_lat = _get_column(df, ["lat", "latitude"])
    col_lon = _get_column(df, ["lon", "lng", "longitude"])
    col_notes = _get_column(df, ["notes", "note", "comment"])

    rows = []
    for _, row in df.iterrows():
        address = _clean_text(row.get(col_address)) if col_address else None
        municipality = (
            _clean_text(row.get(col_municipality)) if col_municipality else None
        ) or _extract_municipality(address)
        species = _normalize_species(row.get(col_species)) if col_species else "Dog"
        chip = _clean_text(row.get(col_chip)) if col_chip else None
        name = _clean_text(row.get(col_name)) if col_name else None
        if not municipality and not address and not chip and not name:
            continue
        furry_id = f"chip-{chip}" if chip else str(uuid4())
        age_val = pd.to_numeric(row.get(col_age), errors="coerce") if col_age else None
        age = int(age_val) if age_val is not None and not pd.isna(age_val) else None
        neutered = _parse_bool(row.get(col_neutered)) if col_neutered else None
        lat_val = pd.to_numeric(row.get(col_lat), errors="coerce") if col_lat else None
        lon_val = pd.to_numeric(row.get(col_lon), errors="coerce") if col_lon else None
        lat = float(lat_val) if lat_val is not None and not pd.isna(lat_val) else None
        lon = float(lon_val) if lon_val is not None and not pd.isna(lon_val) else None
        notes = _clean_text(row.get(col_notes)) if col_notes else None
        rows.append(
            {
                "furryId": furry_id,
                "municipality": municipality,
                "species": species or "Dog",
                "name": name,
                "gender": _clean_text(row.get(col_gender)) if col_gender else None,
                "age": age,
                "neutered": neutered,
                "breed": _clean_text(row.get(col_breed)) if col_breed else None,
                "color": _clean_text(row.get(col_color)) if col_color else None,
                "chipNumber": chip,
                "address": address,
                "lat": lat,
                "lon": lon,
                "notes": notes,
            }
        )
    return rows


def _build_segment_query(filter_spec: SegmentFilter, limit: int):
    clauses = []
    params = {
        "limit": max(10, min(2000, int(limit) if str(limit).isdigit() else 500))
    }

    group = (filter_spec.group or "").strip()
    if group in {"Supporter", "Member"}:
        clauses.append("group = $group")
        params["group"] = group

    time_availability = filter_spec.timeAvailability or []
    if time_availability:
        vals = [str(x) for x in time_availability if str(x).strip()]
        if vals:
            clauses.append("p.timeAvailability IN $timeAvailability")
            params["timeAvailability"] = vals

    tags = filter_spec.tags or []
    if tags:
        vals = [str(x) for x in tags if str(x).strip()]
        if vals:
            clauses.append("any(t IN $tags WHERE t IN tags)")
            params["tags"] = vals

    skills = filter_spec.skills or []
    if skills:
        vals = [str(x) for x in skills if str(x).strip()]
        if vals:
            clauses.append("any(s IN $skills WHERE s IN skills)")
            params["skills"] = vals

    name_contains = (filter_spec.nameContains or "").strip()
    if name_contains:
        clauses.append("toLower(fullName) CONTAINS toLower($nameContains)")
        params["nameContains"] = name_contains

    address_contains = (filter_spec.addressContains or "").strip()
    if address_contains:
        clauses.append("toLower(address) CONTAINS toLower($addressContains)")
        params["addressContains"] = address_contains

    min_effort_val = filter_spec.minEffortHours
    if min_effort_val is not None and min_effort_val > 0:
        clauses.append("effortHours >= $minEffortHours")
        params["minEffortHours"] = float(min_effort_val)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    query = f"""
    MATCH (p:Person)
    OPTIONAL MATCH (p)-[:LIVES_AT]->(addr:Address)
    OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(st:SupporterType)
    WITH p, addr, collect(DISTINCT st.name) AS types
    WITH p, addr,
      (trim(coalesce(p.firstName,'') + ' ' + coalesce(p.lastName,''))) AS fullName,
      CASE WHEN any(x IN types WHERE toLower(x) CONTAINS 'member') THEN 'Member' ELSE 'Supporter' END AS group
    OPTIONAL MATCH (p)-[:HAS_TAG]->(tag:Tag)
    WITH p, addr, fullName, group, collect(DISTINCT tag.name) AS tags
    OPTIONAL MATCH (p)-[:CAN_CONTRIBUTE_WITH]->(sk:Skill)
    WITH p, addr, fullName, group, tags, collect(DISTINCT sk.name) AS skills,
         coalesce(p.effortHours, 0.0) AS effortHours,
         coalesce(p.address, addr.fullAddress, '') AS address
    {where}
    RETURN
      CASE WHEN fullName = '' THEN p.email ELSE fullName END AS fullName,
      p.email AS email,
      group AS group,
      coalesce(p.timeAvailability, 'Unspecified') AS timeAvailability,
      address AS address,
      effortHours AS effortHours,
      tags,
      skills
    ORDER BY effortHours DESC
    LIMIT $limit
    """
    return query, params


def _send_whatsapp_group_message(group: dict, message: str, source: str):
    webhook_url = str(os.getenv("WHATSAPP_GROUP_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        raise HTTPException(status_code=400, detail="WhatsApp webhook not configured.")

    if not message.strip():
        raise HTTPException(status_code=400, detail="Message is empty.")

    payload = {
        "platform": "whatsapp",
        "channel": "group",
        "source": source or "outreach_page",
        "group": {
            "groupId": group.get("groupId"),
            "name": group.get("name"),
            "inviteLink": group.get("inviteLink"),
        },
        "message": message,
    }
    headers = {"Content-Type": "application/json"}
    token = str(os.getenv("WHATSAPP_GROUP_WEBHOOK_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.post(webhook_url, json=payload, headers=headers, timeout=20)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Webhook rejected request ({response.status_code}): {response.text}",
        )
    return {"ok": True}


@router.get("/summary", response_model=CrmSummaryOut)
def crm_summary():
    df = _load_supporter_summary_df()
    if df.empty:
        return {
            "total_people": 0,
            "supporters": 0,
            "members": 0,
            "missing_age": 0,
            "missing_gender": 0,
            "missing_time_availability": 0,
        }
    total_people = int(len(df))
    supporters = int((df["group"] == "Supporter").sum())
    members = int((df["group"] == "Member").sum())
    missing_age = int(df["age"].isna().sum()) if "age" in df.columns else total_people
    missing_gender = (
        int(df["gender"].isna().sum()) if "gender" in df.columns else total_people
    )
    if "timeAvailability" in df.columns:
        missing_time = int(
            (df["timeAvailability"].fillna("Unspecified") == "Unspecified").sum()
        )
    else:
        missing_time = total_people
    return {
        "total_people": total_people,
        "supporters": supporters,
        "members": members,
        "missing_age": missing_age,
        "missing_gender": missing_gender,
        "missing_time_availability": missing_time,
    }


@router.get("/people", response_model=List[PersonOut])
def list_people(
    group: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Search by name or email"),
    limit: int = Query(25, ge=1, le=200),
):
    driver = get_driver()
    search = (q or "").strip()
    query = """
    MATCH (p:Person)
    OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(st:SupporterType)
    WITH p, collect(DISTINCT st.name) AS types
    WITH p,
      trim(coalesce(p.firstName, '') + ' ' + coalesce(p.lastName, '')) AS fullName,
      CASE WHEN any(x IN types WHERE toLower(x) CONTAINS 'member') THEN 'Member' ELSE 'Supporter' END AS grp
    WHERE ($group IS NULL OR grp = $group)
      AND (
        $search = ''
        OR toLower(p.email) CONTAINS toLower($search)
        OR toLower(fullName) CONTAINS toLower($search)
      )
    RETURN
      CASE WHEN fullName = '' THEN p.email ELSE fullName END AS fullName,
      p.email AS email,
      grp AS group,
      p.phone AS phone,
      coalesce(p.timeAvailability, 'Unspecified') AS timeAvailability
    ORDER BY fullName
    LIMIT $limit
    """
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            query,
            {"group": group, "limit": int(limit), "search": search},
        )
    results = []
    for record in records:
        data = record.data()
        results.append(
            {
                "email": data.get("email") or "",
                "fullName": data.get("fullName") or "",
                "group": data.get("group") or "Supporter",
                "phone": data.get("phone"),
                "timeAvailability": data.get("timeAvailability"),
            }
        )
    return results


@router.get("/people/summary")
def list_people_summary(
    group: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    sort: Optional[str] = Query("fullName"),
    limit: int = Query(1000, ge=10, le=5000),
):
    df = _load_supporter_summary_df()
    if df.empty:
        return []
    if group in {"Supporter", "Member"}:
        df = df[df["group"] == group]
    search = (q or "").strip().lower()
    if search:
        df = df[
            df["fullName"].astype(str).str.lower().str.contains(search, na=False)
            | df["email"].astype(str).str.lower().str.contains(search, na=False)
        ]
    sort_map = {
        "effortScore": ("effortScore", False),
        "effortHours": ("effortHours", False),
        "eventAttendCount": ("eventAttendCount", False),
        "referralCount": ("referralCount", False),
        "joinCount": ("joinCount", False),
        "rating": ("rating", False),
        "fullName": ("fullName", True),
    }
    if sort in sort_map:
        col, asc = sort_map[sort]
        if col in df.columns:
            df = df.sort_values(col, ascending=asc)
    df = df.head(int(limit))
    df = df.replace([np.inf, -np.inf], None)
    df = df.replace({np.nan: None})
    df = df.where(pd.notnull(df), None)
    return df.to_dict(orient="records")


@router.get("/people/{email}", response_model=PersonProfileOut)
def get_person_profile(email: str):
    profile = _load_profile(email)
    if not profile:
        raise HTTPException(status_code=404, detail="Person not found")
    return profile


@router.patch("/people/{email}", response_model=PersonProfileOut)
def update_person_profile(email: str, payload: PersonProfileUpdate):
    existing = _load_profile(email)
    if not existing:
        raise HTTPException(status_code=404, detail="Person not found")
    updated = {
        "firstName": payload.firstName if payload.firstName is not None else existing.get("firstName"),
        "lastName": payload.lastName if payload.lastName is not None else existing.get("lastName"),
        "phone": payload.phone if payload.phone is not None else existing.get("phone"),
        "gender": payload.gender if payload.gender is not None else existing.get("gender"),
        "age": payload.age if payload.age is not None else existing.get("age"),
        "timeAvailability": payload.timeAvailability
        if payload.timeAvailability is not None
        else existing.get("timeAvailability"),
        "about": payload.about if payload.about is not None else existing.get("about"),
        "agreesWithManifesto": payload.agreesWithManifesto
        if payload.agreesWithManifesto is not None
        else existing.get("agreesWithManifesto"),
        "interestedInMembership": payload.interestedInMembership
        if payload.interestedInMembership is not None
        else existing.get("interestedInMembership"),
        "facebookGroupMember": payload.facebookGroupMember
        if payload.facebookGroupMember is not None
        else existing.get("facebookGroupMember"),
    }
    driver = get_driver()
    query = """
    MATCH (p:Person {email: $email})
    SET p.firstName = $firstName,
        p.lastName = $lastName,
        p.phone = $phone,
        p.gender = $gender,
        p.age = $age,
        p.timeAvailability = $timeAvailability,
        p.about = $about,
        p.agreesWithManifesto = $agreesWithManifesto,
        p.interestedInMembership = $interestedInMembership,
        p.facebookGroupMember = $facebookGroupMember
    """
    with _db_session(driver) as session:
        _execute_write(session, query, {"email": email, **updated})
    profile = _load_profile(email)
    return profile or updated


@router.get("/tasks", response_model=List[TaskOut])
def list_tasks(
    status: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
    group: Optional[str] = Query(None),
    limit: int = Query(300, ge=10, le=1000),
):
    driver = get_driver()
    query = """
    MATCH (p:Person)-[:HAS_TASK]->(t:Task)
    OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(st:SupporterType)
    WITH p, t, collect(DISTINCT st.name) AS types
    WITH p, t,
      CASE WHEN any(x IN types WHERE toLower(x) CONTAINS 'member') THEN 'Member' ELSE 'Supporter' END AS group
    WHERE ($status IS NULL OR t.status = $status)
      AND ($email IS NULL OR p.email = $email)
      AND ($group IS NULL OR group = $group)
    RETURN
      t.taskId AS taskId,
      t.title AS title,
      coalesce(t.description, '') AS description,
      coalesce(t.status, 'Open') AS status,
      coalesce(t.dueDate, '') AS dueDate,
      coalesce(p.firstName, '') AS firstName,
      coalesce(p.lastName, '') AS lastName,
      p.email AS email,
      group AS group,
      toString(t.createdAt) AS createdAt,
      toString(t.updatedAt) AS updatedAt
    ORDER BY
      CASE WHEN t.status = 'Done' THEN 1 WHEN t.status = 'Cancelled' THEN 2 ELSE 0 END,
      coalesce(t.dueDate, '9999-12-31') ASC,
      t.createdAt DESC
    LIMIT $limit
    """
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            query,
            {"status": status, "email": email, "group": group, "limit": int(limit)},
        )
    return [record.data() for record in records]


@router.post("/tasks", response_model=TaskOut)
def create_task(payload: TaskCreate):
    status = payload.status if payload.status in TASK_STATUSES else "Open"
    driver = get_driver()
    query = """
    MATCH (p:Person {email: $email})
    CREATE (t:Task {
      taskId: randomUUID(),
      title: $title,
      description: $description,
      status: $status,
      dueDate: $dueDate,
      createdAt: datetime(),
      updatedAt: datetime()
    })
    MERGE (p)-[:HAS_TASK]->(t)
    RETURN
      t.taskId AS taskId,
      t.title AS title,
      coalesce(t.description, '') AS description,
      coalesce(t.status, 'Open') AS status,
      coalesce(t.dueDate, '') AS dueDate,
      coalesce(p.firstName, '') AS firstName,
      coalesce(p.lastName, '') AS lastName,
      p.email AS email,
      'Supporter' AS group,
      toString(t.createdAt) AS createdAt,
      toString(t.updatedAt) AS updatedAt
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "email": payload.email,
                "title": payload.title,
                "description": payload.description or "",
                "status": status,
                "dueDate": payload.dueDate or "",
            },
        )
    if not records:
        raise HTTPException(status_code=400, detail="Task could not be created")
    return records[0].data()


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task_status(task_id: str, payload: TaskStatusUpdate):
    if payload.status not in TASK_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    driver = get_driver()
    query = """
    MATCH (p:Person)-[:HAS_TASK]->(t:Task {taskId: $taskId})
    SET t.status = $status,
        t.updatedAt = datetime()
    RETURN
      t.taskId AS taskId,
      t.title AS title,
      coalesce(t.description, '') AS description,
      coalesce(t.status, 'Open') AS status,
      coalesce(t.dueDate, '') AS dueDate,
      coalesce(p.firstName, '') AS firstName,
      coalesce(p.lastName, '') AS lastName,
      p.email AS email,
      'Supporter' AS group,
      toString(t.createdAt) AS createdAt,
      toString(t.updatedAt) AS updatedAt
    """
    with _db_session(driver) as session:
        records = _execute_write(session, query, {"taskId": task_id, "status": payload.status})
    if not records:
        raise HTTPException(status_code=404, detail="Task not found")
    return records[0].data()


@router.post("/tasks/bulk")
def bulk_create_tasks(payload: TaskBulkCreate):
    cleaned = []
    for row in payload.rows or []:
        email = (row.email or "").strip()
        title = (row.title or "").strip()
        if not email or not title:
            continue
        status = row.status if row.status in TASK_STATUSES else "Open"
        cleaned.append(
            {
                "email": email,
                "title": title,
                "description": row.description or "",
                "status": status,
                "dueDate": row.dueDate or "",
            }
        )
    if not cleaned:
        raise HTTPException(status_code=400, detail="No valid tasks provided")
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            UNWIND $rows AS row
            MATCH (p:Person {email: row.email})
            CREATE (t:Task {
              taskId: randomUUID(),
              title: row.title,
              description: row.description,
              status: row.status,
              dueDate: row.dueDate,
              createdAt: datetime(),
              updatedAt: datetime()
            })
            MERGE (p)-[:HAS_TASK]->(t)
            """,
            {"rows": cleaned},
        )
    return {"created": len(cleaned)}


@router.get("/segments", response_model=List[SegmentOut])
def list_segments():
    driver = get_driver()
    query = """
    MATCH (s:Segment)
    RETURN
      s.segmentId AS segmentId,
      s.name AS name,
      coalesce(s.description,'') AS description,
      toString(s.updatedAt) AS updatedAt
    ORDER BY s.updatedAt DESC
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query)
    return [record.data() for record in records]


@router.post("/segments", response_model=SegmentOut)
def create_segment(payload: SegmentCreate):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Segment name is required")
    filter_json = json.dumps(payload.filterSpec.dict(), ensure_ascii=False)
    driver = get_driver()
    query = """
    MERGE (s:Segment {name: $name})
    ON CREATE SET s.segmentId = randomUUID(), s.createdAt = datetime()
    SET s.description = $description,
        s.filterJson = $filterJson,
        s.updatedAt = datetime()
    RETURN
      s.segmentId AS segmentId,
      s.name AS name,
      coalesce(s.description,'') AS description,
      toString(s.updatedAt) AS updatedAt
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {"name": payload.name.strip(), "description": payload.description or "", "filterJson": filter_json},
        )
    if not records:
        raise HTTPException(status_code=500, detail="Segment could not be created")
    return records[0].data()


@router.delete("/segments/{segment_id}")
def delete_segment(segment_id: str):
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            "MATCH (s:Segment {segmentId: $id}) DETACH DELETE s",
            {"id": segment_id},
        )
    return {"deleted": True, "segment_id": segment_id}


@router.post("/segments/run", response_model=List[SegmentPersonOut])
def run_segment(payload: SegmentRunRequest):
    query, params = _build_segment_query(payload.filterSpec, payload.limit or 500)
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_read(session, query, params)
    return [record.data() for record in records]


@router.get("/segments/{segment_id}/run", response_model=List[SegmentPersonOut])
def run_saved_segment(segment_id: str, limit: int = Query(500, ge=10, le=2000)):
    driver = get_driver()
    query = """
    MATCH (s:Segment {segmentId: $id})
    RETURN coalesce(s.filterJson, '{}') AS filterJson
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query, {"id": segment_id})
    if not records:
        raise HTTPException(status_code=404, detail="Segment not found")
    try:
        filter_spec = json.loads(records[0].get("filterJson") or "{}")
    except Exception:
        filter_spec = {}
    query, params = _build_segment_query(SegmentFilter(**filter_spec), limit)
    with _db_session(driver) as session:
        rows = _execute_read(session, query, params)
    return [record.data() for record in rows]


@router.get("/whatsapp-groups", response_model=List[WhatsAppGroupOut])
def list_whatsapp_groups():
    driver = get_driver()
    query = """
    MATCH (g:WhatsAppGroup)
    RETURN
      g.groupId AS groupId,
      g.name AS name,
      coalesce(g.inviteLink, '') AS inviteLink,
      coalesce(g.notes, '') AS notes,
      toString(g.updatedAt) AS updatedAt
    ORDER BY g.updatedAt DESC
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query)
    return [record.data() for record in records]


@router.post("/whatsapp-groups", response_model=WhatsAppGroupOut)
def upsert_whatsapp_group(payload: WhatsAppGroupCreate):
    if not payload.name.strip() or not payload.inviteLink.strip():
        raise HTTPException(status_code=400, detail="Name and inviteLink are required")
    driver = get_driver()
    query = """
    MERGE (g:WhatsAppGroup {name: $name})
    ON CREATE SET g.groupId = randomUUID(), g.createdAt = datetime()
    SET g.inviteLink = $inviteLink,
        g.notes = $notes,
        g.updatedAt = datetime()
    RETURN
      g.groupId AS groupId,
      g.name AS name,
      coalesce(g.inviteLink, '') AS inviteLink,
      coalesce(g.notes, '') AS notes,
      toString(g.updatedAt) AS updatedAt
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {"name": payload.name.strip(), "inviteLink": payload.inviteLink.strip(), "notes": payload.notes or ""},
        )
    if not records:
        raise HTTPException(status_code=500, detail="WhatsApp group could not be saved")
    return records[0].data()


@router.delete("/whatsapp-groups/{group_id}")
def delete_whatsapp_group(group_id: str):
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            "MATCH (g:WhatsAppGroup {groupId: $groupId}) DETACH DELETE g",
            {"groupId": group_id},
        )
    return {"deleted": True, "group_id": group_id}


@router.post("/whatsapp-groups/{group_id}/send")
def send_whatsapp_group_message(group_id: str, payload: WhatsAppMessage):
    driver = get_driver()
    query = """
    MATCH (g:WhatsAppGroup {groupId: $groupId})
    RETURN g.groupId AS groupId, g.name AS name, g.inviteLink AS inviteLink
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query, {"groupId": group_id})
    if not records:
        raise HTTPException(status_code=404, detail="WhatsApp group not found")
    group = records[0].data()
    message = payload.message.strip()
    if payload.appendInvite and group.get("inviteLink"):
        message = f"{message}\n\nGroup link: {group.get('inviteLink')}".strip()
    return _send_whatsapp_group_message(group, message, payload.source or "outreach_page")


@router.post("/people", response_model=PersonProfileOut)
def upsert_person(payload: PersonUpsert):
    email = _clean_text(payload.email)
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    supporter_type = _normalize_supporter_type(payload.supporterType, "Supporter")
    driver = get_driver()
    query = """
    MERGE (p:Person {email: $email})
    ON CREATE SET p.personId = randomUUID(), p.createdAt = datetime()
    SET p.firstName = $firstName,
        p.lastName = $lastName,
        p.gender = $gender,
        p.age = $age,
        p.phone = $phone,
        p.lat = $lat,
        p.lon = $lon,
        p.timeAvailability = coalesce($timeAvailability, p.timeAvailability),
        p.effortHours = coalesce($effortHours, p.effortHours),
        p.eventsAttendedCount = coalesce($eventsAttendedCount, p.eventsAttendedCount),
        p.referralCount = coalesce($referralCount, p.referralCount),
        p.tasksCompleted = coalesce($tasksCompleted, p.tasksCompleted)
    WITH p
    MERGE (st:SupporterType {name: $supporterType})
    MERGE (p)-[:CLASSIFIED_AS]->(st)
    WITH p
    FOREACH (_ IN CASE WHEN $address IS NULL OR $address = '' THEN [] ELSE [1] END |
        MERGE (a:Address {fullAddress: $address})
        ON CREATE SET a.latitude = $lat, a.longitude = $lon
        ON MATCH SET a.latitude = coalesce($lat, a.latitude),
                    a.longitude = coalesce($lon, a.longitude)
        MERGE (p)-[:LIVES_AT]->(a)
    )
    """
    with _db_session(driver) as session:
        _execute_write(
            session,
            query,
            {
                "email": email,
                "firstName": _clean_text(payload.firstName),
                "lastName": _clean_text(payload.lastName),
                "gender": _clean_text(payload.gender),
                "age": payload.age,
                "phone": _clean_text(payload.phone),
                "lat": payload.lat,
                "lon": payload.lon,
                "effortHours": payload.effortHours,
                "eventsAttendedCount": payload.eventsAttendedCount,
                "referralCount": payload.referralCount,
                "tasksCompleted": payload.tasksCompleted,
                "supporterType": supporter_type,
                "address": _clean_text(payload.address),
                "timeAvailability": _clean_text(payload.timeAvailability),
            },
        )
    profile = _load_profile(email)
    return profile or {"email": email}


@router.post("/people/bulk")
def bulk_upsert_people(payload: PeopleBulkImport):
    rows = payload.rows or []
    cleaned = []
    for row in rows:
        email = _clean_text(row.email)
        if not email:
            continue
        cleaned.append(
            {
                "email": email,
                "firstName": _clean_text(row.firstName),
                "lastName": _clean_text(row.lastName),
                "gender": _clean_text(row.gender),
                "age": row.age,
                "phone": _clean_text(row.phone),
                "address": _clean_text(row.address),
                "lat": row.lat,
                "lon": row.lon,
                "effortHours": row.effortHours,
                "eventsAttendedCount": row.eventsAttendedCount,
                "referralCount": row.referralCount,
                "tasksCompleted": row.tasksCompleted,
                "education": _clean_text(row.education),
                "skills": [v for v in (row.skills or []) if _clean_text(v)],
                "supporterType": _normalize_supporter_type(
                    row.supporterType, payload.defaultType or "Supporter"
                ),
                "timeAvailability": _clean_text(row.timeAvailability),
            }
        )
    if not cleaned:
        raise HTTPException(status_code=400, detail="No valid rows provided")
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            UNWIND $rows AS row
            WITH row
            WHERE row.email IS NOT NULL AND trim(row.email) <> ""
            MERGE (p:Person {email: row.email})
            ON CREATE SET p.personId = randomUUID(), p.createdAt = datetime()
            SET p.firstName = row.firstName,
                p.lastName = row.lastName,
                p.gender = row.gender,
                p.age = row.age,
                p.phone = row.phone,
                p.lat = row.lat,
                p.lon = row.lon,
                p.effortHours = coalesce(row.effortHours, p.effortHours),
                p.eventsAttendedCount = coalesce(row.eventsAttendedCount, p.eventsAttendedCount),
                p.referralCount = coalesce(row.referralCount, p.referralCount),
                p.tasksCompleted = coalesce(row.tasksCompleted, p.tasksCompleted),
                p.timeAvailability = coalesce(row.timeAvailability, p.timeAvailability)
            WITH p, row
            FOREACH (_ IN CASE WHEN row.education IS NULL OR row.education = '' THEN [] ELSE [1] END |
                MERGE (ed:EducationLevel {name: row.education})
                MERGE (p)-[:HAS_EDUCATION]->(ed)
            )
            FOREACH (skill IN coalesce(row.skills, []) |
                MERGE (sk:Skill {name: skill})
                MERGE (p)-[:CAN_CONTRIBUTE_WITH]->(sk)
            )
            MERGE (st:SupporterType {name: coalesce(row.supporterType, 'Supporter')})
            MERGE (p)-[:CLASSIFIED_AS]->(st)
            WITH p, row
            FOREACH (_ IN CASE WHEN row.address IS NULL OR row.address = '' THEN [] ELSE [1] END |
                MERGE (a:Address {fullAddress: row.address})
                ON CREATE SET a.latitude = row.lat, a.longitude = row.lon
                ON MATCH SET a.latitude = coalesce(row.lat, a.latitude),
                            a.longitude = coalesce(row.lon, a.longitude)
                MERGE (p)-[:LIVES_AT]->(a)
            )
            """,
            {"rows": cleaned},
        )
    return {"created": len(cleaned)}


@router.post("/people/import")
async def import_people_file(
    file: UploadFile = File(...), default_type: str = Query("Supporter")
):
    try:
        content = await file.read()
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read CSV: {exc}")
    rows = _build_import_rows(df, default_type)
    if not rows:
        raise HTTPException(status_code=400, detail="No valid rows found in CSV")
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            UNWIND $rows AS row
            WITH row
            WHERE row.email IS NOT NULL AND trim(row.email) <> ""
            MERGE (p:Person {email: row.email})
            ON CREATE SET p.personId = randomUUID(), p.createdAt = datetime()
            SET p.firstName = row.firstName,
                p.lastName = row.lastName,
                p.gender = row.gender,
                p.age = row.age,
                p.phone = row.phone,
                p.lat = row.lat,
                p.lon = row.lon,
                p.effortHours = coalesce(row.effortHours, p.effortHours),
                p.eventsAttendedCount = coalesce(row.eventsAttendedCount, p.eventsAttendedCount),
                p.referralCount = coalesce(row.referralCount, p.referralCount),
                p.tasksCompleted = coalesce(row.tasksCompleted, p.tasksCompleted),
                p.timeAvailability = coalesce(row.timeAvailability, p.timeAvailability)
            WITH p, row
            FOREACH (_ IN CASE WHEN row.education IS NULL OR row.education = '' THEN [] ELSE [1] END |
                MERGE (ed:EducationLevel {name: row.education})
                MERGE (p)-[:HAS_EDUCATION]->(ed)
            )
            FOREACH (skill IN coalesce(row.skills, []) |
                MERGE (sk:Skill {name: skill})
                MERGE (p)-[:CAN_CONTRIBUTE_WITH]->(sk)
            )
            MERGE (st:SupporterType {name: coalesce(row.supporterType, 'Supporter')})
            MERGE (p)-[:CLASSIFIED_AS]->(st)
            WITH p, row
            FOREACH (_ IN CASE WHEN row.address IS NULL OR row.address = '' THEN [] ELSE [1] END |
                MERGE (a:Address {fullAddress: row.address})
                ON CREATE SET a.latitude = row.lat, a.longitude = row.lon
                ON MATCH SET a.latitude = coalesce(row.lat, a.latitude),
                            a.longitude = coalesce(row.lon, a.longitude)
                MERGE (p)-[:LIVES_AT]->(a)
            )
            """,
            {"rows": rows},
        )
    return {"created": len(rows)}


@router.get("/dashboard", response_model=DashboardOut)
def crm_dashboard():
    df = _load_supporter_summary_df()
    total_people = int(len(df))
    supporters = int((df["group"] == "Supporter").sum()) if not df.empty else 0
    members = int((df["group"] == "Member").sum()) if not df.empty else 0
    avg_effort = float(df["effortScore"].mean()) if total_people else 0.0

    group_counts = (
        df["group"]
        .value_counts()
        .rename_axis("group")
        .reset_index(name="count")
        .to_dict(orient="records")
        if not df.empty
        else []
    )
    gender_counts = (
        df["gender"]
        .fillna("Unspecified")
        .value_counts()
        .rename_axis("gender")
        .reset_index(name="count")
        .to_dict(orient="records")
        if not df.empty
        else []
    )
    rating_counts = (
        df["rating"]
        .value_counts()
        .sort_index()
        .rename_axis("rating")
        .reset_index(name="count")
        .to_dict(orient="records")
        if not df.empty
        else []
    )

    manifesto_df = _query_df(
        """
        MATCH (p:Person)
        RETURN CASE
            WHEN p.agreesWithManifesto IS NULL THEN 'Unspecified'
            WHEN p.agreesWithManifesto THEN 'Yes'
            ELSE 'No'
        END AS agrees, count(p) AS count
        """
    )
    membership_df = _query_df(
        """
        MATCH (p:Person)
        RETURN CASE
            WHEN p.interestedInMembership IS NULL THEN 'Unspecified'
            WHEN p.interestedInMembership THEN 'Yes'
            ELSE 'No'
        END AS interested, count(p) AS count
        """
    )
    facebook_df = _query_df(
        """
        MATCH (p:Person)
        RETURN CASE
            WHEN p.facebookGroupMember IS NULL THEN 'Unspecified'
            WHEN p.facebookGroupMember THEN 'Yes'
            ELSE 'No'
        END AS facebook, count(p) AS count
        """
    )
    time_df = _query_df(
        """
        MATCH (p:Person)
        RETURN coalesce(p.timeAvailability,'Unspecified') AS availability, count(p) AS count
        """
    )
    involve_df = _query_df(
        """
        MATCH (p:Person)-[:INTERESTED_IN]->(ia:InvolvementArea)
        RETURN ia.name AS area, count(p) AS count
        ORDER BY count DESC
        LIMIT 10
        """
    )
    skills_df = _query_df(
        """
        MATCH (p:Person)-[:CAN_CONTRIBUTE_WITH]->(s:Skill)
        RETURN s.name AS skill, count(p) AS count
        ORDER BY count DESC
        LIMIT 10
        """
    )

    task_feed = _query_df(
        """
        MATCH (p:Person)-[:HAS_TASK]->(t:Task)
        OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(st:SupporterType)
        WITH p, t, collect(DISTINCT st.name) AS types
        WITH p, t,
          CASE WHEN any(x IN types WHERE toLower(x) CONTAINS 'member') THEN 'Member' ELSE 'Supporter' END AS group
        WHERE t.status = 'Open'
        RETURN
          t.taskId AS taskId,
          t.title AS title,
          coalesce(t.dueDate, '') AS dueDate,
          coalesce(p.firstName, '') AS firstName,
          coalesce(p.lastName, '') AS lastName,
          p.email AS email,
          group AS group,
          toString(t.updatedAt) AS updatedAt
        ORDER BY t.updatedAt DESC
        LIMIT 15
        """
    ).to_dict(orient="records")

    return {
        "metrics": {
            "total_people": total_people,
            "supporters": supporters,
            "members": members,
            "avg_effort": avg_effort,
        },
        "charts": {
            "groupCounts": group_counts,
            "genderCounts": gender_counts,
            "ratingCounts": rating_counts,
            "manifesto": manifesto_df.to_dict(orient="records") if not manifesto_df.empty else [],
            "membership": membership_df.to_dict(orient="records") if not membership_df.empty else [],
            "facebook": facebook_df.to_dict(orient="records") if not facebook_df.empty else [],
            "timeAvailability": time_df.to_dict(orient="records") if not time_df.empty else [],
            "involvement": involve_df.to_dict(orient="records") if not involve_df.empty else [],
            "skills": skills_df.to_dict(orient="records") if not skills_df.empty else [],
            "taskFeed": task_feed,
        },
    }


@router.get("/map", response_model=List[MapPersonOut])
def crm_map_data():
    df = _load_map_data_df()
    if df.empty:
        return []
    df = df.where(pd.notnull(df), None)
    return df.to_dict(orient="records")


@router.get("/distinct-values")
def get_distinct_values(label: str, prop: str = "name"):
    allowed = {"Tag", "Skill", "EducationLevel", "InvolvementArea", "SupporterType"}
    if label not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported label")
    query = f"""
    MATCH (n:{label})
    WHERE n.{prop} IS NOT NULL
    RETURN DISTINCT n.{prop} AS value
    ORDER BY value
    """
    df = _query_df(query)
    if df.empty or "value" not in df.columns:
        return []
    return [str(v) for v in df["value"].dropna().tolist() if str(v).strip()]


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            "MATCH (t:Task {taskId: $taskId}) DETACH DELETE t",
            {"taskId": task_id},
        )
    return {"deleted": True, "task_id": task_id}


@router.get("/campaigns", response_model=List[CampaignOut])
def list_campaigns(limit: int = Query(200, ge=10, le=1000)):
    df = _query_df(
        """
        MATCH (c:Campaign)
        RETURN
          c.campaignId AS campaignId,
          c.name AS name,
          coalesce(c.topic, '') AS topic,
          coalesce(c.objective, '') AS objective,
          coalesce(c.status, 'Planned') AS status,
          coalesce(c.startDate, '') AS startDate,
          coalesce(c.endDate, '') AS endDate,
          coalesce(c.owner, '') AS owner,
          coalesce(c.targetGroup, '') AS targetGroup,
          coalesce(c.goal, 0) AS goal,
          coalesce(c.notes, '') AS notes,
          coalesce(c.legislationText, '') AS legislationText,
          coalesce(c.manifestoText, '') AS manifestoText,
          coalesce(c.expertPrompt, '') AS expertPrompt,
          coalesce(c.consensusStatements, []) AS consensusStatements,
          coalesce(c.polarizationStatements, []) AS polarizationStatements,
          coalesce(c.deliberationConversationId, '') AS deliberationConversationId
        ORDER BY c.createdAt DESC
        LIMIT $limit
        """,
        {"limit": int(limit)},
    )
    return df.to_dict(orient="records") if not df.empty else []


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: str):
    df = _query_df(
        """
        MATCH (c:Campaign {campaignId: $campaignId})
        RETURN
          c.campaignId AS campaignId,
          c.name AS name,
          coalesce(c.topic, '') AS topic,
          coalesce(c.objective, '') AS objective,
          coalesce(c.status, 'Planned') AS status,
          coalesce(c.startDate, '') AS startDate,
          coalesce(c.endDate, '') AS endDate,
          coalesce(c.owner, '') AS owner,
          coalesce(c.targetGroup, '') AS targetGroup,
          coalesce(c.goal, 0) AS goal,
          coalesce(c.notes, '') AS notes,
          coalesce(c.legislationText, '') AS legislationText,
          coalesce(c.manifestoText, '') AS manifestoText,
          coalesce(c.expertPrompt, '') AS expertPrompt,
          coalesce(c.consensusStatements, []) AS consensusStatements,
          coalesce(c.polarizationStatements, []) AS polarizationStatements,
          coalesce(c.deliberationConversationId, '') AS deliberationConversationId
        LIMIT 1
        """,
        {"campaignId": _clean_text(campaign_id)},
    )
    if df.empty:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return df.iloc[0].to_dict()


@router.post("/campaigns", response_model=CampaignOut)
def create_campaign(payload: CampaignCreate):
    name = _clean_text(payload.name)
    if not name:
        raise HTTPException(status_code=400, detail="Campaign name is required")
    status = _clean_text(payload.status) or "Planned"
    if status not in CAMPAIGN_STATUSES:
        status = "Planned"
    campaign_id = str(uuid4())
    query = """
    CREATE (c:Campaign {
      campaignId: $campaignId,
      name: $name,
      topic: $topic,
      objective: $objective,
      status: $status,
      startDate: $startDate,
      endDate: $endDate,
      owner: $owner,
      targetGroup: $targetGroup,
      goal: $goal,
      notes: $notes,
      legislationText: $legislationText,
      manifestoText: $manifestoText,
      expertPrompt: $expertPrompt,
      consensusStatements: $consensusStatements,
      polarizationStatements: $polarizationStatements,
      deliberationConversationId: $deliberationConversationId,
      createdAt: datetime(),
      updatedAt: datetime()
    })
    RETURN
      c.campaignId AS campaignId,
      c.name AS name,
      coalesce(c.topic, '') AS topic,
      coalesce(c.objective, '') AS objective,
      coalesce(c.status, 'Planned') AS status,
      coalesce(c.startDate, '') AS startDate,
      coalesce(c.endDate, '') AS endDate,
      coalesce(c.owner, '') AS owner,
      coalesce(c.targetGroup, '') AS targetGroup,
      coalesce(c.goal, 0) AS goal,
      coalesce(c.notes, '') AS notes,
      coalesce(c.legislationText, '') AS legislationText,
      coalesce(c.manifestoText, '') AS manifestoText,
      coalesce(c.expertPrompt, '') AS expertPrompt,
      coalesce(c.consensusStatements, []) AS consensusStatements,
      coalesce(c.polarizationStatements, []) AS polarizationStatements,
      coalesce(c.deliberationConversationId, '') AS deliberationConversationId
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "campaignId": campaign_id,
                "name": name,
                "topic": _clean_text(payload.topic),
                "objective": _clean_text(payload.objective),
                "status": status,
                "startDate": _clean_text(payload.startDate),
                "endDate": _clean_text(payload.endDate),
                "owner": _clean_text(payload.owner),
                "targetGroup": _clean_text(payload.targetGroup),
                "goal": payload.goal or 0,
                "notes": _clean_text(payload.notes),
                "legislationText": _clean_text(payload.legislationText),
                "manifestoText": _clean_text(payload.manifestoText),
                "expertPrompt": _clean_text(payload.expertPrompt),
                "consensusStatements": [],
                "polarizationStatements": [],
                "deliberationConversationId": "",
            },
        )
    if not records:
        raise HTTPException(status_code=500, detail="Campaign could not be created")
    return records[0].data()


@router.post("/campaigns/{campaign_id}/analysis", response_model=CampaignOut)
def analyze_campaign(campaign_id: str, payload: CampaignAnalysisRequest):
    campaign_id = _clean_text(campaign_id)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    analysis = _generate_campaign_analysis(
        payload.topic,
        payload.legislationText,
        payload.manifestoText,
        payload.expertPrompt,
    )
    driver = get_driver()
    query = """
    MATCH (c:Campaign {campaignId: $campaignId})
    SET c.topic = $topic,
        c.legislationText = $legislationText,
        c.manifestoText = $manifestoText,
        c.expertPrompt = $expertPrompt,
        c.consensusStatements = $consensusStatements,
        c.polarizationStatements = $polarizationStatements,
        c.updatedAt = datetime()
    RETURN
      c.campaignId AS campaignId,
      c.name AS name,
      coalesce(c.topic, '') AS topic,
      coalesce(c.objective, '') AS objective,
      coalesce(c.status, 'Planned') AS status,
      coalesce(c.startDate, '') AS startDate,
      coalesce(c.endDate, '') AS endDate,
      coalesce(c.owner, '') AS owner,
      coalesce(c.targetGroup, '') AS targetGroup,
      coalesce(c.goal, 0) AS goal,
      coalesce(c.notes, '') AS notes,
      coalesce(c.legislationText, '') AS legislationText,
      coalesce(c.manifestoText, '') AS manifestoText,
      coalesce(c.expertPrompt, '') AS expertPrompt,
      coalesce(c.consensusStatements, []) AS consensusStatements,
      coalesce(c.polarizationStatements, []) AS polarizationStatements,
      coalesce(c.deliberationConversationId, '') AS deliberationConversationId
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "campaignId": campaign_id,
                "topic": _clean_text(payload.topic),
                "legislationText": _clean_text(payload.legislationText),
                "manifestoText": _clean_text(payload.manifestoText),
                "expertPrompt": _clean_text(payload.expertPrompt),
                "consensusStatements": analysis["consensusStatements"],
                "polarizationStatements": analysis["polarizationStatements"],
            },
        )
    if not records:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return records[0].data()


@router.post("/campaigns/{campaign_id}/deliberation", response_model=CampaignOut)
def launch_campaign_deliberation(campaign_id: str):
    df = _query_df(
        """
        MATCH (c:Campaign {campaignId: $campaignId})
        RETURN
          c.campaignId AS campaignId,
          c.name AS name,
          coalesce(c.topic, '') AS topic,
          coalesce(c.objective, '') AS objective,
          coalesce(c.legislationText, '') AS legislationText,
          coalesce(c.manifestoText, '') AS manifestoText,
          coalesce(c.expertPrompt, '') AS expertPrompt,
          coalesce(c.consensusStatements, []) AS consensusStatements,
          coalesce(c.polarizationStatements, []) AS polarizationStatements,
          coalesce(c.deliberationConversationId, '') AS deliberationConversationId
        LIMIT 1
        """,
        {"campaignId": _clean_text(campaign_id)},
    )
    if df.empty:
        raise HTTPException(status_code=404, detail="Campaign not found")
    row = df.iloc[0].to_dict()
    existing_id = _clean_text(row.get("deliberationConversationId"))
    if existing_id:
        return get_campaign(row.get("campaignId"))
    topic = row.get("topic") or row.get("name") or "Campaign deliberation"
    description = row.get("objective") or "Campaign deliberation conversation."
    convo = create_conversation(
        ConversationCreate(
            topic=topic,
            description=description,
            is_open=True,
            allow_comment_submission=True,
            allow_viz=True,
            moderation_required=False,
        )
    )
    conversation_id = convo.get("id") if isinstance(convo, dict) else None
    statements = list(row.get("consensusStatements") or []) + list(
        row.get("polarizationStatements") or []
    )
    analysis = None
    if not statements:
        analysis = _generate_campaign_analysis(
            row.get("topic"),
            row.get("legislationText"),
            row.get("manifestoText"),
            row.get("expertPrompt"),
        )
        statements = analysis["consensusStatements"] + analysis["polarizationStatements"]
    topic_label = _clean_text(row.get("topic")) or row.get("name") or "Campaign"
    statements = _prepare_seed_statements(statements, topic_label)
    if conversation_id:
        seed_comments(conversation_id, SeedCommentsRequest(comments=statements))
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            MATCH (c:Campaign {campaignId: $campaignId})
            SET c.deliberationConversationId = $conversationId,
                c.updatedAt = datetime()
            FOREACH (_ IN CASE WHEN $updateStatements THEN [1] ELSE [] END |
              SET c.consensusStatements = $consensusStatements,
                  c.polarizationStatements = $polarizationStatements
            )
            """,
            {
                "campaignId": row.get("campaignId"),
                "conversationId": conversation_id,
                "updateStatements": bool(analysis),
                "consensusStatements": analysis["consensusStatements"] if analysis else [],
                "polarizationStatements": analysis["polarizationStatements"] if analysis else [],
            },
        )
    return get_campaign(row.get("campaignId"))


@router.get("/furry/summary", response_model=List[FurryFriendOut])
def list_furry_friends(
    species: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    sort: Optional[str] = Query("name"),
    limit: int = Query(1000, ge=10, le=5000),
):
    df = _query_df(
        """
        MATCH (f:FurryFriend)
        RETURN
          f.furryId AS furryId,
          coalesce(f.municipality, '') AS municipality,
          coalesce(f.species, 'Dog') AS species,
          coalesce(f.name, '') AS name,
          coalesce(f.gender, '') AS gender,
          f.age AS age,
          f.neutered AS neutered,
          coalesce(f.breed, '') AS breed,
          coalesce(f.color, '') AS color,
          coalesce(f.chipNumber, '') AS chipNumber,
          coalesce(f.address, '') AS address,
          f.lat AS lat,
          f.lon AS lon,
          coalesce(f.notes, '') AS notes
        """,
        {},
    )
    if df.empty:
        return []
    if species:
        desired = str(species).strip().lower()
        if desired in {"dog", "cat"}:
            df = df[df["species"].astype(str).str.lower() == desired]
    search = (q or "").strip().lower()
    if search:
        df = df[
            df["municipality"].astype(str).str.lower().str.contains(search, na=False)
            | df["species"].astype(str).str.lower().str.contains(search, na=False)
            | df["name"].astype(str).str.lower().str.contains(search, na=False)
            | df["breed"].astype(str).str.lower().str.contains(search, na=False)
            | df["address"].astype(str).str.lower().str.contains(search, na=False)
            | df["chipNumber"].astype(str).str.lower().str.contains(search, na=False)
        ]
    sort_map = {
        "name": ("name", True),
        "age": ("age", False),
        "municipality": ("municipality", True),
        "species": ("species", True),
    }
    if sort in sort_map:
        col, asc = sort_map[sort]
        if col in df.columns:
            df = df.sort_values(col, ascending=asc)
    df = df.head(int(limit))
    df = df.replace([np.inf, -np.inf], None)
    df = df.replace({np.nan: None})
    df = df.where(pd.notnull(df), None)
    return df.to_dict(orient="records")


@router.get("/furry/{furry_id}", response_model=FurryFriendOut)
def get_furry_friend(furry_id: str):
    df = _query_df(
        """
        MATCH (f:FurryFriend {furryId: $furryId})
        RETURN
          f.furryId AS furryId,
          coalesce(f.municipality, '') AS municipality,
          coalesce(f.species, 'Dog') AS species,
          coalesce(f.name, '') AS name,
          coalesce(f.gender, '') AS gender,
          f.age AS age,
          f.neutered AS neutered,
          coalesce(f.breed, '') AS breed,
          coalesce(f.color, '') AS color,
          coalesce(f.chipNumber, '') AS chipNumber,
          coalesce(f.address, '') AS address,
          f.lat AS lat,
          f.lon AS lon,
          coalesce(f.notes, '') AS notes
        LIMIT 1
        """,
        {"furryId": _clean_text(furry_id)},
    )
    if df.empty:
        raise HTTPException(status_code=404, detail="Record not found")
    return df.iloc[0].to_dict()


@router.post("/furry", response_model=FurryFriendOut)
def upsert_furry_friend(payload: FurryFriendUpsert):
    municipality = _clean_text(payload.municipality)
    address = _clean_text(payload.address)
    if not municipality and not address:
        raise HTTPException(status_code=400, detail="Municipality or address is required")
    if not municipality:
        municipality = _extract_municipality(address) or ""
    species = _clean_text(payload.species) or "Dog"
    furry_id = _clean_text(payload.furryId) or str(uuid4())
    query = """
    MERGE (f:FurryFriend {furryId: $furryId})
    ON CREATE SET f.createdAt = datetime()
    SET f.municipality = $municipality,
        f.species = $species,
        f.name = $name,
        f.gender = $gender,
        f.age = $age,
        f.neutered = $neutered,
        f.breed = $breed,
        f.color = $color,
        f.chipNumber = $chipNumber,
        f.address = $address,
        f.lat = $lat,
        f.lon = $lon,
        f.notes = $notes,
        f.updatedAt = datetime()
    RETURN
      f.furryId AS furryId,
      coalesce(f.municipality, '') AS municipality,
      coalesce(f.species, 'Dog') AS species,
      coalesce(f.name, '') AS name,
      coalesce(f.gender, '') AS gender,
      f.age AS age,
      f.neutered AS neutered,
      coalesce(f.breed, '') AS breed,
      coalesce(f.color, '') AS color,
      coalesce(f.chipNumber, '') AS chipNumber,
      coalesce(f.address, '') AS address,
      f.lat AS lat,
      f.lon AS lon,
      coalesce(f.notes, '') AS notes
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "furryId": furry_id,
                "municipality": municipality,
                "species": species,
                "name": _clean_text(payload.name),
                "gender": _clean_text(payload.gender),
                "age": payload.age,
                "neutered": payload.neutered,
                "breed": _clean_text(payload.breed),
                "color": _clean_text(payload.color),
                "chipNumber": _clean_text(payload.chipNumber),
                "address": address,
                "lat": payload.lat,
                "lon": payload.lon,
                "notes": _clean_text(payload.notes),
            },
        )
    if not records:
        raise HTTPException(status_code=500, detail="Record could not be saved")
    return records[0].data()


@router.post("/furry/import")
async def import_furry_file(file: UploadFile = File(...)):
    try:
        content = await file.read()
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read CSV: {exc}")
    rows = _build_furry_import_rows(df)
    if not rows:
        raise HTTPException(status_code=400, detail="No valid rows found in CSV")
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            UNWIND $rows AS row
            WITH row
            MERGE (f:FurryFriend {furryId: row.furryId})
            ON CREATE SET f.createdAt = datetime()
            SET f.municipality = row.municipality,
                f.species = row.species,
                f.name = row.name,
                f.gender = row.gender,
                f.age = row.age,
                f.neutered = row.neutered,
                f.breed = row.breed,
                f.color = row.color,
                f.chipNumber = row.chipNumber,
                f.address = row.address,
                f.lat = row.lat,
                f.lon = row.lon,
                f.notes = row.notes,
                f.updatedAt = datetime()
            """,
            {"rows": rows},
        )
    return {"created": len(rows)}


@router.get("/events", response_model=List[EventOut])
def list_events(limit: int = Query(200, ge=10, le=1000)):
    df = _query_df(
        """
        MATCH (e:Event)
        OPTIONAL MATCH (p:Person)-[r:REGISTERED_FOR]->(e)
        RETURN
          e.eventId AS eventId,
          e.eventKey AS eventKey,
          e.name AS name,
          e.startDate AS startDate,
          e.endDate AS endDate,
          e.location AS location,
          coalesce(e.status, 'Planned') AS status,
          coalesce(e.capacity, 0) AS capacity,
          count(r) AS registrations,
          coalesce(e.notes, '') AS notes
        ORDER BY e.startDate DESC
        LIMIT $limit
        """,
        {"limit": int(limit)},
    )
    return df.to_dict(orient="records") if not df.empty else []


@router.get("/events/detail", response_model=EventOut)
def get_event_detail(event_id: Optional[str] = None, event_key: Optional[str] = None):
    df = _query_df(
        """
        MATCH (e:Event)
        WHERE ($eventId IS NOT NULL AND e.eventId = $eventId)
           OR ($eventKey IS NOT NULL AND e.eventKey = $eventKey)
        OPTIONAL MATCH (p:Person)-[r:REGISTERED_FOR]->(e)
        RETURN
          e.eventId AS eventId,
          e.eventKey AS eventKey,
          e.name AS name,
          coalesce(e.startDate, '') AS startDate,
          coalesce(e.endDate, '') AS endDate,
          coalesce(e.location, '') AS location,
          coalesce(e.status, 'Planned') AS status,
          coalesce(e.capacity, 0) AS capacity,
          coalesce(e.notes, '') AS notes,
          count(r) AS registrations
        LIMIT 1
        """,
        {"eventId": _clean_text(event_id), "eventKey": _clean_text(event_key)},
    )
    if df.empty:
        raise HTTPException(status_code=404, detail="Event not found")
    return df.iloc[0].to_dict()


@router.post("/events", response_model=EventOut)
def create_event(payload: EventCreate):
    name = _clean_text(payload.name)
    if not name:
        raise HTTPException(status_code=400, detail="Event name is required")
    status = _clean_text(payload.status) or "Planned"
    if status not in EVENT_STATUSES:
        status = "Planned"
    event_id = str(uuid4())
    event_key = str(uuid4())
    driver = get_driver()
    query = """
    CREATE (e:Event {
      eventId: $eventId,
      eventKey: $eventKey,
      name: $name,
      startDate: $startDate,
      endDate: $endDate,
      location: $location,
      status: $status,
      capacity: $capacity,
      notes: $notes,
      createdAt: datetime()
    })
    RETURN
      e.eventId AS eventId,
      e.eventKey AS eventKey,
      e.name AS name,
      e.startDate AS startDate,
      e.endDate AS endDate,
      e.location AS location,
      coalesce(e.status, 'Planned') AS status,
      coalesce(e.capacity, 0) AS capacity,
      0 AS registrations,
      coalesce(e.notes, '') AS notes
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "eventId": event_id,
                "eventKey": event_key,
                "name": name,
                "startDate": _clean_text(payload.startDate),
                "endDate": _clean_text(payload.endDate),
                "location": _clean_text(payload.location),
                "status": status,
                "capacity": payload.capacity or 0,
                "notes": _clean_text(payload.notes),
            },
        )
    if not records:
        raise HTTPException(status_code=500, detail="Event could not be created")
    return records[0].data()


@router.post("/events/with-people")
def create_event_for_people(payload: EventCreateWithPeopleRequest):
    event = payload.event
    rows = payload.rows or []
    if not _clean_text(event.name):
        raise HTTPException(status_code=400, detail="Event name is required")
    status = _clean_text(event.status) or "Planned"
    if status not in EVENT_STATUSES:
        status = "Planned"
    event_id = str(uuid4())
    event_key = str(uuid4())
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            CREATE (e:Event {
              eventId: $eventId,
              eventKey: $eventKey,
              name: $name,
              startDate: $startDate,
              endDate: $endDate,
              location: $location,
              status: $status,
              capacity: $capacity,
              notes: $notes,
              createdAt: datetime()
            })
            """,
            {
                "eventId": event_id,
                "eventKey": event_key,
                "name": _clean_text(event.name),
                "startDate": _clean_text(event.startDate),
                "endDate": _clean_text(event.endDate),
                "location": _clean_text(event.location),
                "status": status,
                "capacity": event.capacity or 0,
                "notes": _clean_text(event.notes),
            },
        )
        _execute_write(
            session,
            """
            UNWIND $rows AS row
            MATCH (e:Event {eventId: $eventId})
            WITH e, row
            WHERE row.email IS NOT NULL AND trim(row.email) <> ""
            MERGE (p:Person {email: row.email})
            ON CREATE SET p.personId = randomUUID(), p.createdAt = datetime()
            SET p.firstName = coalesce(row.firstName, p.firstName),
                p.lastName = coalesce(row.lastName, p.lastName),
                p.phone = coalesce(row.phone, p.phone),
                p.updatedAt = datetime()
            WITH e, p, row
            FOREACH (_ IN CASE
              WHEN row.group IS NULL OR row.group = '' OR NOT row.group IN ['Supporter','Member']
              THEN [] ELSE [1]
            END |
              MERGE (st:SupporterType {name: row.group})
              MERGE (p)-[:CLASSIFIED_AS]->(st)
            )
            MERGE (p)-[r:REGISTERED_FOR]->(e)
            ON CREATE SET r.registeredAt = datetime()
            SET r.status = $status,
                r.updatedAt = datetime()
            """,
            {"eventId": event_id, "rows": rows, "status": payload.registrationStatus},
        )
    return {"eventId": event_id}


@router.post("/events/{event_id}/register")
def register_person_to_event(event_id: str, payload: EventRegisterRequest):
    person = payload.person or {}
    email = _clean_text(person.get("email"))
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    status = _clean_text(payload.status) or "Registered"
    if status not in EVENT_REGISTRATION_STATUSES:
        status = "Registered"
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            MATCH (e:Event {eventId: $eventId})
            MERGE (p:Person {email: $email})
            ON CREATE SET p.personId = randomUUID(), p.createdAt = datetime()
            SET p.firstName = coalesce($firstName, p.firstName),
                p.lastName = coalesce($lastName, p.lastName),
                p.phone = coalesce($phone, p.phone),
                p.updatedAt = datetime()
            FOREACH (_ IN CASE
              WHEN $group IS NULL OR $group = '' OR NOT $group IN ['Supporter','Member']
              THEN [] ELSE [1]
            END |
              MERGE (st:SupporterType {name: $group})
              MERGE (p)-[:CLASSIFIED_AS]->(st)
            )
            MERGE (p)-[r:REGISTERED_FOR]->(e)
            ON CREATE SET r.registeredAt = datetime()
            SET r.status = $status,
                r.notes = $notes,
                r.updatedAt = datetime()
            """,
            {
                "eventId": _clean_text(event_id),
                "email": email,
                "firstName": _clean_text(person.get("firstName")),
                "lastName": _clean_text(person.get("lastName")),
                "phone": _clean_text(person.get("phone")),
                "group": _clean_text(person.get("group")),
                "status": status,
                "notes": _clean_text(payload.notes),
            },
        )
    return {"registered": True}


@router.post("/events/{event_id}/register/bulk")
def bulk_register_people(event_id: str, payload: EventBulkRegisterRequest):
    rows = payload.rows or []
    if not rows:
        raise HTTPException(status_code=400, detail="No rows provided")
    status = _clean_text(payload.status) or "Registered"
    if status not in EVENT_REGISTRATION_STATUSES:
        status = "Registered"
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            MATCH (e:Event {eventId: $eventId})
            WITH e
            UNWIND $rows AS row
            WITH e, row
            WHERE row.email IS NOT NULL AND trim(row.email) <> ""
            MERGE (p:Person {email: row.email})
            ON CREATE SET p.personId = randomUUID(), p.createdAt = datetime()
            SET p.firstName = coalesce(row.firstName, p.firstName),
                p.lastName = coalesce(row.lastName, p.lastName),
                p.phone = coalesce(row.phone, p.phone),
                p.updatedAt = datetime()
            WITH e, p, row
            FOREACH (_ IN CASE
              WHEN row.group IS NULL OR row.group = '' OR NOT row.group IN ['Supporter','Member']
              THEN [] ELSE [1]
            END |
              MERGE (st:SupporterType {name: row.group})
              MERGE (p)-[:CLASSIFIED_AS]->(st)
            )
            MERGE (p)-[r:REGISTERED_FOR]->(e)
            ON CREATE SET r.registeredAt = datetime()
            SET r.status = $status,
                r.updatedAt = datetime()
            """,
            {"eventId": _clean_text(event_id), "rows": rows, "status": status},
        )
    return {"registered": len(rows)}


@router.get("/events/{event_id}/registrations", response_model=List[EventRegistrationOut])
def list_event_registrations(event_id: str, limit: int = Query(500, ge=10, le=5000)):
    df = _query_df(
        """
        MATCH (e:Event {eventId: $eventId})<-[r:REGISTERED_FOR]-(p:Person)
        OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(st:SupporterType)
        WITH p, r, collect(DISTINCT st.name) AS types
        RETURN
          p.email AS email,
          coalesce(p.firstName, '') AS firstName,
          coalesce(p.lastName, '') AS lastName,
          coalesce(p.phone, '') AS phone,
          CASE
            WHEN any(x IN types WHERE toLower(x) CONTAINS 'member') THEN 'Member'
            WHEN size(types) = 0 THEN 'Supporter'
            ELSE head(types)
          END AS group,
          coalesce(r.status, 'Registered') AS registrationStatus,
          coalesce(r.notes, '') AS notes,
          toString(r.registeredAt) AS registeredAt,
          toString(r.updatedAt) AS updatedAt
        ORDER BY r.updatedAt DESC
        LIMIT $limit
        """,
        {"eventId": _clean_text(event_id), "limit": int(limit)},
    )
    return df.to_dict(orient="records") if not df.empty else []


@router.get("/events/registrations/status-counts", response_model=List[EventStatusCountOut])
def list_registration_status_counts(limit_events: int = Query(20, ge=1, le=100)):
    df = _query_df(
        """
        MATCH (e:Event)
        WITH e
        ORDER BY coalesce(e.startDate, '') DESC
        LIMIT $limitEvents
        OPTIONAL MATCH (:Person)-[r:REGISTERED_FOR]->(e)
        RETURN
          e.eventId AS eventId,
          coalesce(e.name, 'Untitled event') AS eventName,
          coalesce(r.status, 'Registered') AS registrationStatus,
          count(r) AS count
        ORDER BY eventName ASC, registrationStatus ASC
        """,
        {"limitEvents": int(limit_events)},
    )
    return df.to_dict(orient="records") if not df.empty else []


@router.delete("/events/{event_id}")
def delete_event(event_id: str):
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            "MATCH (e:Event {eventId: $eventId}) DETACH DELETE e",
            {"eventId": _clean_text(event_id)},
        )
    return {"deleted": True, "event_id": event_id}


@router.get("/admin/status", response_model=AdminStatusOut)
def admin_status():
    from .db import db_health

    health = db_health()
    neo4j_status = "Connected" if health.get("ok") else "Not connected"
    deliberation_status = "Online" if health.get("ok") else "Reachable but degraded"
    api_urls = [str(os.getenv("DELIBERATION_API_URL") or "").strip()]
    fallback = str(os.getenv("DELIBERATION_API_FALLBACK_URL") or "").strip()
    if fallback and fallback not in api_urls:
        api_urls.append(fallback)
    feedback_to = str(os.getenv("FEEDBACK_EMAIL_TO") or "").strip()
    smtp_host = str(os.getenv("SMTP_HOST") or "").strip()
    return {
        "neo4j_status": neo4j_status,
        "deliberation_status": deliberation_status,
        "api_urls": [u for u in api_urls if u],
        "feedback_configured": bool(feedback_to and smtp_host),
        "feedback_from": str(os.getenv("FEEDBACK_EMAIL_FROM") or "").strip() or None,
        "feedback_to": feedback_to or None,
        "whatsapp_configured": bool(str(os.getenv("WHATSAPP_GROUP_WEBHOOK_URL") or "").strip()),
        "slack_configured": bool(str(os.getenv("SLACK_WEBHOOK_URL") or "").strip()),
        "slack_username": str(os.getenv("SLACK_USERNAME") or "").strip() or None,
    }


@router.get("/admin/feedback")
def list_feedback_entries(limit: int = Query(300, ge=1, le=2000)):
    df = _query_df(
        """
        MATCH (f:FeedbackEntry)
        RETURN
          f.feedbackId AS feedbackId,
          coalesce(f.page, '') AS page,
          coalesce(f.name, '') AS name,
          coalesce(f.email, '') AS email,
          coalesce(f.channel, '') AS channel,
          coalesce(f.emailStatus, '') AS emailStatus,
          coalesce(f.emailError, '') AS emailError,
          coalesce(f.message, '') AS message,
          toString(f.createdAt) AS createdAt
        ORDER BY f.createdAt DESC
        LIMIT $limit
        """,
        {"limit": int(limit)},
    )
    return df.to_dict(orient="records") if not df.empty else []


def _count_graph(session) -> Tuple[int, int]:
    nodes_rows = _execute_read(session, "MATCH (n) RETURN count(n) AS count")
    rels_rows = _execute_read(session, "MATCH ()-[r]-() RETURN count(r) AS count")
    nodes = int((nodes_rows[0].get("count") if nodes_rows else 0) or 0)
    rels = int((rels_rows[0].get("count") if rels_rows else 0) or 0)
    return nodes, rels


@router.post("/admin/clear-db")
def clear_aura_db(payload: ClearDbRequest):
    confirm = _clean_text(payload.confirm)
    if confirm != "CLEAR AURA DB":
        raise HTTPException(
            status_code=400, detail="Confirmation text must be 'CLEAR AURA DB'."
        )
    driver = get_driver()
    with _db_session(driver) as session:
        nodes, rels = _count_graph(session)
        _execute_write(session, "MATCH (n) DETACH DELETE n")
    return {
        "ok": True,
        "deleted_nodes": nodes,
        "deleted_relationships": rels,
    }


def _parse_int(value, default):
    try:
        return int(value)
    except Exception:
        return default


def _feedback_email_configured():
    feedback_to = str(os.getenv("FEEDBACK_EMAIL_TO") or "").strip()
    smtp_host = str(os.getenv("SMTP_HOST") or "").strip()
    return bool(feedback_to and smtp_host)


def _send_feedback_email(name: str, email: str, message: str, page: str):
    if not _feedback_email_configured():
        return False, "not_configured", None
    feedback_from = str(os.getenv("FEEDBACK_EMAIL_FROM") or "").strip()
    feedback_to = str(os.getenv("FEEDBACK_EMAIL_TO") or "").strip()
    smtp_host = str(os.getenv("SMTP_HOST") or "").strip()
    smtp_user = str(os.getenv("SMTP_USER") or "").strip()
    smtp_password = str(os.getenv("SMTP_PASSWORD") or "").strip()
    smtp_port = _parse_int(os.getenv("SMTP_PORT"), 587)
    smtp_use_tls = str(os.getenv("SMTP_USE_TLS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    from_email = feedback_from or feedback_to

    msg = EmailMessage()
    msg["Subject"] = f"Feedback ({page or 'app'})"
    msg["From"] = from_email
    msg["To"] = feedback_to
    if email:
        msg["Reply-To"] = email
    body_lines = [
        f"Name: {name or 'Anonymous'}",
        f"Email: {email or 'Not provided'}",
        f"Page: {page or 'Unknown'}",
        "",
        message,
    ]
    msg.set_content("\n".join(body_lines))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.ehlo()
            if smtp_use_tls:
                server.starttls()
                server.ehlo()
            if smtp_user:
                server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return True, "sent", None
    except Exception as exc:
        return False, "failed", str(exc)


def _create_feedback_entry(
    *,
    name: str,
    email: str,
    page: str,
    message: str,
    channel: str,
    email_status: str,
    email_error: str,
):
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            CREATE (f:FeedbackEntry {
              feedbackId: randomUUID(),
              name: $name,
              email: $email,
              page: $page,
              message: $message,
              channel: $channel,
              emailStatus: $emailStatus,
              emailError: $emailError,
              createdAt: datetime()
            })
            """,
            {
                "name": name,
                "email": email,
                "page": page,
                "message": message,
                "channel": channel,
                "emailStatus": email_status,
                "emailError": email_error,
            },
        )


@router.post("/feedback")
def create_feedback(payload: dict):
    message = _clean_text(payload.get("message"))
    if not message:
        raise HTTPException(status_code=400, detail="Message is empty.")
    name = _clean_text(payload.get("name"))
    email = _clean_text(payload.get("email"))
    page = _clean_text(payload.get("page")) or "App"
    channel = _clean_text(payload.get("channel")) or "sidebar_feedback"

    _, email_status, email_error = _send_feedback_email(name, email, message, page)
    _create_feedback_entry(
        name=name or "",
        email=email or "",
        page=page,
        message=message,
        channel=channel,
        email_status=email_status,
        email_error=email_error or "",
    )
    return {
        "ok": True,
        "email_status": email_status,
        "email_error": email_error,
    }


def _send_slack_message(
    *,
    message: str,
    username: str = "",
    channel: str = "",
    source: str = "",
):
    webhook_url = str(os.getenv("SLACK_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        raise HTTPException(status_code=400, detail="Slack webhook is not configured.")
    body = {"text": message}
    resolved_username = _clean_text(username) or _clean_text(os.getenv("SLACK_USERNAME"))
    if resolved_username:
        body["username"] = resolved_username
    resolved_channel = _clean_text(channel) or _clean_text(os.getenv("SLACK_CHANNEL"))
    if resolved_channel:
        body["channel"] = resolved_channel
    if _clean_text(source):
        body["icon_emoji"] = ":speech_balloon:"
    try:
        response = requests.post(
            webhook_url,
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=20,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Webhook rejected request ({response.status_code}): {response.text}",
        )


@router.post("/admin/slack-test")
def send_slack_test(payload: dict):
    message = _clean_text(payload.get("message"))
    if not message:
        raise HTTPException(status_code=400, detail="Message is empty.")
    _send_slack_message(
        message=message,
        username=_clean_text(payload.get("username")),
        channel=_clean_text(payload.get("channel")),
        source=_clean_text(payload.get("source")) or "admin_test",
    )
    return {"ok": True}


@router.post("/slack/send")
def send_slack_message(payload: dict):
    message = _clean_text(payload.get("message"))
    if not message:
        raise HTTPException(status_code=400, detail="Message is empty.")
    _send_slack_message(
        message=message,
        username=_clean_text(payload.get("username")),
        channel=_clean_text(payload.get("channel")),
        source=_clean_text(payload.get("source")) or "frontend_share",
    )
    return {"ok": True}
