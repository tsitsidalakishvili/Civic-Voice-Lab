"""
Privacy-conscious CRM neighborhood map endpoints.

Freedom Square uses neighborhood-level mapping to understand supporter,
member, and volunteer distribution without exposing exact personal addresses
or exact home coordinates by default.
"""

from typing import Optional

import pandas as pd
from fastapi import APIRouter, Query

from .routes_crm_helpers import _query_df
from .services.crm_snapshot_cache import get_snapshot_token, read_snapshot_people
from .services.location_service import (
    aggregate_people_by_neighborhood,
    people_for_map,
    people_for_neighborhood,
    unmatched_people,
)

router = APIRouter()

_LOCATION_RESPONSE_CACHE: dict[tuple, list[dict]] = {}


def _cache_key(endpoint: str, filters: dict | None = None, extra: str = "") -> tuple:
    filters = filters or {}
    normalized_filters = tuple(sorted((key, str(value or "")) for key, value in filters.items()))
    return (get_snapshot_token(), endpoint, extra, normalized_filters)


def _cached_response(key: tuple, builder):
    if key in _LOCATION_RESPONSE_CACHE:
        return _LOCATION_RESPONSE_CACHE[key]
    if len(_LOCATION_RESPONSE_CACHE) > 80:
        _LOCATION_RESPONSE_CACHE.clear()
    value = builder()
    _LOCATION_RESPONSE_CACHE[key] = value
    return value


def _clean_value(value):
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
    records = []
    for row in clean.to_dict(orient="records"):
        records.append({key: _clean_value(value) for key, value in row.items()})
    return records


def _load_people_for_locations() -> list[dict]:
    cached_people = read_snapshot_people(allow_expired=True)
    if cached_people is not None:
        return cached_people
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


def _location_filters(
    supporter_type: Optional[str] = None,
    member_status: Optional[str] = None,
    campaign_id: Optional[str] = None,
    tag: Optional[str] = None,
    skill: Optional[str] = None,
    gender: Optional[str] = None,
    age_group: Optional[str] = None,
    engagement_status: Optional[str] = None,
) -> dict:
    return {
        "supporterType": supporter_type,
        "memberStatus": member_status,
        "campaignId": campaign_id,
        "tag": tag,
        "skill": skill,
        "gender": gender,
        "ageGroup": age_group,
        "engagementStatus": engagement_status,
    }


@router.get("/map/neighborhoods")
def crm_map_neighborhoods(
    supporterType: Optional[str] = Query(None),
    memberStatus: Optional[str] = Query(None),
    campaignId: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    gender: Optional[str] = Query(None),
    ageGroup: Optional[str] = Query(None),
    engagementStatus: Optional[str] = Query(None),
):
    filters = _location_filters(
        supporterType,
        memberStatus,
        campaignId,
        tag,
        skill,
        gender,
        ageGroup,
        engagementStatus,
    )
    key = _cache_key("neighborhoods", filters)
    return _cached_response(
        key,
        lambda: aggregate_people_by_neighborhood(_load_people_for_locations(), filters),
    )


@router.get("/map/people")
def crm_map_people(
    supporterType: Optional[str] = Query(None),
    memberStatus: Optional[str] = Query(None),
    campaignId: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    gender: Optional[str] = Query(None),
    ageGroup: Optional[str] = Query(None),
    engagementStatus: Optional[str] = Query(None),
):
    filters = _location_filters(
        supporterType,
        memberStatus,
        campaignId,
        tag,
        skill,
        gender,
        ageGroup,
        engagementStatus,
    )
    key = _cache_key("people", filters)
    return _cached_response(
        key,
        lambda: people_for_map(_load_people_for_locations(), filters),
    )

@router.get("/map/neighborhoods/{neighborhood_id}/people")
def crm_map_neighborhood_people(
    neighborhood_id: str,
    supporterType: Optional[str] = Query(None),
    memberStatus: Optional[str] = Query(None),
    campaignId: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    gender: Optional[str] = Query(None),
    ageGroup: Optional[str] = Query(None),
    engagementStatus: Optional[str] = Query(None),
):
    filters = _location_filters(
        supporterType,
        memberStatus,
        campaignId,
        tag,
        skill,
        gender,
        ageGroup,
        engagementStatus,
    )
    key = _cache_key("neighborhood_people", filters, neighborhood_id)
    return _cached_response(
        key,
        lambda: people_for_neighborhood(_load_people_for_locations(), neighborhood_id, filters),
    )


@router.get("/locations/unmatched")
def crm_unmatched_locations():
    key = _cache_key("unmatched")
    return _cached_response(key, lambda: unmatched_people(_load_people_for_locations()))
