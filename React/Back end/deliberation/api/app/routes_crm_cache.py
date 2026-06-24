from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter

from .routes_crm_helpers import _query_df
from .services.crm_snapshot_cache import (
    delete_snapshot,
    get_snapshot_meta,
    read_snapshot_people,
    write_snapshot,
)

router = APIRouter()


def _clean_value(value: Any):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _clean_records(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    clean = df.where(pd.notnull(df), None)
    return [
        {key: _clean_value(value) for key, value in row.items()}
        for row in clean.to_dict(orient="records")
    ]


def fetch_crm_snapshot_people() -> list[dict]:
    df = _query_df(
        """
        MATCH (p:Person)
        OPTIONAL MATCH (p)-[:LIVES_AT]->(addr:Address)
        OPTIONAL MATCH (p)-[:IS_SUPPORTER]->(s:Supporter)
        OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(st:SupporterType)
        OPTIONAL MATCH (p)-[:HAS_TAG]->(tag:Tag)
        OPTIONAL MATCH (p)-[:WANTS_TO_HELP_WITH]->(skill:InvolvementArea)
        OPTIONAL MATCH (p)-[:INTERESTED_IN]->(interest:InvolvementArea)
        OPTIONAL MATCH (p)-[eventRel:REGISTERED_FOR]->(:Event)
        OPTIONAL MATCH (p)-[:HAS_ACTIVITY]->(activity:Activity)
        WITH p, addr, s,
             collect(DISTINCT st.name) AS types,
             collect(DISTINCT tag.name) AS tags,
             collect(DISTINCT coalesce(skill.name, interest.name)) AS skills,
             count(DISTINCT eventRel) AS campaignParticipation,
             0 AS lastActivityCount30d,
             max(activity.createdAt) AS lastEngagement
        RETURN
          coalesce(p.personId, p.email, elementId(p)) AS personId,
          p.email AS email,
          coalesce(p.fullName, trim(coalesce(p.firstName, '') + ' ' + coalesce(p.lastName, ''))) AS fullName,
          p.firstName AS firstName,
          p.lastName AS lastName,
          p.phone AS phone,
          p.age AS age,
          coalesce(p.gender, 'Unspecified') AS gender,
          coalesce(p.timeAvailability, 'Unspecified') AS timeAvailability,
          p.agreesWithManifesto AS agreesWithManifesto,
          p.supporterType AS group,
          coalesce(p.status, 'Active') AS status,
          coalesce(p.city, addr.city) AS city,
          coalesce(p.district, addr.district) AS district,
          coalesce(p.area, addr.area) AS area,
          coalesce(p.micro_area, p.microArea, addr.micro_area, addr.microArea) AS micro_area,
          coalesce(p.neighborhood, p.neighbourhood, addr.neighborhood, addr.neighbourhood) AS neighborhood,
          coalesce(p.address, addr.fullAddress, addr.address) AS address,
          coalesce(p.lat, addr.lat, addr.latitude) AS lat,
          coalesce(p.lon, p.lng, addr.lon, addr.lng, addr.longitude) AS lon,
          toString(p.createdAt) AS createdAt,
          toString(p.updatedAt) AS updatedAt,
          types,
          tags,
          skills,
          campaignParticipation,
          lastActivityCount30d,
          toString(lastEngagement) AS lastEngagement
        """,
        {},
    )
    return _clean_records(df)


def estimate_changes_since(last_fetched_at: str | None) -> int | None:
    if not last_fetched_at:
        return None
    df = _query_df(
        """
        MATCH (p:Person)
        WHERE p.updatedAt IS NOT NULL AND toString(p.updatedAt) > $lastFetchedAt
        RETURN count(p) AS changes
        """,
        {"lastFetchedAt": last_fetched_at},
    )
    if df.empty:
        return 0
    return int(df.iloc[0].get("changes") or 0)


@router.get("/cache/crm/status")
def crm_cache_status():
    meta = get_snapshot_meta()
    changes = estimate_changes_since(meta.get("lastFetchedAt")) if meta.get("exists") else None
    return get_snapshot_meta(changes_since_fetch=changes)


@router.post("/cache/crm/refresh")
def crm_cache_refresh():
    people = fetch_crm_snapshot_people()
    return write_snapshot(people, source="manual_refresh")


@router.delete("/cache/crm")
def crm_cache_delete():
    return delete_snapshot()


@router.get("/cache/crm/people")
def crm_cache_people():
    people = read_snapshot_people(allow_expired=True)
    return people or []
