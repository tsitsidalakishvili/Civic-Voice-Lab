import json

import streamlit as st

from crm.db.neo4j import run_query, run_write
from crm.utils.text import clean_text


def upsert_segment(name, description, filter_spec):
    name = clean_text(name)
    if not name:
        return False
    description = clean_text(description) or ""
    filter_json = json.dumps(filter_spec or {}, ensure_ascii=False)
    result = run_write(
        """
        MERGE (s:Segment {name: $name})
        ON CREATE SET s.segmentId = randomUUID(), s.createdAt = datetime()
        SET s.description = $description,
            s.filterJson = $filterJson,
            s.updatedAt = datetime()
        """,
        {"name": name, "description": description, "filterJson": filter_json},
    )
    if result:
        list_segments.clear()
        load_segment_filter.clear()
        run_saved_segment.clear()
    return result


@st.cache_data(ttl=30, show_spinner=False)
def list_segments():
    return run_query(
        """
        MATCH (s:Segment)
        RETURN
          s.segmentId AS segmentId,
          s.name AS name,
          coalesce(s.description,'') AS description,
          toString(s.updatedAt) AS updatedAt
        ORDER BY s.updatedAt DESC
        """,
        silent=True,
    )


def delete_segment(segment_id):
    segment_id = clean_text(segment_id)
    if not segment_id:
        return False
    result = run_write(
        """
        MATCH (s:Segment {segmentId: $id})
        DETACH DELETE s
        """,
        {"id": segment_id},
    )
    if result:
        list_segments.clear()
        load_segment_filter.clear()
        run_saved_segment.clear()
    return result


@st.cache_data(ttl=30, show_spinner=False)
def load_segment_filter(segment_id):
    segment_id = clean_text(segment_id)
    if not segment_id:
        return {}
    df = run_query(
        """
        MATCH (s:Segment {segmentId: $id})
        RETURN coalesce(s.filterJson, '{}') AS filterJson
        """,
        {"id": segment_id},
        silent=True,
    )
    if df.empty or "filterJson" not in df.columns:
        return {}
    try:
        return json.loads(df["filterJson"].iloc[0] or "{}")
    except Exception:
        return {}


def run_segment(filter_spec, limit=500):
    filter_spec = filter_spec or {}
    clauses = []
    params = {"limit": max(10, min(2000, int(limit) if str(limit).isdigit() else 500))}

    group = clean_text(filter_spec.get("group"))
    if group in {"Supporter", "Member"}:
        clauses.append("group = $group")
        params["group"] = group

    time_availability = filter_spec.get("timeAvailability") or []
    if isinstance(time_availability, list) and time_availability:
        vals = [str(x) for x in time_availability if str(x).strip()]
        if vals:
            clauses.append("p.timeAvailability IN $timeAvailability")
            params["timeAvailability"] = vals

    tags = filter_spec.get("tags") or []
    if isinstance(tags, list) and tags:
        vals = [str(x) for x in tags if str(x).strip()]
        if vals:
            clauses.append("any(t IN $tags WHERE t IN tags)")
            params["tags"] = vals

    skills = filter_spec.get("skills") or []
    if isinstance(skills, list) and skills:
        vals = [str(x) for x in skills if str(x).strip()]
        if vals:
            clauses.append("any(s IN $skills WHERE s IN skills)")
            params["skills"] = vals

    name_contains = clean_text(filter_spec.get("nameContains"))
    if name_contains:
        clauses.append("toLower(fullName) CONTAINS toLower($nameContains)")
        params["nameContains"] = name_contains

    address_contains = clean_text(filter_spec.get("addressContains"))
    if address_contains:
        clauses.append("toLower(address) CONTAINS toLower($addressContains)")
        params["addressContains"] = address_contains

    min_effort = filter_spec.get("minEffortHours")
    try:
        min_effort_val = float(min_effort) if min_effort is not None and min_effort != "" else None
    except Exception:
        min_effort_val = None
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
    return run_query(query, params=params, silent=True)


@st.cache_data(ttl=30, show_spinner=False)
def run_saved_segment(segment_id, limit=500):
    spec = load_segment_filter(segment_id)
    return run_segment(spec, limit=limit)
