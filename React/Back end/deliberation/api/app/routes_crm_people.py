"""
CRM – contacts / people CRUD, summary, dashboard, map, import/export,
geocoding triggers, segments, distinct-values, and furry-friend registry.
"""
import io
import json
from typing import List, Optional

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
    _extract_municipality,
    SegmentFilter,
)

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


# ---------------------------------------------------------------------------
# Local helper: load map data
# ---------------------------------------------------------------------------

def _load_map_data_df() -> pd.DataFrame:
    df = _query_df(
        """
        MATCH (p:Person)
        OPTIONAL MATCH (p)-[:LIVES_AT]->(a:Address)
        WITH p,
             coalesce(p.lat, a.latitude) AS lat,
             coalesce(p.lon, a.longitude) AS lon,
             coalesce(p.address, a.fullAddress) AS address
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
    df = _apply_geocoding(df)
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


# ---------------------------------------------------------------------------
# Segment endpoints
# ---------------------------------------------------------------------------

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
