"""
Shared constants, helpers, and Pydantic models used across multiple CRM sub-modules.
"""
import json
import os
import re
from functools import lru_cache
from typing import Any, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .db import get_active_database, get_driver

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------
TASK_STATUSES = ["Open", "In Progress", "Done", "Cancelled"]
EVENT_STATUSES = ["Planned", "Scheduled", "Completed", "Cancelled"]
EVENT_REGISTRATION_STATUSES = ["Registered", "Attended", "Cancelled", "No Show"]
CAMPAIGN_STATUSES = [
    "Draft",
    "Funding",
    "Funded",
    "In Progress",
    "Awaiting Verification",
    "Completed",
    "Cancelled",
    "Planned",
    "Active",
    "Paused",
]
PAYMENT_STATUSES = [
    "initiated",
    "pending",
    "succeeded",
    "failed",
    "refunded",
    "cancelled",
]

# ---------------------------------------------------------------------------
# Geocoding / env config
# ---------------------------------------------------------------------------
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
GOOGLE_MAPS_GEOCODE_URL = os.getenv(
    "GOOGLE_MAPS_GEOCODE_URL", "https://maps.googleapis.com/maps/api/geocode/json"
).strip()
CRM_GEOCODE_STRATEGY = os.getenv("CRM_GEOCODE_STRATEGY", "always").strip().lower()
CRM_GEOCODE_CITY_HINT = os.getenv("CRM_GEOCODE_CITY_HINT", "Tbilisi, Georgia").strip()


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


CRM_GEOCODE_MAX_PER_REQUEST = _safe_int(
    os.getenv("CRM_GEOCODE_MAX_PER_REQUEST", "25"), 25
)
CRM_GEOCODE_TIMEOUT_S = _safe_float(os.getenv("CRM_GEOCODE_TIMEOUT_S", "4"), 4.0)
MAX_CONTRIBUTION_AMOUNT = _safe_float(os.getenv("MAX_CONTRIBUTION_AMOUNT", "0"), 0.0)
ENABLE_PUBLIC_CAMPAIGNS = str(os.getenv("ENABLE_PUBLIC_CAMPAIGNS", "1")).strip().lower() in (
    "1",
    "true",
    "yes",
)
ENABLE_PAYMENTS = str(os.getenv("ENABLE_PAYMENTS", "1")).strip().lower() in (
    "1",
    "true",
    "yes",
)

# ---------------------------------------------------------------------------
# Neo4j session helpers
# ---------------------------------------------------------------------------

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


def _query_df(query: str, params: Optional[dict] = None) -> pd.DataFrame:
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_read(session, query, params or {})
    if not records:
        return pd.DataFrame()
    return pd.DataFrame([record.data() for record in records])


def _sanitize_neo4j_value(value: Any) -> Any:
    """Convert Neo4j driver / pandas / numpy scalars to JSON-friendly Python values."""
    if value is None:
        return None
    if isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, (float, np.floating)):
        if pd.isna(value):
            return None
        return float(value)
    if hasattr(value, "item") and not isinstance(value, (str, bytes, dict, list)):
        try:
            return _sanitize_neo4j_value(value.item())
        except Exception:
            pass
    if hasattr(value, "isoformat") and not isinstance(value, str):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return value


def _sanitize_neo4j_row(row: dict) -> dict:
    return {k: _sanitize_neo4j_value(v) for k, v in row.items()}


# ---------------------------------------------------------------------------
# Geocoding helper (Nominatim / OpenStreetMap — no API key required)
# ---------------------------------------------------------------------------

_geocode_cache: dict[str, tuple[float, float] | None] = {}


def geocode_address(address: str) -> tuple[float, float] | None:
    """Return (lat, lon) for *address* using Nominatim, or None on failure.

    Results are cached in-process so the same address is only looked up once
    per server lifetime.  A 1-second timeout prevents slow rows from blocking
    the whole import.
    """
    key = address.strip().lower()
    if key in _geocode_cache:
        return _geocode_cache[key]
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1},
            headers={"User-Agent": "FreedomSquare/1.0 (admin@freedomsquare.ge)"},
            timeout=5,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            result = (float(results[0]["lat"]), float(results[0]["lon"]))
            _geocode_cache[key] = result
            return result
    except Exception:
        pass
    _geocode_cache[key] = None
    return None


# ---------------------------------------------------------------------------
# Text / data helpers
# ---------------------------------------------------------------------------

def _clean_text(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _safe_int_alias(value, default: int) -> int:
    """Alias kept for backward compatibility inside this module."""
    return _safe_int(value, default)


def _normalize_supporter_type(value, default_type="Supporter") -> str:
    text = _clean_text(value)
    if not text:
        return default_type
    return "Member" if "member" in text.lower() else "Supporter"


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


def _format_list_label(values, limit=6):
    items = [str(v).strip() for v in values or [] if str(v).strip()]
    items = sorted(set(items))
    if not items:
        return "None"
    if len(items) > limit:
        return ", ".join(items[:limit]) + f" (+{len(items) - limit} more)"
    return ", ".join(items)


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


# ---------------------------------------------------------------------------
# Campaign budget helper
# ---------------------------------------------------------------------------

def _compute_campaign_budget(
    target_amount: Optional[float],
    fee_percent: Optional[float],
    fee_amount: Optional[float],
    execution_amount: Optional[float],
) -> tuple:
    target = _safe_float(target_amount, 0.0)
    percent = _safe_float(fee_percent, 0.0)
    fee = _safe_float(fee_amount, 0.0)
    execution = _safe_float(execution_amount, 0.0)
    if target > 0 and percent > 0:
        fee = round(target * (percent / 100), 2)
    if target > 0 and execution <= 0:
        execution = round(max(target - fee, 0.0), 2)
    return percent, fee, execution


# ---------------------------------------------------------------------------
# Geocoding helpers
# ---------------------------------------------------------------------------

def _normalize_geocode_address(address: str) -> Optional[str]:
    cleaned = _clean_text(address)
    if not cleaned:
        return None
    if CRM_GEOCODE_CITY_HINT:
        hint = CRM_GEOCODE_CITY_HINT.strip()
        if hint and hint.lower() not in cleaned.lower():
            return f"{cleaned}, {hint}"
    return cleaned


@lru_cache(maxsize=1024)
def _derive_neighbourhood_from_address(address: Optional[str]) -> Optional[str]:
    text = _clean_text(address)
    if not text:
        return None
    lowered = text.lower()
    pairs = [
        ("დიღმის მასივი", "დიღმის მასივი"),
        ("დიდი დიღომ", "დიდი დიღომი"),
        ("სოფ.დიღომ", "დიღომი"),
        ("სოფელი დიღომ", "დიღომი"),
        ("ვაზისუბ", "ვაზისუბანი"),
        ("ვარკეთილ", "ვარკეთილი"),
        ("გლდან", "გლდანი"),
        ("საბურთალ", "საბურთალო"),
        ("ვაჟა", "საბურთალო"),
        ("ნუცუბიძ", "საბურთალო"),
        ("თამარაშვილ", "ვაკე"),
        ("ჭავჭავაძ", "ვაკე"),
        ("ვაკე", "ვაკე"),
        ("ისან", "ისანი"),
        ("ნავთლუღ", "ნავთლუღი"),
        ("ნაძალადევ", "ნაძალადევი"),
        ("ჩუღურეთ", "ჩუღურეთი"),
        ("სოლოლაკ", "სოლოლაკი"),
        ("მთაწმინდ", "მთაწმინდა"),
        ("ვერა", "ვერა"),
        ("ავლაბ", "ავლაბარი"),
        ("ორთაჭალ", "ორთაჭალა"),
        ("სამგორ", "სამგორი"),
        ("ლილო", "ლილო"),
        ("თბილისის ზღვა", "თბილისის ზღვა"),
        ("რუსთავ", "რუსთავი"),
        ("ბათუმ", "ბათუმი"),
        ("ზუგდიდ", "ზუგდიდი"),
        ("მარტვილ", "მარტვილი"),
        ("ოზურგეთ", "ოზურგეთი"),
        ("სიღნაღ", "სიღნაღი"),
        ("საგარეჯ", "საგარეჯო"),
        ("ახმეტ", "ახმეტა"),
    ]
    for needle, label in pairs:
        if needle in lowered:
            return label
    parts = [part.strip() for part in text.split(",") if part.strip()]
    district_index = next((idx for idx, part in enumerate(parts) if "რაიონი" in part), None)
    if district_index is not None and district_index > 0:
        return parts[district_index - 1]
    if len(parts) >= 2 and parts[-1] in {"საქართველო", "Georgia"}:
        return parts[-2]
    return None


NEIGHBOURHOOD_COMPONENT_TYPES = (
    "neighborhood",
    "sublocality_level_1",
    "sublocality",
    "administrative_area_level_3",
    "administrative_area_level_2",
)


def _extract_google_neighbourhood(result: dict) -> Optional[str]:
    components = result.get("address_components") or []
    for component_type in NEIGHBOURHOOD_COMPONENT_TYPES:
        for component in components:
            types = component.get("types") or []
            if component_type in types:
                value = _clean_text(component.get("long_name"))
                if value:
                    return value
    return _derive_neighbourhood_from_address(result.get("formatted_address"))


@lru_cache(maxsize=1024)
def _geocode_address(query: str) -> Optional[dict]:
    if not GOOGLE_MAPS_API_KEY or not query:
        return None
    try:
        response = requests.get(
            GOOGLE_MAPS_GEOCODE_URL,
            params={"address": query, "key": GOOGLE_MAPS_API_KEY},
            timeout=CRM_GEOCODE_TIMEOUT_S,
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
    first_result = results[0]
    location = (first_result.get("geometry") or {}).get("location") or {}
    lat = location.get("lat")
    lon = location.get("lng")
    if lat is None or lon is None:
        return None
    formatted_address = first_result.get("formatted_address")
    return {
        "lat": float(lat),
        "lon": float(lon),
        "formatted_address": formatted_address,
        "neighbourhood": _extract_google_neighbourhood(first_result)
        or _derive_neighbourhood_from_address(query)
        or _derive_neighbourhood_from_address(formatted_address),
    }


def _needs_geocode(strategy: str, lat, lon, address: str) -> bool:
    if strategy == "off" or not address:
        return False
    if strategy == "always":
        return True
    if lat is None or lon is None:
        return True
    if pd.isna(lat) or pd.isna(lon):
        return True
    if lat < -90 or lat > 90:
        return True
    if lon < -180 or lon > 180:
        return True
    return False


def _persist_geocode_updates(rows: List[dict]) -> None:
    if not rows:
        return
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            UNWIND $rows AS row
            WITH row
            MATCH (p:Person {email: row.email})
            SET p.lat = row.lat,
                p.lon = row.lon,
                p.address = CASE
                    WHEN p.address IS NULL OR trim(p.address) = '' THEN row.address
                    ELSE p.address
                END,
                p.neighbourhood = CASE
                    WHEN row.neighbourhood IS NULL OR trim(row.neighbourhood) = '' THEN p.neighbourhood
                    ELSE row.neighbourhood
                END
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


def _apply_geocoding(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or not GOOGLE_MAPS_API_KEY or CRM_GEOCODE_STRATEGY == "off":
        return df
    budget = max(0, CRM_GEOCODE_MAX_PER_REQUEST)
    if budget == 0:
        return df
    updates = []
    for idx, row in df.iterrows():
        if budget <= 0:
            break
        address_value = row.get("address")
        address = "" if address_value is None or pd.isna(address_value) else str(address_value).strip()
        lat = row.get("lat")
        lon = row.get("lon")
        if not _needs_geocode(CRM_GEOCODE_STRATEGY, lat, lon, address):
            continue
        query = _normalize_geocode_address(address)
        if not query:
            continue
        result = _geocode_address(query)
        if not result:
            continue
        df.at[idx, "lat"] = result["lat"]
        df.at[idx, "lon"] = result["lon"]
        formatted_address = result.get("formatted_address")
        neighbourhood = result.get("neighbourhood") or _derive_neighbourhood_from_address(address) or _derive_neighbourhood_from_address(formatted_address)
        address_value = address or formatted_address or None
        if not address and formatted_address:
            df.at[idx, "address"] = formatted_address
        if neighbourhood:
            df.at[idx, "neighbourhood"] = neighbourhood
        email = row.get("email")
        if email:
            updates.append(
                {
                    "email": email,
                    "lat": result["lat"],
                    "lon": result["lon"],
                    "address": address_value,
                    "neighbourhood": neighbourhood,
                }
            )
            budget -= 1
    if updates:
        _persist_geocode_updates(updates)
    return df


# ---------------------------------------------------------------------------
# People enrichment helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Column-matching helpers (used by import)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Segment query builder
# ---------------------------------------------------------------------------

class SegmentFilter(BaseModel):
    model_config = ConfigDict(extra="ignore")

    group: Optional[str] = None
    timeAvailability: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    skills: Optional[List[str]] = None
    nameContains: Optional[str] = None
    addressContains: Optional[str] = None
    minEffortHours: Optional[float] = None


def _decode_stored_filter_json(raw: Any) -> dict:
    """Turn Neo4j/string/bytes/map values into a plain dict for SegmentFilter."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, (bytes, bytearray)):
        try:
            text = raw.decode("utf-8").strip() or "{}"
        except Exception:
            return {}
        try:
            parsed = json.loads(text)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    if isinstance(raw, str):
        text = raw.strip() or "{}"
        try:
            parsed = json.loads(text)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _normalize_segment_filter_keys(d: dict) -> dict:
    """Accept snake_case keys (or mixed) from older payloads."""
    key_map = {
        "time_availability": "timeAvailability",
        "name_contains": "nameContains",
        "address_contains": "addressContains",
        "min_effort_hours": "minEffortHours",
    }
    out: dict = {}
    for key, val in (d or {}).items():
        nk = key_map.get(str(key), str(key))
        if nk not in out:
            out[nk] = val
    return out


def segment_filter_from_stored_value(raw: Any) -> SegmentFilter:
    """Parse filterJson from DB into SegmentFilter (never raises)."""
    spec_dict = _normalize_segment_filter_keys(_decode_stored_filter_json(raw))
    try:
        return SegmentFilter.model_validate(spec_dict)
    except Exception:
        return SegmentFilter()


def _segment_where_clause_and_params(filter_spec: SegmentFilter):
    """Build WHERE clause and Cypher params for segment filters (no limit)."""
    clauses = []
    params = {}

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
    return where, params


_SEGMENT_MATCH_PIPELINE = """
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
"""


def _build_segment_query(filter_spec: SegmentFilter, limit: int):
    where, params = _segment_where_clause_and_params(filter_spec)
    params = {**params, "limit": max(10, min(2000, int(limit) if str(limit).isdigit() else 500))}
    query = f"""
    {_SEGMENT_MATCH_PIPELINE.strip()}
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


def _build_segment_count_query(filter_spec: SegmentFilter):
    where, params = _segment_where_clause_and_params(filter_spec)
    query = f"""
    {_SEGMENT_MATCH_PIPELINE.strip()}
    {where}
    RETURN count(p) AS cnt
    """
    return query, params


# ---------------------------------------------------------------------------
# Campaign analysis helpers (used by campaigns and deliberation)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# People profile loader
# ---------------------------------------------------------------------------

def _load_profile(email: str) -> Optional[dict]:
    driver = get_driver()
    query = """
    MATCH (p:Person {email: $email})
    OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(st:SupporterType)
    OPTIONAL MATCH (p)-[:HAS_TAG]->(tag:Tag)
    OPTIONAL MATCH (p)-[:CAN_CONTRIBUTE_WITH]->(sk:Skill)
    OPTIONAL MATCH (p)-[:INTERESTED_IN]->(ia:InvolvementArea)
    OPTIONAL MATCH (p)-[:INTERESTED_IN]->(t:Topic)
    WITH p,
      collect(DISTINCT st.name) AS supporterTypes,
      collect(DISTINCT tag.name) AS tags,
      collect(DISTINCT sk.name) AS skills,
      collect(DISTINCT ia.name) AS involvementAreas,
      collect(DISTINCT t.name) AS topicsOfInterest
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
      // New Georgian fields
      p.profession AS profession,
      p.socialMedia AS socialMedia,
      p.wasPartyMember AS wasPartyMember,
      p.partyDetails AS partyDetails,
      p.howToHelp AS howToHelp,
      p.additionalComments AS additionalComments,
      p.personalId AS personalId,
      p.whatsappChat AS whatsappChat,
      p.dateOfBirth AS dateOfBirth,
      supporterTypes,
      tags,
      skills,
      involvementAreas,
      topicsOfInterest
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query, {"email": email})
    if not records:
        return None
    return records[0].data()


# ---------------------------------------------------------------------------
# Import row builders
# ---------------------------------------------------------------------------

def _build_import_rows(df: pd.DataFrame, default_type: str) -> List[dict]:
    if df.empty:
        return []
    df["age"] = pd.to_numeric(df.get("age"), errors="coerce")
    # Georgian column name mappings
    col_email = _get_column(df, ["email", "primary_email", "e_mail", "e-mail", "email_address", "ელ.ფოსტა"])
    col_email_secondary = _get_column(
        df, ["secondary_email", "alternate_email", "alt_email"]
    )
    if not col_email:
        return []
    col_first = _get_column(df, ["first_name", "firstname", "first", "სახელი"])
    col_last = _get_column(df, ["last_name", "lastname", "last", "გვარი"])
    col_gender = _get_column(df, ["gender", "sex", "სქესი"])
    col_age = _get_column(df, ["age"])
    col_phone = _get_column(df, ["phone", "primary_phone", "mobile", "ტელ"])
    col_phone_secondary = _get_column(df, ["secondary_phone", "alt_phone"])
    col_address = _get_column(df, ["address", "fulladdress", "full_address", "მისამართი"])
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
            "რა დროს დაუთმობთ ჩვენს საქმიანობას ?",
        ],
    )
    # New fields from Georgian supporter/member files
    col_date_of_birth = _get_column(df, ["დაბ. თარიღი", "დაბ.თარიღი", "date_of_birth", "dob", "birth_date"])
    col_profession = _get_column(df, ["პროფესია/სამუშაო ადგილი", "profession", "workplace", "occupation"])
    col_social_media = _get_column(df, ["სოც ქსელები", "social_media", "social_networks", "facebook"])
    col_was_party_member = _get_column(df, ["ყოფილხართ თუ არა რომელიმე პარტიის წევრი?", "was_party_member", "former_party_member"])
    col_party_details = _get_column(df, ["გთხოვთ, მიუთითოთ კონკრეტულად", "party_details", "party_history"])
    col_about = _get_column(df, ["მოგვიყევით თქვენს შესახებ და გვითხარით, რატომ გსურთ შემოგვიერთდეთ.", "about", "bio", "description"])
    col_topics = _get_column(df, ["გთხოვთ, მონიშნოთ თქვენთვის საინტერესო თემები", "topics", "interests", "topics_of_interest"])
    col_involvement = _get_column(df, ["რა მიმართულებით გირჩევნიათ ჩაერთოთ \"თავისუფლების მოედნის\"  საქმიანობაში?", "involvement_areas", "involvement", "participation"])
    col_how_help = _get_column(df, ["როგორ დაეხმარებით \"თავისუფლების მოედანს\"?", "how_to_help", "help_type", "contribution"])
    col_additional_comments = _get_column(df, ["სივრცე დამატებითი კომენტარისთვის", "additional_comments", "comments", "notes"])
    col_agrees_manifesto = _get_column(df, ["გავეცანი თავისუფლების მოედნის მანიფესტს და სრულად ვიზიარებ მასში გაცხადებულ იდეებს.", "agrees_with_manifesto", "manifesto_agreed"])
    col_wants_membership = _get_column(df, ["გსურთ თუ არა ჩვენი პარტიის წევრობა მომავალში?", "interested_in_membership", "wants_membership"])
    col_personal_id = _get_column(df, ["პ/ნ", "personal_id", "id_number", "pn"])
    col_whatsapp = _get_column(df, ["WhatsApp ჩატი", "whatsapp", "whatsapp_chat"])

    rows = []
    for _, row in df.iterrows():
        email = _clean_text(row.get(col_email))
        if not email and col_email_secondary:
            email = _clean_text(row.get(col_email_secondary))
        if not email:
            continue
        
        # Handle age - either from direct age column or calculate from date_of_birth
        age_val = pd.to_numeric(row.get(col_age), errors="coerce") if col_age else None
        age = None
        if age_val is not None and not pd.isna(age_val) and age_val > 0:
            age = int(age_val)
        elif col_date_of_birth:
            dob_val = row.get(col_date_of_birth)
            if dob_val and not pd.isna(dob_val):
                try:
                    dob_str = str(dob_val).strip()
                    # Try different date formats
                    dob = None
                    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%m/%d/%Y"]:
                        try:
                            dob = pd.to_datetime(dob_str, format=fmt)
                            break
                        except:
                            continue
                    if dob is None:
                        dob = pd.to_datetime(dob_str, errors="coerce")
                    if dob is not None and not pd.isna(dob):
                        from datetime import datetime
                        age = int((datetime.now() - dob).days / 365.25)
                except:
                    pass
        
        lat_val = pd.to_numeric(row.get(col_lat), errors="coerce") if col_lat else None
        lon_val = pd.to_numeric(row.get(col_lon), errors="coerce") if col_lon else None
        lat = float(lat_val) if lat_val is not None and not pd.isna(lat_val) else None
        lon = float(lon_val) if lon_val is not None and not pd.isna(lon_val) else None
        if (lat is None or lon is None) and col_address:
            address_text = _clean_text(row.get(col_address))
            if address_text:
                coords = geocode_address(address_text)
                if coords:
                    lat, lon = coords
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
        
        # Process Georgian boolean/text fields
        def _parse_georgian_bool(val):
            if pd.isna(val) or val is None:
                return None
            val_str = str(val).strip().lower()
            return val_str in ["დიახ", "კი", "yes", "true", "1", "ha", "ჰაჰ", "ჰაუ", "y"]
        
        was_party_member = _parse_georgian_bool(row.get(col_was_party_member)) if col_was_party_member else None
        agrees_manifesto = _parse_georgian_bool(row.get(col_agrees_manifesto)) if col_agrees_manifesto else None
        wants_membership = _parse_georgian_bool(row.get(col_wants_membership)) if col_wants_membership else None
        
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
                # New Georgian fields
                "profession": _clean_text(row.get(col_profession)) if col_profession else None,
                "socialMedia": _clean_text(row.get(col_social_media)) if col_social_media else None,
                "wasPartyMember": was_party_member,
                "partyDetails": _clean_text(row.get(col_party_details)) if col_party_details else None,
                "about": _clean_text(row.get(col_about)) if col_about else None,
                "topicsOfInterest": _split_list(row.get(col_topics)) if col_topics else [],
                "involvementAreas": _split_list(row.get(col_involvement)) if col_involvement else [],
                "howToHelp": _clean_text(row.get(col_how_help)) if col_how_help else None,
                "additionalComments": _clean_text(row.get(col_additional_comments)) if col_additional_comments else None,
                "agreesWithManifesto": agrees_manifesto,
                "interestedInMembership": wants_membership,
                "personalId": _clean_text(row.get(col_personal_id)) if col_personal_id else None,
                "whatsappChat": _clean_text(row.get(col_whatsapp)) if col_whatsapp else None,
                "dateOfBirth": str(row.get(col_date_of_birth)) if col_date_of_birth and not pd.isna(row.get(col_date_of_birth)) else None,
            }
        )
    return rows


def _build_furry_import_rows(df: pd.DataFrame) -> List[dict]:
    from uuid import uuid4
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
