import pandas as pd
import streamlit as st

from crm.db.neo4j import run_query, run_write
from crm.utils.text import clean_text


def upsert_person(payload):
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
        p.effortHours = coalesce($effortHours, p.effortHours),
        p.eventsAttendedCount = coalesce($eventsAttendedCount, p.eventsAttendedCount),
        p.referralCount = coalesce($referralCount, p.referralCount)
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
    result = run_write(query, payload)
    if result:
        search_people.clear()
        load_person_profile.clear()
        get_distinct_values.clear()
    return result


@st.cache_data(ttl=30, show_spinner=False)
def search_people(query, limit=50):
    query = clean_text(query)
    try:
        limit = int(limit)
    except Exception:
        limit = 50
    limit = max(5, min(200, limit))
    if not query:
        return pd.DataFrame()
    return run_query(
        """
        MATCH (p:Person)
        OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(st:SupporterType)
        WITH p, collect(DISTINCT st.name) AS types
        WITH p,
          (trim(coalesce(p.firstName,'') + ' ' + coalesce(p.lastName,''))) AS fullName,
          CASE WHEN any(x IN types WHERE toLower(x) CONTAINS 'member') THEN 'Member' ELSE 'Supporter' END AS group
        WHERE toLower(p.email) CONTAINS toLower($q)
           OR toLower(fullName) CONTAINS toLower($q)
        RETURN
          CASE WHEN fullName = '' THEN p.email ELSE fullName END AS fullName,
          p.email AS email,
          group AS group,
          coalesce(p.timeAvailability, 'Unspecified') AS timeAvailability
        ORDER BY fullName
        LIMIT $limit
        """,
        {"q": query, "limit": limit},
        silent=True,
    )


@st.cache_data(ttl=30, show_spinner=False)
def load_person_profile(email):
    email = clean_text(email)
    if not email:
        return pd.DataFrame()
    return run_query(
        """
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
        """,
        {"email": email},
        silent=True,
    )


def update_person_profile(email, payload):
    email = clean_text(email)
    if not email:
        return False
    # Only updates core fields; tags/skills/involvement are left as-is for now.
    result = run_write(
        """
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
        """,
        {
            "email": email,
            "firstName": clean_text(payload.get("firstName")),
            "lastName": clean_text(payload.get("lastName")),
            "phone": clean_text(payload.get("phone")),
            "gender": clean_text(payload.get("gender")),
            "age": payload.get("age"),
            "timeAvailability": clean_text(payload.get("timeAvailability")),
            "about": clean_text(payload.get("about")),
            "agreesWithManifesto": bool(payload.get("agreesWithManifesto", False)),
            "interestedInMembership": bool(payload.get("interestedInMembership", False)),
            "facebookGroupMember": bool(payload.get("facebookGroupMember", False)),
        },
    )
    if result:
        search_people.clear()
        load_person_profile.clear()
    return result


@st.cache_data(ttl=120, show_spinner=False)
def get_distinct_values(label, prop="name"):
    query = f"""
    MATCH (n:{label})
    WHERE n.{prop} IS NOT NULL
    RETURN DISTINCT n.{prop} AS value
    ORDER BY value
    """
    df = run_query(query, silent=True)
    if df.empty or "value" not in df.columns:
        return []
    return [str(v) for v in df["value"].dropna().tolist() if str(v).strip()]


def bulk_upsert_people(rows):
    if not rows:
        return False
    query = """
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
        p.referralCount = coalesce(row.referralCount, p.referralCount)
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
    """
    result = run_write(query, {"rows": rows})
    if result:
        search_people.clear()
        load_person_profile.clear()
        get_distinct_values.clear()
    return result
