"""
CRM – contacts / people CRUD, summary, dashboard, map, import/export,
geocoding triggers, segments, distinct-values, and furry-friend registry.
"""
import io
import json
import os
from typing import List, Optional
from uuid import uuid4

import numpy as np
import pandas as pd

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field

from .db import get_driver
from .routes_crm_helpers import (
    _clean_text,
    _normalize_supporter_type,
    _execute_read,
    _execute_write,
    _db_session,
    _query_df,
    _load_supporter_summary_df,
    _load_profile,
    _apply_geocoding,
    _enrich_people_core,
    _format_list_label,
    _rating_color,
    _build_import_rows,
    _build_furry_import_rows,
    _build_segment_query,
    _build_segment_count_query,
    _extract_municipality,
    _derive_neighbourhood_from_address,
    _split_list,
    SegmentFilter,
    segment_filter_from_stored_value,
)
from .routes_crm_support import _send_smtp_email

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

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
    # New Georgian fields
    profession: Optional[str] = None
    social_media: Optional[str] = Field(alias="socialMedia", default=None)
    was_party_member: Optional[bool] = Field(alias="wasPartyMember", default=None)
    party_details: Optional[str] = Field(alias="partyDetails", default=None)
    how_to_help: Optional[str] = Field(alias="howToHelp", default=None)
    additional_comments: Optional[str] = Field(alias="additionalComments", default=None)
    personal_id: Optional[str] = Field(alias="personalId", default=None)
    whatsapp_chat: Optional[str] = Field(alias="whatsappChat", default=None)
    date_of_birth: Optional[str] = Field(alias="dateOfBirth", default=None)
    topics_of_interest: List[str] = Field(alias="topicsOfInterest", default_factory=list)


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
    about: Optional[str] = None
    agreesWithManifesto: Optional[bool] = None
    interestedInMembership: Optional[bool] = None
    facebookGroupMember: Optional[bool] = None
    education: Optional[str] = None
    educationLevels: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    skills: Optional[List[str]] = None
    involvementAreas: Optional[List[str]] = None


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
    person_id: Optional[str] = Field(alias="personId", default=None)
    full_name: str = Field(alias="fullName")
    email: str = ""
    group: str
    lat: float
    lon: float
    time_availability: str = Field(alias="timeAvailability")
    age: Optional[int] = None
    age_group: str = Field(alias="ageGroup")
    gender: str = "Unspecified"
    skills: List[str] = []
    skills_label: str = Field(alias="skillsLabel")
    involvement_label: str = Field(alias="involvementLabel")
    involvement_title: str = Field(alias="involvementTitle")
    address_label: str = Field(alias="addressLabel")
    neighbourhood: Optional[str] = None
    rating: Optional[str] = None
    rating_stars: Optional[str] = Field(alias="ratingStars", default=None)
    effort_hours: float = Field(alias="effortHours")
    event_attend_count: int = Field(alias="eventAttendCount")
    referral_count: int = Field(alias="referralCount")
    about: Optional[str] = ""
    point_size: float = Field(alias="pointSize")
    color: List[int]


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


class SegmentCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    filterSpec: SegmentFilter = Field(default_factory=SegmentFilter)


class SegmentOut(BaseModel):
    segment_id: str = Field(alias="segmentId")
    name: str
    description: str = ""
    updated_at: Optional[str] = Field(alias="updatedAt", default=None)
    filter_spec: SegmentFilter = Field(default_factory=SegmentFilter, alias="filterSpec")


class SegmentCountOut(BaseModel):
    count: int


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


class SupporterInviteCreate(BaseModel):
    recipient_name: Optional[str] = Field(alias="recipientName", default="")
    recipient_email: Optional[str] = Field(alias="recipientEmail", default="")
    recipient_phone: Optional[str] = Field(alias="recipientPhone", default="")
    channel: Optional[str] = "manual"
    invite_audience: Optional[str] = Field(alias="inviteAudience", default="individual")
    supporter_type: Optional[str] = Field(alias="supporterType", default="Supporter")
    notes: Optional[str] = ""


class SurveyInviteCreate(BaseModel):
    conversation_id: str = Field(alias="conversationId", min_length=1)
    topic: Optional[str] = ""
    invite_link: str = Field(alias="inviteLink", min_length=1)
    recipient_name: Optional[str] = Field(alias="recipientName", default="")
    recipient_email: Optional[str] = Field(alias="recipientEmail", default="")
    recipient_phone: Optional[str] = Field(alias="recipientPhone", default="")
    channel: Optional[str] = "manual"
    invite_audience: Optional[str] = Field(alias="inviteAudience", default="individual")
    notes: Optional[str] = ""


class EventInviteCreate(BaseModel):
    event_id: Optional[str] = Field(alias="eventId", default="")
    event_name: Optional[str] = Field(alias="eventName", default="")
    invite_link: str = Field(alias="inviteLink", min_length=1)
    recipient_name: Optional[str] = Field(alias="recipientName", default="")
    recipient_email: Optional[str] = Field(alias="recipientEmail", default="")
    recipient_emails: List[str] = Field(alias="recipientEmails", default_factory=list)
    channel: Optional[str] = "email"
    invite_audience: Optional[str] = Field(alias="inviteAudience", default="individual")
    notes: Optional[str] = ""


class SupporterInviteReminderCreate(BaseModel):
    channel: Optional[str] = "manual"
    note: Optional[str] = ""


class SupporterSignupCreate(BaseModel):
    first_name: str = Field(alias="firstName", min_length=1)
    last_name: str = Field(alias="lastName", min_length=1)
    birth_date: str = Field(alias="birthDate", min_length=1)
    email: str
    phone: str = Field(min_length=1)
    address: str = Field(min_length=1)
    profession: str = Field(min_length=1)
    social_media: str = Field(alias="socialMedia", min_length=1)
    former_party_member: str = Field(alias="formerPartyMember", min_length=1)
    time_availability: str = Field(alias="timeAvailability", min_length=1)
    interests: List[str] = Field(default_factory=list, min_length=1)
    whatsapp_group: str = Field(alias="whatsappGroup", min_length=1)
    interested_in_membership: str = Field(alias="interestedInMembership", min_length=1)
    additional_comments: Optional[str] = Field(alias="additionalComments", default="")
    agrees_with_manifesto: bool = Field(alias="agreesWithManifesto", default=False)
    invite_code: Optional[str] = Field(alias="inviteCode", default="")


class SupporterSignupConfigUpdate(BaseModel):
    welcome_video_url: Optional[str] = Field(alias="welcomeVideoUrl", default="")
    thank_you_video_url: Optional[str] = Field(alias="thankYouVideoUrl", default="")


class SupporterInviteGroupsConfigUpdate(BaseModel):
    everyone_group_email: Optional[str] = Field(alias="everyoneGroupEmail", default="")
    verified_group_email: Optional[str] = Field(alias="verifiedGroupEmail", default="")
    registered_group_email: Optional[str] = Field(alias="registeredGroupEmail", default="")


# ---------------------------------------------------------------------------
# Local helper: load map data
# ---------------------------------------------------------------------------


def _build_supporter_signup_submission(payload: SupporterSignupCreate) -> dict:
    email = _clean_text(payload.email)
    first_name = _clean_text(payload.first_name)
    last_name = _clean_text(payload.last_name)
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if not first_name:
        raise HTTPException(status_code=400, detail="First name is required")
    if not last_name:
        raise HTTPException(status_code=400, detail="Last name is required")

    return {
        "email": email,
        "firstName": first_name,
        "lastName": last_name,
        "birthDate": _clean_text(payload.birth_date),
        "phone": _clean_text(payload.phone),
        "address": _clean_text(payload.address),
        "profession": _clean_text(payload.profession),
        "socialMedia": _clean_text(payload.social_media),
        "formerPartyMember": _clean_text(payload.former_party_member),
        "timeAvailability": _clean_text(payload.time_availability),
        "interests": [_clean_text(item) for item in (payload.interests or []) if _clean_text(item)],
        "whatsappGroup": _clean_text(payload.whatsapp_group),
        "interestedInMembership": _clean_text(payload.interested_in_membership),
        "additionalComments": _clean_text(payload.additional_comments),
        "agreesWithManifesto": bool(payload.agrees_with_manifesto),
        "inviteCode": _clean_text(payload.invite_code),
    }

def _supporter_signup_base_url():
    configured = str(os.getenv("SUPPORTER_SIGNUP_BASE_URL") or "").strip()
    if configured:
        return configured
    frontend_url = str(os.getenv("FRONTEND_PUBLIC_URL") or "").strip().rstrip("/")
    if frontend_url:
        return f"{frontend_url}/supporter-signup"
    return "http://localhost:5174/supporter-signup"


def _build_supporter_invite_url(invite_code: str, supporter_type: str = "Supporter"):
    from urllib.parse import urlencode

    base_url = _supporter_signup_base_url()
    params = {
        "invite_code": invite_code,
        "supporter_type": _normalize_supporter_type(supporter_type, "Supporter").lower(),
    }
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode(params)}"


def _build_supporter_invite_email_message(recipient_name: str, invite_url: str, supporter_type: str = "Supporter"):
    name = recipient_name or "friend"
    type_label = _normalize_supporter_type(supporter_type, "Supporter").lower()
    return f"""
Hello, {name}!

Here is your Freedom Square {type_label} signup form.
Please click the link below and complete the form:

{invite_url}

Best regards,
The Freedom Square Team
""".strip()


def _build_supporter_reminder_email_message(recipient_name: str, invite_url: str):
    name = recipient_name or "friend"
    return f"""
Hello, {name}!

This is a reminder that you were invited to join the Freedom Square supporter group.
Please click the link below to complete your registration:

{invite_url}

Best regards,
The Freedom Square Team
""".strip()


def _send_supporter_invite_email(recipient_email: str, recipient_name: str, invite_code: str, supporter_type: str):
    invite_url = _build_supporter_invite_url(invite_code, supporter_type)
    return _send_smtp_email(
        recipient_email,
        f"Freedom Square {_normalize_supporter_type(supporter_type, 'Supporter')} signup form",
        _build_supporter_invite_email_message(recipient_name, invite_url, supporter_type),
    )


def _build_survey_invite_email_message(recipient_name: str, topic: str, invite_url: str, notes: str = ""):
    name = recipient_name or "friend"
    topic_label = topic or "Freedom Square survey"
    note_block = f"\n\nNote: {notes}" if notes else ""
    return f"""
Hello, {name}!

You are invited to take part in this Freedom Square survey:
{topic_label}

Please click the link below to participate:

{invite_url}{note_block}

Best regards,
The Freedom Square Team
""".strip()


def _send_survey_invite_email(recipient_email: str, recipient_name: str, topic: str, invite_url: str, notes: str = ""):
    return _send_smtp_email(
        recipient_email,
        f"Freedom Square survey: {topic or 'Participate'}",
        _build_survey_invite_email_message(recipient_name, topic, invite_url, notes),
    )


def _build_event_invite_email_message(recipient_name: str, event_name: str, invite_url: str, notes: str = ""):
    name = recipient_name or "friend"
    event_label = event_name or "Freedom Square event"
    note_block = f"\n\nNote: {notes}" if notes else ""
    return f"""
Hello, {name}!

You are invited to register for this Freedom Square event:
{event_label}

Please click the link below to register:

{invite_url}{note_block}

Best regards,
The Freedom Square Team
""".strip()


def _send_event_invite_email(recipient_email: str, recipient_name: str, event_name: str, invite_url: str, notes: str = ""):
    return _send_smtp_email(
        recipient_email,
        f"Freedom Square event: {event_name or 'Registration'}",
        _build_event_invite_email_message(recipient_name, event_name, invite_url, notes),
    )


def _send_supporter_reminder_email(recipient_email: str, recipient_name: str, invite_code: str, supporter_type: str):
    invite_url = _build_supporter_invite_url(invite_code, supporter_type)
    return _send_smtp_email(
        recipient_email,
        "Reminder: Freedom Square signup form",
        _build_supporter_reminder_email_message(recipient_name, invite_url),
    )


def _load_map_data_df() -> pd.DataFrame:
    df = _query_df(
        """
        MATCH (p:Person)
        OPTIONAL MATCH (p)-[:LIVES_AT]->(addr:Address)
        WITH p,
             coalesce(p.personId, p.email, elementId(p)) AS personId,
             coalesce(p.lat, addr.lat, addr.latitude) AS lat,
             coalesce(p.lon, addr.lon, addr.longitude) AS lon,
             coalesce(p.address, addr.fullAddress) AS address
        OPTIONAL MATCH (p)-[:IS_SUPPORTER]->(s:Supporter)
        OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(st:SupporterType)
        OPTIONAL MATCH (p)-[:HAS_ACTIVITY]->(a:Activity)
        OPTIONAL MATCH (p)-[r:REGISTERED_FOR]->(:Event)
        OPTIONAL MATCH (p)-[:WANTS_TO_HELP_WITH]->(wh:InvolvementArea)
        OPTIONAL MATCH (p)-[:HAS_EDUCATION]->(ed:EducationLevel)
        OPTIONAL MATCH (p)-[:INTERESTED_IN]->(ia:InvolvementArea)
        OPTIONAL MATCH (p)<-[:REFERRED_BY]-(refP:Person)
        OPTIONAL MATCH (s)-[:RECRUITED]->(sr:Supporter)
        WITH p, s, personId, lat, lon, address,
             collect(DISTINCT st.name) AS types,
             collect(DISTINCT ed.name) AS educationLevels,
             collect(DISTINCT ia.name) AS involvementAreas,
             count(DISTINCT a) AS activityCount,
             count(DISTINCT r) AS eventJoinCount,
             count(DISTINCT CASE WHEN r.status = 'Attended' THEN r ELSE NULL END) AS eventAttendRelCount,
             collect(DISTINCT wh.name) AS skills,
             count(DISTINCT refP) AS referredCount,
             count(DISTINCT sr) AS recruitedCount
        RETURN
          personId,
          lat,
          lon,
          address AS address,
          p.neighbourhood AS neighbourhood,
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
    df = _apply_geocoding(df)
    df = df.dropna(subset=["lat", "lon"])
    df = df[df["lat"].between(-90, 90) & df["lon"].between(-180, 180)]
    df = df[~((df["lat"].abs() < 1e-6) & (df["lon"].abs() < 1e-6))]
    df["personId"] = df["personId"].fillna(df["email"]).fillna("")
    df["email"] = df["email"].fillna("")
    df["firstName"] = df["firstName"].fillna("")
    df["lastName"] = df["lastName"].fillna("")
    # Normalize gender values to F/M/U (1.0=Female, nan/string=Male, empty=Unknown)
    def _normalize_gender(g):
        if pd.isna(g) or str(g).lower() in ('', 'none', 'null', 'unspecified'):
            return 'U'
        s = str(g).lower()
        # Female: 1, 1.0, 'female', 'f'
        if s in ('1', '1.0') or 'female' in s or s == 'f':
            return 'F'
        # Male: 2, 2.0, 'male', 'm', OR any other value including 'nan'
        if s in ('2', '2.0') or 'male' in s or s == 'm' or s == 'nan':
            return 'M'
        # Other explicit values
        if s in ('3', '3.0') or 'other' in s or s == 'o':
            return 'O'
        # Default to Male for any unrecognized value
        return 'M'
    df["gender"] = df["gender"].apply(_normalize_gender)
    df["timeAvailability"] = df["timeAvailability"].fillna("Unspecified")
    df["about"] = df["about"].fillna("")
    df["address"] = df["address"].fillna("")
    df["neighbourhood"] = df["neighbourhood"].fillna("")
    df["neighbourhood"] = df.apply(
        lambda row: row.get("neighbourhood") or _derive_neighbourhood_from_address(row.get("address")),
        axis=1,
    ).fillna("")

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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

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


@router.get("/supporter-invites/stats")
def supporter_invite_stats():
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            """
            MATCH (inv:SupporterInvite)
            RETURN
              count(inv) AS sent,
              sum(CASE WHEN coalesce(inv.status, 'sent') = 'converted' THEN 1 ELSE 0 END) AS converted,
              sum(CASE WHEN coalesce(inv.status, 'sent') = 'submitted' THEN 1 ELSE 0 END) AS submitted,
              sum(coalesce(inv.reminderCount, 0)) AS reminders
            """,
        )
        channel_rows = _execute_read(
            session,
            """
            MATCH (inv:SupporterInvite)
            RETURN coalesce(inv.channel, 'manual') AS channel, count(inv) AS sent
            ORDER BY sent DESC
            """,
        )
    sent = int((records[0].get("sent") if records else 0) or 0)
    converted = int((records[0].get("converted") if records else 0) or 0)
    submitted = int((records[0].get("submitted") if records else 0) or 0)
    reminders = int((records[0].get("reminders") if records else 0) or 0)
    conversion_rate = round((converted / sent) * 100, 2) if sent else 0.0
    return {
        "sent": sent,
        "converted": converted,
        "pending": submitted,
        "reminders": reminders,
        "conversionRate": conversion_rate,
        "channels": [
            {"channel": row.get("channel") or "manual", "sent": int(row.get("sent") or 0)}
            for row in channel_rows
        ],
    }


@router.get("/supporter-invites")
def list_supporter_invites(limit: int = Query(100, ge=1, le=1000)):
    driver = get_driver()
    with _db_session(driver) as session:
        rows = _execute_read(
            session,
            """
            MATCH (inv:SupporterInvite)
            RETURN
              inv.inviteId AS inviteId,
              inv.inviteCode AS inviteCode,
              coalesce(inv.recipientName, '') AS recipientName,
              coalesce(inv.recipientEmail, '') AS recipientEmail,
              coalesce(inv.recipientPhone, '') AS recipientPhone,
              coalesce(inv.channel, 'manual') AS channel,
              coalesce(inv.inviteAudience, 'individual') AS inviteAudience,
              coalesce(inv.supporterType, 'Supporter') AS supporterType,
              coalesce(inv.status, 'sent') AS status,
              coalesce(inv.reminderCount, 0) AS reminderCount,
              toString(inv.createdAt) AS createdAt,
              toString(inv.lastReminderAt) AS lastReminderAt,
              coalesce(inv.submittedEmail, '') AS submittedEmail,
              toString(inv.convertedAt) AS convertedAt,
              coalesce(inv.convertedEmail, '') AS convertedEmail
            ORDER BY inv.createdAt DESC
            LIMIT $limit
            """,
            {"limit": int(limit)},
        )
    return [row.data() for row in rows]


@router.post("/supporter-invites")
def create_supporter_invite(payload: SupporterInviteCreate):
    invite_id = str(uuid4())
    invite_code = uuid4().hex[:12]
    supporter_type = _normalize_supporter_type(payload.supporter_type, "Supporter")
    recipient_name = _clean_text(payload.recipient_name)
    recipient_email = _clean_text(payload.recipient_email)
    recipient_phone = _clean_text(payload.recipient_phone)
    channel = _clean_text(payload.channel) or "manual"
    invite_audience = _clean_text(payload.invite_audience) or "individual"
    invite_email_sent = False
    invite_email_status = "not_attempted"
    invite_email_error = ""
    if channel.lower() == "email":
        invite_email_sent, invite_email_status, invite_email_error = _send_supporter_invite_email(
            recipient_email,
            recipient_name,
            invite_code,
            supporter_type,
        )
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            """
            CREATE (inv:SupporterInvite {
              inviteId: $inviteId,
              inviteCode: $inviteCode,
              recipientName: $recipientName,
              recipientEmail: $recipientEmail,
              recipientPhone: $recipientPhone,
              channel: $channel,
              inviteAudience: $inviteAudience,
              supporterType: $supporterType,
              notes: $notes,
              status: 'sent',
              inviteEmailStatus: $inviteEmailStatus,
              inviteEmailError: $inviteEmailError,
              reminderCount: 0,
              createdAt: datetime()
            })
            RETURN
              inv.inviteId AS inviteId,
              inv.inviteCode AS inviteCode,
              inv.recipientName AS recipientName,
              inv.recipientEmail AS recipientEmail,
              inv.recipientPhone AS recipientPhone,
              inv.channel AS channel,
              coalesce(inv.inviteAudience, 'individual') AS inviteAudience,
              inv.supporterType AS supporterType,
              inv.status AS status,
              inv.inviteEmailStatus AS inviteEmailStatus,
              inv.inviteEmailError AS inviteEmailError,
              coalesce(inv.reminderCount, 0) AS reminderCount,
              toString(inv.createdAt) AS createdAt
            """,
            {
                "inviteId": invite_id,
                "inviteCode": invite_code,
                "recipientName": recipient_name,
                "recipientEmail": recipient_email,
                "recipientPhone": recipient_phone,
                "channel": channel,
                "inviteAudience": invite_audience,
                "supporterType": supporter_type,
                "notes": _clean_text(payload.notes),
                "inviteEmailStatus": invite_email_status,
                "inviteEmailError": invite_email_error or "",
            },
        )
    if not records:
        raise HTTPException(status_code=500, detail="Unable to create invite")
    result = records[0].data()
    result["emailSent"] = invite_email_sent
    result["emailStatus"] = invite_email_status
    if invite_email_error:
        result["emailError"] = invite_email_error
    return result


@router.post("/survey-invites")
def create_survey_invite(payload: SurveyInviteCreate):
    invite_id = str(uuid4())
    conversation_id = _clean_text(payload.conversation_id)
    topic = _clean_text(payload.topic)
    invite_link = _clean_text(payload.invite_link)
    recipient_name = _clean_text(payload.recipient_name)
    recipient_email = _clean_text(payload.recipient_email)
    recipient_phone = _clean_text(payload.recipient_phone)
    channel = _clean_text(payload.channel) or "manual"
    invite_audience = _clean_text(payload.invite_audience) or "individual"
    notes = _clean_text(payload.notes)
    if not conversation_id:
        raise HTTPException(status_code=400, detail="Conversation is required")
    if not invite_link:
        raise HTTPException(status_code=400, detail="Invite link is required")

    invite_email_sent = False
    invite_email_status = "not_attempted"
    invite_email_error = ""
    if channel.lower() == "email":
        invite_email_sent, invite_email_status, invite_email_error = _send_survey_invite_email(
            recipient_email,
            recipient_name,
            topic,
            invite_link,
            notes,
        )

    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            """
            CREATE (inv:SurveyInvite {
              inviteId: $inviteId,
              conversationId: $conversationId,
              topic: $topic,
              inviteLink: $inviteLink,
              recipientName: $recipientName,
              recipientEmail: $recipientEmail,
              recipientPhone: $recipientPhone,
              channel: $channel,
              inviteAudience: $inviteAudience,
              notes: $notes,
              status: 'sent',
              inviteEmailStatus: $inviteEmailStatus,
              inviteEmailError: $inviteEmailError,
              createdAt: datetime()
            })
            WITH inv
            OPTIONAL MATCH (c:Conversation {id: $conversationId})
            FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END |
              MERGE (inv)-[:INVITES_TO]->(c)
            )
            RETURN
              inv.inviteId AS inviteId,
              inv.conversationId AS conversationId,
              inv.topic AS topic,
              inv.inviteLink AS inviteLink,
              inv.recipientName AS recipientName,
              inv.recipientEmail AS recipientEmail,
              inv.recipientPhone AS recipientPhone,
              inv.channel AS channel,
              coalesce(inv.inviteAudience, 'individual') AS inviteAudience,
              inv.status AS status,
              inv.inviteEmailStatus AS inviteEmailStatus,
              inv.inviteEmailError AS inviteEmailError,
              toString(inv.createdAt) AS createdAt
            """,
            {
                "inviteId": invite_id,
                "conversationId": conversation_id,
                "topic": topic,
                "inviteLink": invite_link,
                "recipientName": recipient_name,
                "recipientEmail": recipient_email,
                "recipientPhone": recipient_phone,
                "channel": channel,
                "inviteAudience": invite_audience,
                "notes": notes,
                "inviteEmailStatus": invite_email_status,
                "inviteEmailError": invite_email_error or "",
            },
        )
    if not records:
        raise HTTPException(status_code=500, detail="Unable to create survey invite")
    result = records[0].data()
    result["emailSent"] = invite_email_sent
    result["emailStatus"] = invite_email_status
    if invite_email_error:
        result["emailError"] = invite_email_error
    return result


@router.post("/event-invites")
def create_event_invite(payload: EventInviteCreate):
    invite_link = _clean_text(payload.invite_link)
    event_name = _clean_text(payload.event_name)
    recipient_name = _clean_text(payload.recipient_name)
    notes = _clean_text(payload.notes)
    channel = (_clean_text(payload.channel) or "email").lower()
    if channel != "email":
        raise HTTPException(status_code=400, detail="Only email event invites are sent by this endpoint")
    if not invite_link:
        raise HTTPException(status_code=400, detail="Invite link is required")

    recipients = []
    single_email = _clean_text(payload.recipient_email)
    if single_email:
        recipients.append(single_email)
    for email in payload.recipient_emails or []:
        cleaned = _clean_text(email)
        if cleaned:
            recipients.append(cleaned)
    recipients = list(dict.fromkeys(recipients))
    if not recipients:
        raise HTTPException(status_code=400, detail="Recipient email is required")

    results = []
    sent_count = 0
    for email in recipients:
        sent, status, error = _send_event_invite_email(
            email,
            recipient_name if len(recipients) == 1 else "",
            event_name,
            invite_link,
            notes,
        )
        if sent:
            sent_count += 1
        results.append({"recipientEmail": email, "emailSent": sent, "emailStatus": status, "emailError": error or ""})

    return {
        "emailSent": sent_count > 0 and sent_count == len(recipients),
        "sentCount": sent_count,
        "failedCount": len(recipients) - sent_count,
        "totalCount": len(recipients),
        "emailStatus": "sent" if sent_count == len(recipients) else ("partial" if sent_count else (results[0]["emailStatus"] if results else "failed")),
        "results": results,
    }


@router.post("/supporter-invites/{invite_code}/remind")
def remind_supporter_invite(invite_code: str, payload: SupporterInviteReminderCreate):
    code = _clean_text(invite_code)
    if not code:
        raise HTTPException(status_code=400, detail="Invite code is required")

    driver = get_driver()
    with _db_session(driver) as session:
        invite_records = _execute_read(
            session,
            """
            MATCH (inv:SupporterInvite {inviteCode: $inviteCode})
            RETURN
              inv.recipientEmail AS recipientEmail,
              inv.recipientName AS recipientName,
              inv.inviteCode AS inviteCode,
              coalesce(inv.supporterType, 'Supporter') AS supporterType,
              coalesce(inv.reminderCount, 0) AS currentReminderCount
            """,
            {"inviteCode": code},
        )

    if not invite_records:
        raise HTTPException(status_code=404, detail="Invite not found")

    invite_data = invite_records[0].data()
    recipient_email = invite_data.get("recipientEmail")
    recipient_name = invite_data.get("recipientName") or "მეგობარო"
    supporter_type = invite_data.get("supporterType") or "Supporter"
    email_sent, email_status, email_error = _send_supporter_reminder_email(
        recipient_email, recipient_name, code, supporter_type
    )

    with _db_session(driver) as session:
        records = _execute_write(
            session,
            """
            MATCH (inv:SupporterInvite {inviteCode: $inviteCode})
            SET inv.reminderCount = coalesce(inv.reminderCount, 0) + 1,
                inv.lastReminderAt = datetime(),
                inv.lastReminderChannel = $channel,
                inv.lastReminderNote = $note,
                inv.lastReminderEmailStatus = $emailStatus,
                inv.lastReminderEmailError = $emailError,
                inv.updatedAt = datetime()
            RETURN
              inv.inviteId AS inviteId,
              inv.inviteCode AS inviteCode,
              coalesce(inv.status, 'sent') AS status,
              coalesce(inv.reminderCount, 0) AS reminderCount,
              toString(inv.lastReminderAt) AS lastReminderAt,
              inv.lastReminderEmailStatus AS emailStatus,
              inv.lastReminderEmailError AS emailError
            """,
            {
                "inviteCode": code,
                "channel": _clean_text(payload.channel) or "manual",
                "note": _clean_text(payload.note),
                "emailStatus": email_status,
                "emailError": email_error or "",
            },
        )

    if not records:
        raise HTTPException(status_code=404, detail="Invite not found")

    result = records[0].data()

    result["emailSent"] = email_sent
    result["emailStatus"] = email_status
    if email_error:
        result["emailError"] = email_error

    return result


@router.post("/supporter-signup")
def supporter_signup(payload: SupporterSignupCreate):
    submission = _build_supporter_signup_submission(payload)
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            MERGE (signup:SupporterSignupSubmission {email: $email, status: 'pending'})
            ON CREATE SET signup.signupId = randomUUID(), signup.createdAt = datetime()
            SET signup.firstName = $firstName,
                signup.lastName = $lastName,
                signup.birthDate = $birthDate,
                signup.phone = $phone,
                signup.address = $address,
                signup.profession = $profession,
                signup.socialMedia = $socialMedia,
                signup.formerPartyMember = $formerPartyMember,
                signup.timeAvailability = $timeAvailability,
                signup.interests = $interests,
                signup.whatsappGroup = $whatsappGroup,
                signup.interestedInMembership = $interestedInMembership,
                signup.additionalComments = $additionalComments,
                signup.agreesWithManifesto = $agreesWithManifesto,
                signup.inviteCode = $inviteCode,
                signup.signupSource = 'public_signup',
                signup.submittedAt = datetime(),
                signup.updatedAt = datetime()
            """,
            submission,
        )
        if submission["inviteCode"]:
            _execute_write(
                session,
                """
                MATCH (inv:SupporterInvite {inviteCode: $inviteCode})
                MATCH (signup:SupporterSignupSubmission {email: $email, status: 'pending'})
                SET inv.status = 'submitted',
                    inv.submittedAt = datetime(),
                    inv.submittedEmail = $email,
                    inv.updatedAt = datetime()
                MERGE (inv)-[:SUBMITTED_FORM]->(signup)
                """,
                {"inviteCode": submission["inviteCode"], "email": submission["email"]},
            )
    return {
        "saved": True,
        "email": submission["email"],
        "inviteCode": submission["inviteCode"],
        "status": "pending",
    }


@router.get("/supporter-signups/pending")
def list_pending_supporter_signups(limit: int = Query(100, ge=1, le=1000)):
    driver = get_driver()
    with _db_session(driver) as session:
        rows = _execute_read(
            session,
            """
            MATCH (signup:SupporterSignupSubmission)
            WHERE coalesce(signup.status, 'pending') = 'pending'
            RETURN
              signup.signupId AS signupId,
              signup.email AS email,
              coalesce(signup.inviteCode, '') AS inviteCode,
              coalesce(signup.firstName, '') AS firstName,
              coalesce(signup.lastName, '') AS lastName,
              coalesce(signup.supporterType, 'Supporter') AS supporterType,
              coalesce(signup.phone, '') AS phone,
              coalesce(signup.timeAvailability, 'Unspecified') AS timeAvailability,
              coalesce(signup.address, '') AS address,
              coalesce(signup.about, '') AS about,
              coalesce(signup.gender, '') AS gender,
              signup.age AS age,
              coalesce(signup.educationLevels, []) AS educationLevels,
              coalesce(signup.skills, []) AS skills,
              coalesce(signup.tags, []) AS tags,
              coalesce(signup.involvementAreas, []) AS involvementAreas,
              coalesce(signup.interests, []) AS interests,
              coalesce(signup.agreesWithManifesto, false) AS agreesWithManifesto,
              coalesce(signup.interestedInMembership, false) AS interestedInMembership,
              coalesce(signup.facebookGroupMember, false) AS facebookGroupMember,
              toString(coalesce(signup.submittedAt, signup.createdAt)) AS createdAt
            ORDER BY coalesce(signup.submittedAt, signup.createdAt) DESC
            LIMIT $limit
            """,
            {"limit": int(limit)},
        )
    return [row.data() for row in rows]


@router.post("/supporter-signups/{email}/approve")
def approve_pending_supporter_signup(email: str):
    target_email = _clean_text(email)
    if not target_email:
        raise HTTPException(status_code=400, detail="Email is required")
    driver = get_driver()
    with _db_session(driver) as session:
        rows = _execute_read(
            session,
            """
            MATCH (signup:SupporterSignupSubmission {email: $email})
            WHERE coalesce(signup.status, 'pending') = 'pending'
            RETURN
              signup.email AS email,
              coalesce(signup.firstName, '') AS firstName,
              coalesce(signup.lastName, '') AS lastName,
              coalesce(signup.phone, '') AS phone,
              coalesce(signup.supporterType, 'Supporter') AS supporterType,
              coalesce(signup.gender, '') AS gender,
              signup.age AS age,
              coalesce(signup.address, '') AS address,
              signup.lat AS lat,
              signup.lon AS lon,
              signup.effortHours AS effortHours,
              signup.eventsAttendedCount AS eventsAttendedCount,
              signup.referralCount AS referralCount,
              signup.tasksCompleted AS tasksCompleted,
              coalesce(signup.about, '') AS about,
              coalesce(signup.agreesWithManifesto, false) AS agreesWithManifesto,
              coalesce(signup.timeAvailability, 'Unspecified') AS timeAvailability,
              coalesce(signup.interestedInMembership, false) AS interestedInMembership,
              coalesce(signup.facebookGroupMember, false) AS facebookGroupMember,
              coalesce(signup.educationLevels, []) AS educationLevels,
              coalesce(signup.skills, []) AS skills,
              coalesce(signup.tags, []) AS tags,
              coalesce(signup.involvementAreas, []) AS involvementAreas,
              coalesce(signup.inviteCode, '') AS inviteCode
            """,
            {"email": target_email},
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Pending supporter/member not found")

        pending = rows[0].data()
        upsert_person(
            PersonUpsert(
                email=pending["email"],
                firstName=pending.get("firstName") or "",
                lastName=pending.get("lastName") or "",
                gender=pending.get("gender") or "",
                age=pending.get("age"),
                phone=pending.get("phone") or "",
                lat=pending.get("lat"),
                lon=pending.get("lon"),
                effortHours=pending.get("effortHours"),
                eventsAttendedCount=pending.get("eventsAttendedCount"),
                referralCount=pending.get("referralCount"),
                tasksCompleted=pending.get("tasksCompleted"),
                supporterType=pending.get("supporterType") or "Supporter",
                address=pending.get("address") or "",
                timeAvailability=pending.get("timeAvailability") or "Unspecified",
                about=pending.get("about") or "",
                agreesWithManifesto=bool(pending.get("agreesWithManifesto")),
                interestedInMembership=bool(pending.get("interestedInMembership")),
                facebookGroupMember=bool(pending.get("facebookGroupMember")),
                educationLevels=pending.get("educationLevels") or [],
                tags=pending.get("tags") or [],
                skills=pending.get("skills") or [],
                involvementAreas=pending.get("involvementAreas") or [],
            )
        )

        rows = _execute_write(
            session,
            """
            MATCH (signup:SupporterSignupSubmission {email: $email})
            WHERE coalesce(signup.status, 'pending') = 'pending'
            MATCH (p:Person {email: $email})
            SET signup.status = 'approved',
                signup.approvedAt = datetime(),
                signup.updatedAt = datetime(),
                p.signupSource = 'public_signup',
                p.networkApprovalStatus = 'approved',
                p.networkApprovedAt = datetime(),
                p.networkApprovalUpdatedAt = datetime(),
                p.updatedAt = datetime()
            MERGE (signup)-[:APPROVED_TO]->(p)
            WITH signup, p
            FOREACH (_ IN CASE WHEN coalesce(signup.inviteCode, '') = '' THEN [] ELSE [1] END |
                MERGE (inv:SupporterInvite {inviteCode: signup.inviteCode})
                SET inv.status = 'converted',
                    inv.convertedAt = datetime(),
                    inv.convertedEmail = $email,
                    inv.updatedAt = datetime()
                MERGE (inv)-[:CONVERTED_TO]->(p)
                MERGE (inv)-[:SUBMITTED_FORM]->(signup)
            )
            RETURN
              p.email AS email,
              coalesce(p.networkApprovalStatus, 'approved') AS status,
              toString(p.networkApprovedAt) AS approvedAt
            """,
            {"email": target_email},
        )
    if not rows:
        raise HTTPException(status_code=404, detail="Pending supporter/member not found")
    return rows[0].data()


@router.post("/supporter-signups/by-id/{signup_id}/approve")
def approve_pending_supporter_signup_by_id(signup_id: str):
    target_signup_id = _clean_text(signup_id)
    if not target_signup_id:
        raise HTTPException(status_code=400, detail="Signup id is required")
    driver = get_driver()
    with _db_session(driver) as session:
        rows = _execute_read(
            session,
            """
            MATCH (signup:SupporterSignupSubmission {signupId: $signupId})
            WHERE coalesce(signup.status, 'pending') = 'pending'
            RETURN
              signup.signupId AS signupId,
              signup.email AS email,
              coalesce(signup.firstName, '') AS firstName,
              coalesce(signup.lastName, '') AS lastName,
              coalesce(signup.phone, '') AS phone,
              coalesce(signup.supporterType, 'Supporter') AS supporterType,
              coalesce(signup.gender, '') AS gender,
              signup.age AS age,
              coalesce(signup.address, '') AS address,
              signup.lat AS lat,
              signup.lon AS lon,
              signup.effortHours AS effortHours,
              signup.eventsAttendedCount AS eventsAttendedCount,
              signup.referralCount AS referralCount,
              signup.tasksCompleted AS tasksCompleted,
              coalesce(signup.about, '') AS about,
              coalesce(signup.agreesWithManifesto, false) AS agreesWithManifesto,
              coalesce(signup.timeAvailability, 'Unspecified') AS timeAvailability,
              coalesce(signup.interestedInMembership, false) AS interestedInMembership,
              coalesce(signup.facebookGroupMember, false) AS facebookGroupMember,
              coalesce(signup.educationLevels, []) AS educationLevels,
              coalesce(signup.skills, []) AS skills,
              coalesce(signup.tags, []) AS tags,
              coalesce(signup.involvementAreas, []) AS involvementAreas,
              coalesce(signup.inviteCode, '') AS inviteCode
            """,
            {"signupId": target_signup_id},
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Pending supporter/member not found")
        pending = rows[0].data()
        upsert_person(
            PersonUpsert(
                email=pending["email"],
                firstName=pending.get("firstName") or "",
                lastName=pending.get("lastName") or "",
                gender=pending.get("gender") or "",
                age=pending.get("age"),
                phone=pending.get("phone") or "",
                lat=pending.get("lat"),
                lon=pending.get("lon"),
                effortHours=pending.get("effortHours"),
                eventsAttendedCount=pending.get("eventsAttendedCount"),
                referralCount=pending.get("referralCount"),
                tasksCompleted=pending.get("tasksCompleted"),
                supporterType=pending.get("supporterType") or "Supporter",
                address=pending.get("address") or "",
                timeAvailability=pending.get("timeAvailability") or "Unspecified",
                about=pending.get("about") or "",
                agreesWithManifesto=bool(pending.get("agreesWithManifesto")),
                interestedInMembership=bool(pending.get("interestedInMembership")),
                facebookGroupMember=bool(pending.get("facebookGroupMember")),
                educationLevels=pending.get("educationLevels") or [],
                tags=pending.get("tags") or [],
                skills=pending.get("skills") or [],
                involvementAreas=pending.get("involvementAreas") or [],
            )
        )
        rows = _execute_write(
            session,
            """
            MATCH (signup:SupporterSignupSubmission {signupId: $signupId})
            WHERE coalesce(signup.status, 'pending') = 'pending'
            MATCH (p:Person {email: signup.email})
            SET signup.status = 'approved',
                signup.approvedAt = datetime(),
                signup.updatedAt = datetime(),
                p.signupSource = 'public_signup',
                p.networkApprovalStatus = 'approved',
                p.networkApprovedAt = datetime(),
                p.networkApprovalUpdatedAt = datetime(),
                p.updatedAt = datetime()
            MERGE (signup)-[:APPROVED_TO]->(p)
            WITH signup, p
            FOREACH (_ IN CASE WHEN coalesce(signup.inviteCode, '') = '' THEN [] ELSE [1] END |
                MERGE (inv:SupporterInvite {inviteCode: signup.inviteCode})
                SET inv.status = 'converted',
                    inv.convertedAt = datetime(),
                    inv.convertedEmail = signup.email,
                    inv.updatedAt = datetime()
                MERGE (inv)-[:CONVERTED_TO]->(p)
                MERGE (inv)-[:SUBMITTED_FORM]->(signup)
            )
            RETURN
              p.email AS email,
              coalesce(p.networkApprovalStatus, 'approved') AS status,
              toString(p.networkApprovedAt) AS approvedAt
            """,
            {"signupId": target_signup_id},
        )
    if not rows:
        raise HTTPException(status_code=404, detail="Pending supporter/member not found")
    return rows[0].data()


@router.post("/supporter-signups/{email}/decline")
def decline_pending_supporter_signup(email: str):
    target_email = _clean_text(email)
    if not target_email:
        raise HTTPException(status_code=400, detail="Email is required")
    driver = get_driver()
    with _db_session(driver) as session:
        rows = _execute_read(
            session,
            """
            MATCH (signup:SupporterSignupSubmission {email: $email})
            WHERE coalesce(signup.status, 'pending') = 'pending'
            RETURN
              signup.email AS email,
              coalesce(signup.firstName, '') AS firstName,
              coalesce(signup.lastName, '') AS lastName,
              coalesce(signup.phone, '') AS phone,
              coalesce(signup.birthDate, '') AS birthDate,
              coalesce(signup.address, '') AS address,
              coalesce(signup.profession, '') AS profession,
              coalesce(signup.socialMedia, '') AS socialMedia,
              coalesce(signup.formerPartyMember, '') AS formerPartyMember,
              coalesce(signup.timeAvailability, '') AS timeAvailability,
              coalesce(signup.interests, []) AS interests,
              coalesce(signup.whatsappGroup, '') AS whatsappGroup,
              coalesce(signup.interestedInMembership, '') AS interestedInMembership,
              coalesce(signup.additionalComments, '') AS additionalComments,
              coalesce(signup.agreesWithManifesto, false) AS agreesWithManifesto,
              coalesce(signup.inviteCode, '') AS inviteCode,
              toString(signup.createdAt) AS createdAt
            """,
            {"email": target_email},
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Pending supporter/member not found")

        # Update signup status to declined
        _execute_write(
            session,
            """
            MATCH (signup:SupporterSignupSubmission {email: $email})
            WHERE coalesce(signup.status, 'pending') = 'pending'
            SET signup.status = 'declined',
                signup.declinedAt = datetime(),
                signup.updatedAt = datetime()
            """,
            {"email": target_email},
        )
    return {"email": target_email, "status": "declined"}


@router.post("/supporter-signups/by-id/{signup_id}/decline")
def decline_pending_supporter_signup_by_id(signup_id: str):
    target_signup_id = _clean_text(signup_id)
    if not target_signup_id:
        raise HTTPException(status_code=400, detail="Signup id is required")
    driver = get_driver()
    with _db_session(driver) as session:
        rows = _execute_read(
            session,
            """
            MATCH (signup:SupporterSignupSubmission {signupId: $signupId})
            WHERE coalesce(signup.status, 'pending') = 'pending'
            RETURN
              signup.signupId AS signupId,
              signup.email AS email,
              coalesce(signup.firstName, '') AS firstName,
              coalesce(signup.lastName, '') AS lastName,
              coalesce(signup.phone, '') AS phone,
              coalesce(signup.birthDate, '') AS birthDate,
              coalesce(signup.address, '') AS address,
              coalesce(signup.profession, '') AS profession,
              coalesce(signup.socialMedia, '') AS socialMedia,
              coalesce(signup.formerPartyMember, '') AS formerPartyMember,
              coalesce(signup.timeAvailability, '') AS timeAvailability,
              coalesce(signup.interests, []) AS interests,
              coalesce(signup.whatsappGroup, '') AS whatsappGroup,
              coalesce(signup.interestedInMembership, '') AS interestedInMembership,
              coalesce(signup.additionalComments, '') AS additionalComments,
              coalesce(signup.agreesWithManifesto, false) AS agreesWithManifesto,
              coalesce(signup.inviteCode, '') AS inviteCode,
              toString(signup.createdAt) AS createdAt
            """,
            {"signupId": target_signup_id},
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Pending supporter/member not found")

        # Update signup status to declined
        _execute_write(
            session,
            """
            MATCH (signup:SupporterSignupSubmission {signupId: $signupId})
            WHERE coalesce(signup.status, 'pending') = 'pending'
            SET signup.status = 'declined',
                signup.declinedAt = datetime(),
                signup.updatedAt = datetime()
            """,
            {"signupId": target_signup_id},
        )
    return {"signupId": target_signup_id, "status": "declined"}


@router.get("/supporter-signup-config")
def get_supporter_signup_config():
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            """
            MATCH (cfg:PlatformConfig {id: 'supporter-signup'})
            RETURN
              coalesce(cfg.welcomeVideoUrl, '') AS welcomeVideoUrl,
              coalesce(cfg.thankYouVideoUrl, '') AS thankYouVideoUrl,
              toString(cfg.updatedAt) AS updatedAt
            """,
        )
    if not records:
        return {"welcomeVideoUrl": "", "thankYouVideoUrl": "", "updatedAt": None}
    row = records[0]
    return {
        "welcomeVideoUrl": row.get("welcomeVideoUrl") or "",
        "thankYouVideoUrl": row.get("thankYouVideoUrl") or "",
        "updatedAt": row.get("updatedAt"),
    }


@router.patch("/supporter-signup-config")
def update_supporter_signup_config(payload: SupporterSignupConfigUpdate):
    welcome_video_url = _clean_text(payload.welcome_video_url)
    thank_you_video_url = _clean_text(payload.thank_you_video_url)
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            """
            MERGE (cfg:PlatformConfig {id: 'supporter-signup'})
            ON CREATE SET cfg.createdAt = datetime()
            SET cfg.welcomeVideoUrl = $welcomeVideoUrl,
                cfg.thankYouVideoUrl = $thankYouVideoUrl,
                cfg.updatedAt = datetime()
            RETURN
              coalesce(cfg.welcomeVideoUrl, '') AS welcomeVideoUrl,
              coalesce(cfg.thankYouVideoUrl, '') AS thankYouVideoUrl,
              toString(cfg.updatedAt) AS updatedAt
            """,
            {
                "welcomeVideoUrl": welcome_video_url,
                "thankYouVideoUrl": thank_you_video_url,
            },
        )
    if not records:
        raise HTTPException(status_code=500, detail="Unable to update signup config")
    row = records[0]
    return {
        "welcomeVideoUrl": row.get("welcomeVideoUrl") or "",
        "thankYouVideoUrl": row.get("thankYouVideoUrl") or "",
        "updatedAt": row.get("updatedAt"),
    }


@router.get("/supporter-invite-groups-config")
def get_supporter_invite_groups_config():
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_read(
            session,
            """
            MATCH (cfg:PlatformConfig {id: 'supporter-invite-groups'})
            RETURN
              coalesce(cfg.everyoneGroupEmail, '') AS everyoneGroupEmail,
              coalesce(cfg.verifiedGroupEmail, '') AS verifiedGroupEmail,
              coalesce(cfg.registeredGroupEmail, '') AS registeredGroupEmail,
              toString(cfg.updatedAt) AS updatedAt
            """,
        )
    if not records:
        return {
            "everyoneGroupEmail": "",
            "verifiedGroupEmail": "",
            "registeredGroupEmail": "",
            "updatedAt": None,
        }
    row = records[0]
    return {
        "everyoneGroupEmail": row.get("everyoneGroupEmail") or "",
        "verifiedGroupEmail": row.get("verifiedGroupEmail") or "",
        "registeredGroupEmail": row.get("registeredGroupEmail") or "",
        "updatedAt": row.get("updatedAt"),
    }


@router.patch("/supporter-invite-groups-config")
def update_supporter_invite_groups_config(payload: SupporterInviteGroupsConfigUpdate):
    everyone_group_email = _clean_text(payload.everyone_group_email)
    verified_group_email = _clean_text(payload.verified_group_email)
    registered_group_email = _clean_text(payload.registered_group_email)
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            """
            MERGE (cfg:PlatformConfig {id: 'supporter-invite-groups'})
            ON CREATE SET cfg.createdAt = datetime()
            SET cfg.everyoneGroupEmail = $everyoneGroupEmail,
                cfg.verifiedGroupEmail = $verifiedGroupEmail,
                cfg.registeredGroupEmail = $registeredGroupEmail,
                cfg.updatedAt = datetime()
            RETURN
              coalesce(cfg.everyoneGroupEmail, '') AS everyoneGroupEmail,
              coalesce(cfg.verifiedGroupEmail, '') AS verifiedGroupEmail,
              coalesce(cfg.registeredGroupEmail, '') AS registeredGroupEmail,
              toString(cfg.updatedAt) AS updatedAt
            """,
            {
                "everyoneGroupEmail": everyone_group_email,
                "verifiedGroupEmail": verified_group_email,
                "registeredGroupEmail": registered_group_email,
            },
        )
    if not records:
        raise HTTPException(status_code=500, detail="Unable to update invite group config")
    row = records[0]
    return {
        "everyoneGroupEmail": row.get("everyoneGroupEmail") or "",
        "verifiedGroupEmail": row.get("verifiedGroupEmail") or "",
        "registeredGroupEmail": row.get("registeredGroupEmail") or "",
        "updatedAt": row.get("updatedAt"),
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


@router.get("/people/{identifier}", response_model=PersonProfileOut)
def get_person_profile(identifier: str):
    profile = _load_profile(identifier)
    if not profile:
        raise HTTPException(status_code=404, detail="Person not found")
    return profile


@router.patch("/people/{identifier}", response_model=PersonProfileOut)
def update_person_profile(identifier: str, payload: PersonProfileUpdate):
    existing = _load_profile(identifier)
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
    MATCH (p:Person)
    WHERE p.email = $identifier
       OR p.personId = $identifier
       OR p.generatedId = $identifier
       OR elementId(p) = $identifier
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
        _execute_write(session, query, {"identifier": identifier, **updated})
    profile = _load_profile(identifier)
    return profile or updated


@router.post("/people", response_model=PersonProfileOut)
def upsert_person(payload: PersonUpsert):
    email = _clean_text(payload.email)
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    supporter_type = _normalize_supporter_type(payload.supporterType, "Supporter")
    tags = _split_list(payload.tags) if payload.tags is not None else None
    skills = _split_list(payload.skills) if payload.skills is not None else None
    involvement_areas = (
        _split_list(payload.involvementAreas)
        if payload.involvementAreas is not None
        else None
    )
    education_levels = (
        _split_list(payload.educationLevels)
        if payload.educationLevels is not None
        else None
    )
    education = _clean_text(payload.education) if payload.education is not None else None
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
        p.tasksCompleted = coalesce($tasksCompleted, p.tasksCompleted),
        p.about = coalesce($about, p.about),
        p.agreesWithManifesto = coalesce($agreesWithManifesto, p.agreesWithManifesto),
        p.interestedInMembership = coalesce($interestedInMembership, p.interestedInMembership),
        p.facebookGroupMember = coalesce($facebookGroupMember, p.facebookGroupMember)
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
                "about": _clean_text(payload.about),
                "agreesWithManifesto": payload.agreesWithManifesto,
                "interestedInMembership": payload.interestedInMembership,
                "facebookGroupMember": payload.facebookGroupMember,
            },
        )
        if education_levels is not None:
            _execute_write(
                session,
                """
                MATCH (p:Person {email: $email})
                OPTIONAL MATCH (p)-[oldEdu:HAS_EDUCATION]->(:EducationLevel)
                DELETE oldEdu
                WITH p
                UNWIND $educationLevels AS educationName
                MERGE (ed:EducationLevel {name: educationName})
                MERGE (p)-[:HAS_EDUCATION]->(ed)
                """,
                {"email": email, "educationLevels": education_levels},
            )
        elif education is not None:
            _execute_write(
                session,
                """
                MATCH (p:Person {email: $email})
                OPTIONAL MATCH (p)-[oldEdu:HAS_EDUCATION]->(:EducationLevel)
                DELETE oldEdu
                WITH p
                FOREACH (_ IN CASE WHEN $education = '' THEN [] ELSE [1] END |
                    MERGE (ed:EducationLevel {name: $education})
                    MERGE (p)-[:HAS_EDUCATION]->(ed)
                )
                """,
                {"email": email, "education": education},
            )
        if tags is not None:
            _execute_write(
                session,
                """
                MATCH (p:Person {email: $email})
                OPTIONAL MATCH (p)-[oldTag:HAS_TAG]->(:Tag)
                DELETE oldTag
                WITH p
                UNWIND $tags AS tagName
                MERGE (tag:Tag {name: tagName})
                MERGE (p)-[:HAS_TAG]->(tag)
                """,
                {"email": email, "tags": tags},
            )
        if skills is not None:
            _execute_write(
                session,
                """
                MATCH (p:Person {email: $email})
                OPTIONAL MATCH (p)-[oldSkill:CAN_CONTRIBUTE_WITH]->(:Skill)
                DELETE oldSkill
                WITH p
                UNWIND $skills AS skillName
                MERGE (sk:Skill {name: skillName})
                MERGE (p)-[:CAN_CONTRIBUTE_WITH]->(sk)
                """,
                {"email": email, "skills": skills},
            )
        if involvement_areas is not None:
            _execute_write(
                session,
                """
                MATCH (p:Person {email: $email})
                OPTIONAL MATCH (p)-[oldInterest:INTERESTED_IN]->(:InvolvementArea)
                DELETE oldInterest
                WITH p
                UNWIND $involvementAreas AS areaName
                MERGE (ia:InvolvementArea {name: areaName})
                MERGE (p)-[:INTERESTED_IN]->(ia)
                """,
                {"email": email, "involvementAreas": involvement_areas},
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
                ON CREATE SET a.lat = row.lat, a.lon = row.lon
                ON MATCH SET a.lat = coalesce(row.lat, a.lat),
                            a.lon = coalesce(row.lon, a.lon)
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
                p.timeAvailability = coalesce(row.timeAvailability, p.timeAvailability),
                // New Georgian fields
                p.profession = coalesce(row.profession, p.profession),
                p.socialMedia = coalesce(row.socialMedia, p.socialMedia),
                p.wasPartyMember = coalesce(row.wasPartyMember, p.wasPartyMember),
                p.partyDetails = coalesce(row.partyDetails, p.partyDetails),
                p.about = coalesce(row.about, p.about),
                p.howToHelp = coalesce(row.howToHelp, p.howToHelp),
                p.additionalComments = coalesce(row.additionalComments, p.additionalComments),
                p.agreesWithManifesto = coalesce(row.agreesWithManifesto, p.agreesWithManifesto),
                p.interestedInMembership = coalesce(row.interestedInMembership, p.interestedInMembership),
                p.personalId = coalesce(row.personalId, p.personalId),
                p.whatsappChat = coalesce(row.whatsappChat, p.whatsappChat),
                p.dateOfBirth = coalesce(row.dateOfBirth, p.dateOfBirth)
            WITH p, row
            FOREACH (_ IN CASE WHEN row.education IS NULL OR row.education = '' THEN [] ELSE [1] END |
                MERGE (ed:EducationLevel {name: row.education})
                MERGE (p)-[:HAS_EDUCATION]->(ed)
            )
            FOREACH (skill IN coalesce(row.skills, []) |
                MERGE (sk:Skill {name: skill})
                MERGE (p)-[:CAN_CONTRIBUTE_WITH]->(sk)
            )
            FOREACH (topic IN coalesce(row.topicsOfInterest, []) |
                MERGE (t:Topic {name: topic})
                MERGE (p)-[:INTERESTED_IN]->(t)
            )
            FOREACH (area IN coalesce(row.involvementAreas, []) |
                MERGE (ia:InvolvementArea {name: area})
                MERGE (p)-[:WANTS_TO_HELP_WITH]->(ia)
            )
            MERGE (st:SupporterType {name: coalesce(row.supporterType, 'Supporter')})
            MERGE (p)-[:CLASSIFIED_AS]->(st)
            WITH p, row
            FOREACH (_ IN CASE WHEN row.address IS NULL OR row.address = '' THEN [] ELSE [1] END |
                MERGE (a:Address {fullAddress: row.address})
                ON CREATE SET a.lat = row.lat, a.lon = row.lon
                ON MATCH SET a.lat = coalesce(row.lat, a.lat),
                            a.lon = coalesce(row.lon, a.lon)
                MERGE (p)-[:LIVES_AT]->(a)
            )
            """,
            {"rows": rows},
        )
    return {"created": len(rows)}


@router.get("/dashboard", response_model=DashboardOut)
def crm_dashboard():
    df = _load_supporter_summary_df()
    # Get accurate total from Neo4j if DataFrame is empty
    if df.empty:
        total_df = _query_df("MATCH (p:Person) RETURN count(p) AS cnt")
        total_people = int(total_df.iloc[0]["cnt"]) if not total_df.empty else 0
    else:
        total_people = int(len(df))
    supporters = int((df["group"] == "Supporter").sum()) if not df.empty else 0
    members = int((df["group"] == "Member").sum()) if not df.empty else 0
    avg_effort = float(df["effortScore"].mean()) if total_people and not df.empty else 0.0

    group_counts = (
        df["group"]
        .value_counts()
        .rename_axis("group")
        .reset_index(name="count")
        .to_dict(orient="records")
        if not df.empty
        else []
    )
    # Gender distribution - treat 'nan' as Male, '1.0' as Female, empty as Unknown
    gender_counts = _query_df(
        """
        MATCH (p:Person)
        WITH p,
          CASE
            WHEN p.gender IS NULL OR p.gender = '' THEN 'U'
            WHEN toString(p.gender) IN ['1', '1.0'] OR toLower(toString(p.gender)) CONTAINS 'female' THEN 'F'
            WHEN toString(p.gender) = 'nan' OR toString(p.gender) IN ['2', '2.0'] OR toLower(toString(p.gender)) CONTAINS 'male' THEN 'M'
            WHEN toString(p.gender) IN ['3', '3.0'] OR toLower(toString(p.gender)) CONTAINS 'other' THEN 'O'
            ELSE 'M'
          END AS normalizedGender
        RETURN normalizedGender AS gender, count(*) AS count
        ORDER BY count DESC
        """
    ).to_dict(orient="records")
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

    # New Georgian data queries
    age_groups = _query_df(
        """
        MATCH (p:Person)
        WITH toInteger(p.age) AS calculatedAge
        WHERE calculatedAge IS NOT NULL AND calculatedAge >= 0
        WITH calculatedAge,
          CASE
            WHEN calculatedAge < 18 THEN 'Under 18'
            WHEN calculatedAge <= 30 THEN '18-30'
            WHEN calculatedAge <= 45 THEN '31-45'
            WHEN calculatedAge <= 60 THEN '46-60'
            ELSE '60+'
          END AS ageGroup
        RETURN ageGroup AS group, count(*) AS count
        ORDER BY
          CASE ageGroup
            WHEN 'Under 18' THEN 0
            WHEN '18-30' THEN 1
            WHEN '31-45' THEN 2
            WHEN '46-60' THEN 3
            WHEN '60+' THEN 4
            ELSE 5
          END
        """
    ).to_dict(orient="records")

    # Top professions
    profession_counts = _query_df(
        """
        MATCH (p:Person)
        WHERE p.profession IS NOT NULL AND p.profession <> ''
        RETURN p.profession AS profession, count(*) AS count
        ORDER BY count DESC
        LIMIT 10
        """
    ).to_dict(orient="records")

    # Region distribution with detailed Tbilisi districts
    region_counts = _query_df(
        """
        MATCH (p:Person)
        OPTIONAL MATCH (p)-[:LIVES_AT]->(a:Address)
        WITH p,
          CASE
            WHEN a.fullAddress IS NOT NULL AND a.fullAddress <> '' THEN a.fullAddress
            WHEN p.address IS NOT NULL AND p.address <> '' THEN p.address
            ELSE ''
          END AS address
        WITH address,
          CASE
            WHEN toLower(address) CONTAINS 'ბათუმი' OR toLower(address) CONTAINS 'batumi' THEN 'Batumi'
            WHEN toLower(address) CONTAINS 'ქუთაისი' OR toLower(address) CONTAINS 'kutaisi' THEN 'Kutaisi'
            WHEN toLower(address) CONTAINS 'რუსთავი' OR toLower(address) CONTAINS 'rustavi' THEN 'Rustavi'
            WHEN toLower(address) CONTAINS 'გორი' OR toLower(address) CONTAINS 'gori' THEN 'Gori'
            WHEN toLower(address) CONTAINS 'ზუგდიდი' OR toLower(address) CONTAINS 'zugdidi' THEN 'Zugdidi'
            WHEN toLower(address) CONTAINS 'თელავი' OR toLower(address) CONTAINS 'telavi' THEN 'Telavi'
            WHEN toLower(address) CONTAINS 'ახმეტა' OR toLower(address) CONTAINS 'akhmeta' THEN 'Akhmeta'
            WHEN toLower(address) CONTAINS 'ოზურგეთი' OR toLower(address) CONTAINS 'ozurgeti' THEN 'Ozurgeti'
            WHEN toLower(address) CONTAINS 'ხაშური' OR toLower(address) CONTAINS 'khashuri' THEN 'Khashuri'
            WHEN toLower(address) CONTAINS 'ჭიათურა' OR toLower(address) CONTAINS 'chiatura' THEN 'Chiatura'
            WHEN toLower(address) CONTAINS 'მცხეთა' OR toLower(address) CONTAINS 'mtskheta' THEN 'Mtskheta'
            WHEN toLower(address) CONTAINS 'მარტვილი' OR toLower(address) CONTAINS 'martvili' THEN 'Martvili'
            WHEN toLower(address) CONTAINS 'ტყიბული' OR toLower(address) CONTAINS 'tkibuli' THEN 'Tkibuli'
            WHEN toLower(address) CONTAINS 'საგარეჯო' OR toLower(address) CONTAINS 'sagarejo' THEN 'Sagarejo'
            WHEN toLower(address) CONTAINS 'სიღნაღი' OR toLower(address) CONTAINS 'sighnaghi' THEN 'Sighnaghi'
            WHEN toLower(address) CONTAINS 'ქობულეთი' OR toLower(address) CONTAINS 'kobuleti' THEN 'Kobuleti'
            WHEN toLower(address) CONTAINS 'ვაკე' THEN 'Tbilisi - Vake'
            WHEN toLower(address) CONTAINS 'საბურთალო' THEN 'Tbilisi - Saburtalo'
            WHEN toLower(address) CONTAINS 'დიღომი' OR toLower(address) CONTAINS 'dighomi' THEN 'Tbilisi - Dighomi'
            WHEN toLower(address) CONTAINS 'მუხიანი' OR toLower(address) CONTAINS 'mukhiani' THEN 'Tbilisi - Mukhiani'
            WHEN toLower(address) CONTAINS 'ვარკეთილი' OR toLower(address) CONTAINS 'varketili' THEN 'Tbilisi - Varketili'
            WHEN toLower(address) CONTAINS 'გლდანი' OR toLower(address) CONTAINS 'gldani' THEN 'Tbilisi - Gldani'
            WHEN toLower(address) CONTAINS 'სამგორი' OR toLower(address) CONTAINS 'samgori' THEN 'Tbilisi - Samgori'
            WHEN toLower(address) CONTAINS 'ნაძალადევი' OR toLower(address) CONTAINS 'nadzaladevi' THEN 'Tbilisi - Nadzaladevi'
            WHEN toLower(address) CONTAINS 'ისანი' OR toLower(address) CONTAINS 'isani' THEN 'Tbilisi - Isani'
            WHEN toLower(address) CONTAINS 'კრწანისი' OR toLower(address) CONTAINS 'krtsanisi' THEN 'Tbilisi - Krtsanisi'
            WHEN toLower(address) CONTAINS 'მთაწმინდა' OR toLower(address) CONTAINS 'mtatsminda' THEN 'Tbilisi - Mtatsminda'
            WHEN toLower(address) CONTAINS 'სოლოლაკი' OR toLower(address) CONTAINS 'sololaki' THEN 'Tbilisi - Sololaki'
            WHEN toLower(address) CONTAINS 'ვერა' OR toLower(address) CONTAINS 'vera' THEN 'Tbilisi - Vera'
            WHEN toLower(address) CONTAINS 'დიდუბე' OR toLower(address) CONTAINS 'didube' THEN 'Tbilisi - Didube'
            WHEN toLower(address) CONTAINS 'ჩუღურეთი' OR toLower(address) CONTAINS 'chugureti' THEN 'Tbilisi - Chugureti'
            WHEN toLower(address) CONTAINS 'აბანოთუბანი' OR toLower(address) CONTAINS 'abanotubani' THEN 'Tbilisi - Abanotubani'
            WHEN toLower(address) CONTAINS 'ვაზისუბანი' OR toLower(address) CONTAINS 'vazisubani' THEN 'Tbilisi - Vazisubani'
            WHEN toLower(address) CONTAINS 'თბილისი' OR toLower(address) CONTAINS 'tbilisi' THEN 'Tbilisi (Other)'
            WHEN address = '' THEN 'Unknown'
            ELSE 'Other Regions'
          END AS region
        RETURN region AS region, count(*) AS count
        ORDER BY count DESC
        """
    ).to_dict(orient="records")

    # Region grouping with major cities shown individually
    region_grouped = _query_df(
        """
        MATCH (p:Person)
        OPTIONAL MATCH (p)-[:LIVES_AT]->(a:Address)
        WITH p,
          CASE
            WHEN a.fullAddress IS NOT NULL AND a.fullAddress <> '' THEN a.fullAddress
            WHEN p.address IS NOT NULL AND p.address <> '' THEN p.address
            ELSE ''
          END AS address
        WITH address,
          CASE
            WHEN toLower(address) CONTAINS 'თბილისი' OR toLower(address) CONTAINS 'tbilisi' THEN 'Tbilisi'
            WHEN toLower(address) CONTAINS 'ბათუმი' OR toLower(address) CONTAINS 'batumi' THEN 'Batumi'
            WHEN toLower(address) CONTAINS 'ქუთაისი' OR toLower(address) CONTAINS 'kutaisi' THEN 'Kutaisi'
            WHEN toLower(address) CONTAINS 'რუსთავი' OR toLower(address) CONTAINS 'rustavi' THEN 'Rustavi'
            WHEN toLower(address) CONTAINS 'გორი' OR toLower(address) CONTAINS 'gori' THEN 'Gori'
            WHEN toLower(address) CONTAINS 'ზუგდიდი' OR toLower(address) CONTAINS 'zugdidi' THEN 'Zugdidi'
            WHEN toLower(address) CONTAINS 'თელავი' OR toLower(address) CONTAINS 'telavi' THEN 'Telavi'
            WHEN toLower(address) CONTAINS 'ახმეტა' OR toLower(address) CONTAINS 'akhmeta' THEN 'Akhmeta'
            WHEN toLower(address) CONTAINS 'ოზურგეთი' OR toLower(address) CONTAINS 'ozurgeti' THEN 'Ozurgeti'
            WHEN toLower(address) CONTAINS 'ხაშური' OR toLower(address) CONTAINS 'khashuri' THEN 'Khashuri'
            WHEN toLower(address) CONTAINS 'ჭიათურა' OR toLower(address) CONTAINS 'chiatura' THEN 'Chiatura'
            WHEN toLower(address) CONTAINS 'მცხეთა' OR toLower(address) CONTAINS 'mtskheta' THEN 'Mtskheta'
            WHEN toLower(address) CONTAINS 'მარტვილი' OR toLower(address) CONTAINS 'martvili' THEN 'Martvili'
            WHEN toLower(address) CONTAINS 'სამტრედია' OR toLower(address) CONTAINS 'samtredia' THEN 'Samtredia'
            WHEN toLower(address) CONTAINS 'თეძამი' OR toLower(address) CONTAINS 'tedzami' THEN 'Tedzami'
            WHEN toLower(address) CONTAINS 'საგარეჯო' OR toLower(address) CONTAINS 'sagarejo' THEN 'Sagarejo'
            WHEN toLower(address) CONTAINS 'სიღნაღი' OR toLower(address) CONTAINS 'sighnaghi' THEN 'Sighnaghi'
            WHEN toLower(address) CONTAINS 'ქობულეთი' OR toLower(address) CONTAINS 'kobuleti' THEN 'Kobuleti'
            WHEN toLower(address) CONTAINS 'ფოთი' OR toLower(address) CONTAINS 'poti' THEN 'Poti'
            WHEN toLower(address) CONTAINS 'სოხუმი' OR toLower(address) CONTAINS 'sukhumi' THEN 'Sukhumi'
            WHEN address = '' THEN 'Unknown'
            ELSE 'Other Regions'
          END AS regionGroup
        RETURN regionGroup AS group, count(*) AS count
        ORDER BY count DESC
        """
    ).to_dict(orient="records")

    # Party membership history
    party_membership = _query_df(
        """
        MATCH (p:Person)
        WITH p,
          CASE WHEN p.wasPartyMember = true THEN 'Former Party Member'
               ELSE 'No Party History'
          END AS partyStatus
        RETURN partyStatus AS status, count(*) AS count
        """
    ).to_dict(orient="records")

    # Involvement areas (what people want to help with)
    involvement_areas = _query_df(
        """
        MATCH (p:Person)-[:WANTS_TO_HELP_WITH]->(ia:InvolvementArea)
        RETURN ia.name AS area, count(*) AS count
        ORDER BY count DESC
        LIMIT 10
        """
    ).to_dict(orient="records")

    # Combined expertise (Skills + InvolvementAreas + Topics)
    combined_expertise = _query_df(
        """
        MATCH (p:Person)
        OPTIONAL MATCH (p)-[:CAN_CONTRIBUTE_WITH]->(s:Skill)
        OPTIONAL MATCH (p)-[:WANTS_TO_HELP_WITH]->(ia:InvolvementArea)
        OPTIONAL MATCH (p)-[:INTERESTED_IN]->(t:Topic)
        WITH p, s, ia, t
        WHERE s IS NOT NULL OR ia IS NOT NULL OR t IS NOT NULL
        WITH
          CASE
            WHEN s IS NOT NULL THEN s.name
            WHEN ia IS NOT NULL THEN ia.name
            WHEN t IS NOT NULL THEN t.name
          END AS expertise
        RETURN expertise, count(*) AS count
        ORDER BY count DESC
        LIMIT 15
        """
    ).to_dict(orient="records")

    # Detailed regional breakdown (Georgian regions)
    region_detail = _query_df(
        """
        MATCH (p:Person)
        OPTIONAL MATCH (p)-[:LIVES_AT]->(a:Address)
        WITH p, coalesce(a.fullAddress, p.address, '') AS address
        WITH p, address,
          CASE
            WHEN toLower(address) CONTAINS 'თბილისი' OR toLower(address) CONTAINS 'tbilisi' THEN 'Tbilisi'
            WHEN toLower(address) CONTAINS 'ბათუმი' OR toLower(address) CONTAINS 'batumi' OR toLower(address) CONTAINS 'აჭარა' THEN 'Adjara (Batumi)'
            WHEN toLower(address) CONTAINS 'ქუთაისი' OR toLower(address) CONTAINS 'kutaisi' OR toLower(address) CONTAINS 'იმერეთი' THEN 'Imereti (Kutaisi)'
            WHEN toLower(address) CONTAINS 'თელავი' OR toLower(address) CONTAINS 'telavi' OR toLower(address) CONTAINS 'კახეთი' THEN 'Kakheti (Telavi)'
            WHEN toLower(address) CONTAINS 'გორი' OR toLower(address) CONTAINS 'gori' OR toLower(address) CONTAINS 'შიდა ქართლი' THEN 'Shida Kartli (Gori)'
            WHEN toLower(address) CONTAINS 'რუსთავი' OR toLower(address) CONTAINS 'rustavi' OR toLower(address) CONTAINS 'ქვემო ქართლი' THEN 'Kvemo Kartli (Rustavi)'
            WHEN toLower(address) CONTAINS 'ზუგდიდი' OR toLower(address) CONTAINS 'zugdidi' OR toLower(address) CONTAINS 'სამეგრელო' THEN 'Samegrelo (Zugdidi)'
            WHEN toLower(address) CONTAINS 'პანკისი' OR toLower(address) CONTAINS 'pankisi' OR toLower(address) CONTAINS 'ხევსურეთი' THEN 'Other Regions'
            WHEN address = '' THEN 'Unknown'
            ELSE 'Other Regions'
          END AS region
        RETURN region AS region, count(*) AS count
        ORDER BY count DESC
        """
    ).to_dict(orient="records")

    # Membership growth by join date
    membership_growth = _query_df(
        """
        MATCH (p:Person)
        WHERE p.joinDate IS NOT NULL AND p.joinDate <> ''
        WITH p,
          CASE
            WHEN p.joinDate CONTAINS '2024' THEN '2024'
            WHEN p.joinDate CONTAINS '17.11.2025' OR p.joinDate CONTAINS '17.11.2045' THEN 'Nov 2025'
            WHEN p.joinDate CONTAINS '2025' THEN '2025'
            ELSE 'Other'
          END AS joinPeriod
        RETURN joinPeriod AS period, count(*) AS count
        ORDER BY
          CASE joinPeriod
            WHEN '2024' THEN 1
            WHEN '2025' THEN 2
            WHEN 'Nov 2025' THEN 3
            ELSE 4
          END
        """
    ).to_dict(orient="records")

    # Engagement readiness (high potential supporters)
    engagement_ready = _query_df(
        """
        MATCH (p:Person)
        WHERE p.age IS NOT NULL
          AND (p.timeAvailability IS NOT NULL AND p.timeAvailability <> '')
          AND (p.profession IS NOT NULL AND p.profession <> '')
        WITH p,
          CASE
            WHEN p.age <= 40 AND (toLower(p.timeAvailability) CONTAINS 'კვირის' OR toLower(p.timeAvailability) CONTAINS 'შაბათ' OR toLower(p.timeAvailability) CONTAINS 'თავისუფალი') THEN 'High Engagement'
            WHEN p.age <= 50 AND (toLower(p.timeAvailability) CONTAINS 'კვირის' OR toLower(p.timeAvailability) CONTAINS 'შაბათ') THEN 'Medium Engagement'
            ELSE 'Low Engagement'
          END AS engagement
        RETURN engagement AS level, count(*) AS count
        ORDER BY
          CASE engagement
            WHEN 'High Engagement' THEN 1
            WHEN 'Medium Engagement' THEN 2
            WHEN 'Low Engagement' THEN 3
            ELSE 4
          END
        """
    ).to_dict(orient="records")

    # Time availability grouped into Weekends vs Weekdays
    time_availability_grouped = _query_df(
        """
        MATCH (p:Person)
        WHERE p.timeAvailability IS NOT NULL AND p.timeAvailability <> ''
        WITH p,
          CASE
            WHEN toLower(p.timeAvailability) CONTAINS 'შაბათ' OR toLower(p.timeAvailability) CONTAINS 'კვირას' THEN 'Weekends'
            WHEN toLower(p.timeAvailability) CONTAINS 'სამუშაო' OR toLower(p.timeAvailability) CONTAINS 'ორშაბათი' OR toLower(p.timeAvailability) CONTAINS 'სამშაბათს' OR toLower(p.timeAvailability) CONTAINS 'ხუთშაბათს' THEN 'Weekdays'
            WHEN toLower(p.timeAvailability) CONTAINS 'კვირის' OR toLower(p.timeAvailability) CONTAINS 'ნებისმიერ' OR toLower(p.timeAvailability) CONTAINS 'თავისუფალი' OR toLower(p.timeAvailability) CONTAINS 'ნებისმიერ დროს' THEN 'Flexible'
            ELSE 'Other/Unspecified'
          END AS timeGroup
        RETURN timeGroup AS group, count(*) AS count
        ORDER BY
          CASE timeGroup
            WHEN 'Weekends' THEN 1
            WHEN 'Weekdays' THEN 2
            WHEN 'Flexible' THEN 3
            ELSE 4
          END
        """
    ).to_dict(orient="records")

    # Regional Skills Distribution - Top involvement areas by major cities
    regional_skills = _query_df(
        """
        MATCH (p:Person)-[:WANTS_TO_HELP_WITH]->(ia:InvolvementArea)
        MATCH (p)-[:LIVES_AT]->(a:Address)
        WITH a, ia,
          CASE
            WHEN toLower(a.fullAddress) CONTAINS 'თბილისი' OR toLower(a.fullAddress) CONTAINS 'tbilisi' THEN 'Tbilisi'
            WHEN toLower(a.fullAddress) CONTAINS 'ბათუმი' OR toLower(a.fullAddress) CONTAINS 'batumi' THEN 'Batumi'
            WHEN toLower(a.fullAddress) CONTAINS 'ქუთაისი' OR toLower(a.fullAddress) CONTAINS 'kutaisi' THEN 'Kutaisi'
            WHEN toLower(a.fullAddress) CONTAINS 'რუსთავი' OR toLower(a.fullAddress) CONTAINS 'rustavi' THEN 'Rustavi'
            WHEN toLower(a.fullAddress) CONTAINS 'გორი' OR toLower(a.fullAddress) CONTAINS 'gori' THEN 'Gori'
            WHEN toLower(a.fullAddress) CONTAINS 'ზუგდიდი' OR toLower(a.fullAddress) CONTAINS 'zugdidi' THEN 'Zugdidi'
            WHEN toLower(a.fullAddress) CONTAINS 'თელავი' OR toLower(a.fullAddress) CONTAINS 'telavi' THEN 'Telavi'
            ELSE 'Other'
          END AS region
        WHERE region <> 'Other'
        RETURN region, ia.name AS skill, count(*) AS count
        ORDER BY region, count DESC
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
            "ageGroups": age_groups,
            "professionCounts": profession_counts,
            "regionCounts": region_counts,
            "regionGrouped": region_grouped,
            "regionDetail": region_detail,
            "partyMembership": party_membership,
            "involvementAreas": involvement_areas,
            "membershipGrowth": membership_growth,
            "engagementReady": engagement_ready,
            "manifesto": manifesto_df.to_dict(orient="records") if not manifesto_df.empty else [],
            "membership": membership_df.to_dict(orient="records") if not membership_df.empty else [],
            "facebook": facebook_df.to_dict(orient="records") if not facebook_df.empty else [],
            "timeAvailability": time_df.to_dict(orient="records") if not time_df.empty else [],
            "timeAvailabilityGrouped": time_availability_grouped,
            "involvement": involve_df.to_dict(orient="records") if not involve_df.empty else [],
            "skills": skills_df.to_dict(orient="records") if not skills_df.empty else [],
            "regionalSkills": regional_skills,
            "combinedExpertise": combined_expertise,
            "taskFeed": task_feed,
        },
    }


@router.get("/map", response_model=List[MapPersonOut])
def crm_map_data():
    df = _load_map_data_df()
    if df.empty:
        return []
    # Filter to only include records with valid coordinates
    df = df[df["lat"].notna() & df["lon"].notna()]
    df = df.where(pd.notnull(df), None)
    records = df.to_dict(orient="records")
    for record in records:
        if "age" in record:
            value = record["age"]
            if value is None or (isinstance(value, float) and np.isnan(value)):
                record["age"] = None
            else:
                record["age"] = int(value)
    return records


# ---------------------------------------------------------------------------
# End of CRM People Routes
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Segment endpoints
# ---------------------------------------------------------------------------


def _segment_record_to_out(row: dict) -> dict:
    """Attach parsed filterSpec for API responses."""
    data = dict(row)
    raw = data.pop("filterJson", None)
    filt = segment_filter_from_stored_value(raw)
    data["filterSpec"] = filt.model_dump(mode="json")
    return data


@router.get("/segments", response_model=List[SegmentOut])
def list_segments():
    driver = get_driver()
    query = """
    MATCH (s:Segment)
    RETURN
      s.segmentId AS segmentId,
      s.name AS name,
      coalesce(s.description,'') AS description,
      toString(s.updatedAt) AS updatedAt,
      coalesce(s.filterJson, '{}') AS filterJson
    ORDER BY s.updatedAt DESC
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query)
    return [_segment_record_to_out(record.data()) for record in records]


@router.post("/segments", response_model=SegmentOut)
def create_segment(payload: SegmentCreate):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Segment name is required")
    filter_json = payload.filterSpec.model_dump_json()
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
      toString(s.updatedAt) AS updatedAt,
      coalesce(s.filterJson, '{}') AS filterJson
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {"name": payload.name.strip(), "description": payload.description or "", "filterJson": filter_json},
        )
    if not records:
        raise HTTPException(status_code=500, detail="Segment could not be created")
    return _segment_record_to_out(records[0].data())


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


@router.get("/segments/{segment_id}/count", response_model=SegmentCountOut)
def count_saved_segment(segment_id: str):
    driver = get_driver()
    query = """
    MATCH (s:Segment {segmentId: $id})
    RETURN coalesce(s.filterJson, '{}') AS filterJson
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query, {"id": segment_id})
    if not records:
        raise HTTPException(status_code=404, detail="Segment not found")
    row = records[0].data() if hasattr(records[0], "data") else dict(records[0])
    filt = segment_filter_from_stored_value(row.get("filterJson"))
    count_query, params = _build_segment_count_query(filt)
    with _db_session(driver) as session:
        rows = _execute_read(session, count_query, params)
    if not rows:
        return SegmentCountOut(count=0)
    cnt_row = rows[0].data() if hasattr(rows[0], "data") else dict(rows[0])
    cnt = cnt_row.get("cnt")
    try:
        n = int(cnt)
    except (TypeError, ValueError):
        n = 0
    return SegmentCountOut(count=n)


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
    row = records[0].data() if hasattr(records[0], "data") else dict(records[0])
    filt = segment_filter_from_stored_value(row.get("filterJson"))
    person_query, params = _build_segment_query(filt, limit)
    with _db_session(driver) as session:
        rows = _execute_read(session, person_query, params)
    return [record.data() for record in rows]


# ---------------------------------------------------------------------------
# Furry-friend endpoints
# ---------------------------------------------------------------------------

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
    from uuid import uuid4
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
