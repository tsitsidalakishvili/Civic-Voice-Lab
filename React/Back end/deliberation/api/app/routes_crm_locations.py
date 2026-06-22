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
from .services.location_service import (
    aggregate_people_by_neighborhood,
    people_for_map,
    people_for_neighborhood,
    unmatched_people,
)

router = APIRouter()


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
    people = _load_people_for_locations()
    return aggregate_people_by_neighborhood(
        people,
        _location_filters(
            supporterType,
            memberStatus,
            campaignId,
            tag,
            skill,
            gender,
            ageGroup,
            engagementStatus,
        ),
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
    people = _load_people_for_locations()
    return people_for_map(
        people,
        _location_filters(
            supporterType,
            memberStatus,
            campaignId,
            tag,
            skill,
            gender,
            ageGroup,
            engagementStatus,
        ),
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
    people = _load_people_for_locations()
    return people_for_neighborhood(
        people,
        neighborhood_id,
        _location_filters(
            supporterType,
            memberStatus,
            campaignId,
            tag,
            skill,
            gender,
            ageGroup,
            engagementStatus,
        ),
    )


@router.get("/locations/unmatched")
def crm_unmatched_locations():
    return unmatched_people(_load_people_for_locations())





