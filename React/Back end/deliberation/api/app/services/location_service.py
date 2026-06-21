import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "tbilisi_neighborhoods.json"
TBILISI_CENTER = {"lat": 41.7151, "lng": 44.8271}

CITY_LOCATIONS = [
    {
        "id": "georgia_tbilisi_city",
        "city": "Tbilisi",
        "district": "Tbilisi",
        "area": "Tbilisi",
        "micro_area": "Tbilisi",
        "lat": 41.7151,
        "lng": 44.8271,
        "aliases": ["თბილისი", "tbilisi", "tiflis"],
    },
    {
        "id": "georgia_ajara_batumi",
        "city": "Batumi",
        "district": "Adjara",
        "area": "Batumi",
        "micro_area": "Batumi",
        "lat": 41.6168,
        "lng": 41.6367,
        "aliases": ["აჭარა", "ბათუმი", "batumi", "adjara"],
    },
    {
        "id": "georgia_imereti_kutaisi",
        "city": "Kutaisi",
        "district": "Imereti",
        "area": "Kutaisi",
        "micro_area": "Kutaisi",
        "lat": 42.2679,
        "lng": 42.6946,
        "aliases": ["იმერეთი", "ქუთაისი", "kutaisi", "imereti"],
    },
    {
        "id": "georgia_kakheti_telavi",
        "city": "Telavi",
        "district": "Kakheti",
        "area": "Telavi",
        "micro_area": "Telavi",
        "lat": 41.9198,
        "lng": 45.4732,
        "aliases": ["კახეთი", "თელავი", "telavi", "kakheti"],
    },
    {
        "id": "georgia_shida_kartli_gori",
        "city": "Gori",
        "district": "Shida Kartli",
        "area": "Gori",
        "micro_area": "Gori",
        "lat": 41.9842,
        "lng": 44.1158,
        "aliases": ["გორი", "gori"],
    },
    {
        "id": "georgia_kakheti_pankisi",
        "city": "Pankisi",
        "district": "Kakheti",
        "area": "Pankisi",
        "micro_area": "Pankisi",
        "lat": 42.16,
        "lng": 45.33,
        "aliases": ["პანკისი", "pankisi"],
    },
    {
        "id": "georgia_kvemo_kartli_rustavi",
        "city": "Rustavi",
        "district": "Kvemo Kartli",
        "area": "Rustavi",
        "micro_area": "Rustavi",
        "lat": 41.5495,
        "lng": 44.9932,
        "aliases": ["რუსთავი", "rustavi"],
    },
]

GEORGIA_GENERAL_LOCATION = {
    "id": "georgia_general",
    "city": "Georgia",
    "district": "Georgia",
    "area": "Georgia",
    "micro_area": "Georgia",
    "lat": 42.3154,
    "lng": 43.3569,
}


def _plain(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "none", "null", "nan", "unspecified"}:
        return ""
    return text


def normalize_location_text(text: Any) -> str:
    """Normalize noisy Georgian/English location text for local dictionary matching."""
    value = unicodedata.normalize("NFKC", _plain(text)).lower()
    value = value.replace("-", " ")
    value = re.sub(r"[^\w\s\u10a0-\u10ff]", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()
    return value


@lru_cache(maxsize=1)
def load_neighborhoods() -> list[dict]:
    with DATA_PATH.open("r", encoding="utf-8") as handle:
        rows = json.load(handle)
    neighborhoods = []
    for row in rows:
        aliases = {row["micro_area"], row.get("area", ""), row.get("district", "")}
        aliases.update(row.get("aliases") or [])
        normalized_aliases = sorted(
            {normalize_location_text(alias) for alias in aliases if normalize_location_text(alias)},
            key=len,
            reverse=True,
        )
        neighborhoods.append({**row, "aliases_normalized": normalized_aliases})
    return neighborhoods


def _as_float(value: Any) -> float | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num):
        return None
    return num


def _distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _best_nearest_neighborhood(lat: float | None, lng: float | None) -> tuple[dict | None, float]:
    if lat is None or lng is None:
        return None, 0
    if abs(lat - TBILISI_CENTER["lat"]) < 0.001 and abs(lng - TBILISI_CENTER["lng"]) < 0.001:
        return None, 0
    best = None
    best_distance = float("inf")
    for neighborhood in load_neighborhoods():
        dist = _distance_km(lat, lng, float(neighborhood["lat"]), float(neighborhood["lng"]))
        if dist < best_distance:
            best = neighborhood
            best_distance = dist
    if best and best_distance <= 2.5:
        return best, max(0.55, 0.82 - best_distance * 0.08)
    return None, 0


def _find_by_name(value: Any) -> dict | None:
    normalized = normalize_location_text(value)
    if not normalized:
        return None
    for neighborhood in load_neighborhoods():
        if normalized in neighborhood["aliases_normalized"]:
            return neighborhood
    return None

def _match_city_location(*values: Any) -> dict | None:
    normalized_values = [normalize_location_text(value) for value in values if normalize_location_text(value)]
    if not normalized_values:
        return None
    candidates = []
    for location in CITY_LOCATIONS:
        for alias in location["aliases"]:
            normalized_alias = normalize_location_text(alias)
            if normalized_alias:
                candidates.append((normalized_alias, location))
    for value in normalized_values:
        for normalized_alias, location in sorted(candidates, key=lambda item: len(item[0]), reverse=True):
            if value == normalized_alias:
                return location
    normalized = normalize_location_text(" ".join(normalized_values))
    for normalized_alias, location in sorted(candidates, key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"(^|\s){re.escape(normalized_alias)}($|\s)", normalized):
            return location
    return None


def _suggest_neighborhood(text: str) -> tuple[dict | None, float]:
    normalized = normalize_location_text(text)
    if not normalized:
        return None, 0
    best = None
    best_score = 0.0
    tokens = set(normalized.split())
    for neighborhood in load_neighborhoods():
        for alias in neighborhood["aliases_normalized"]:
            alias_tokens = set(alias.split())
            if not alias_tokens:
                continue
            overlap = len(tokens & alias_tokens) / len(alias_tokens)
            if overlap > best_score:
                best = neighborhood
                best_score = overlap
    if best_score >= 0.5:
        return best, min(0.72, best_score)
    return None, 0


def match_tbilisi_neighborhood(address_raw: Any, city: Any = None, lat: Any = None, lng: Any = None, **fields):
    address = _plain(address_raw)
    city_text = normalize_location_text(city)
    explicit_values = [
        fields.get("micro_area"),
        fields.get("microArea"),
        fields.get("neighborhood"),
        fields.get("neighbourhood"),
        fields.get("area"),
        fields.get("district"),
    ]
    for value in explicit_values:
        matched = _find_by_name(value)
        if matched:
            return matched, 0.95, "stored_location"

    search_text = " ".join(_plain(v) for v in [address, city, *explicit_values] if _plain(v))
    normalized = normalize_location_text(search_text)
    if normalized in {"tbilisi", "თბილისი"} or (city_text in {"tbilisi", "თბილისი"} and not address):
        return None, 0.0, "city_only"

    for neighborhood in load_neighborhoods():
        for alias in neighborhood["aliases_normalized"]:
            if alias and re.search(rf"(^|\s){re.escape(alias)}($|\s)", normalized):
                return neighborhood, 0.9, "address_alias"

    nearest, nearest_confidence = _best_nearest_neighborhood(_as_float(lat), _as_float(lng))
    if nearest:
        return nearest, nearest_confidence, "nearest_center"

    suggested, suggestion_confidence = _suggest_neighborhood(search_text)
    if suggested:
        return None, suggestion_confidence, "suggested"
    return None, 0.0, "unmatched"


def _age_group(age: Any) -> str:
    num = _as_float(age)
    if num is None:
        return "Unknown"
    age_int = int(num)
    if age_int < 18:
        return "Under 18"
    if age_int <= 24:
        return "18-24"
    if age_int <= 34:
        return "25-34"
    if age_int <= 44:
        return "35-44"
    if age_int <= 54:
        return "45-54"
    if age_int <= 64:
        return "55-64"
    return "65+"


def _clean_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    result = []
    for item in value:
        text = _plain(item)
        if text:
            result.append(text)
    return result


def _audience_group(row: dict) -> str:
    raw = " ".join([_plain(row.get("group")), *_clean_list(row.get("types"))]).lower()
    if "partner" in raw:
        return "Partner"
    if "volunteer" in raw:
        return "Volunteer"
    if "member" in raw:
        return "Member"
    if "supporter" in raw:
        return "Supporter"
    return _plain(row.get("group")) or "Unknown"


def _display_person(row: dict, location: dict | None = None) -> dict:
    group = _audience_group(row)
    full_name = _plain(row.get("fullName")) or " ".join(
        part for part in [_plain(row.get("firstName")), _plain(row.get("lastName"))] if part
    )
    return {
        "personId": _plain(row.get("personId")) or _plain(row.get("email")),
        "fullName": full_name or "Unknown",
        "email": _plain(row.get("email")),
        "phone": _plain(row.get("phone")),
        "type": group,
        "status": _plain(row.get("status")) or "Active",
        "gender": _plain(row.get("gender")) or "Unspecified",
        "age": int(_as_float(row.get("age"))) if _as_float(row.get("age")) is not None else None,
        "ageGroup": _age_group(row.get("age")),
        "timeAvailability": _plain(row.get("timeAvailability")) or "Unspecified",
        "tags": _clean_list(row.get("tags")),
        "skills": _clean_list(row.get("skills")),
        "campaignParticipation": int(_as_float(row.get("campaignParticipation")) or 0),
        "lastEngagement": _plain(row.get("lastEngagement")),
        "neighborhoodId": location.get("id") if location else "",
        "neighborhood": location.get("micro_area") if location else "Unmatched",
        "locationPrecision": location.get("location_precision", "neighborhood") if location else "unknown",
    }


def assign_location_fields(person: dict) -> dict:
    matched, confidence, source = match_tbilisi_neighborhood(
        person.get("address"),
        city=person.get("city"),
        lat=person.get("lat"),
        lng=person.get("lon"),
        district=person.get("district"),
        area=person.get("area"),
        micro_area=person.get("micro_area"),
        microArea=person.get("microArea"),
        neighborhood=person.get("neighborhood"),
        neighbourhood=person.get("neighbourhood"),
    )
    if matched:
        return {
            "city": matched["city"],
            "district": matched["district"],
            "area": matched["area"],
            "micro_area": matched["micro_area"],
            "neighborhood": matched["micro_area"],
            "neighborhood_lat": matched["lat"],
            "neighborhood_lng": matched["lng"],
            "neighborhood_id": matched["id"],
            "location_precision": "neighborhood",
            "location_source": source,
            "location_confidence": round(confidence, 2),
            "location_review_needed": confidence < 0.82,
            "_matched": matched,
        }

    city_match = _match_city_location(
        person.get("address"),
        person.get("city"),
        person.get("district"),
        person.get("area"),
        person.get("neighborhood"),
        person.get("neighbourhood"),
    )
    if city_match:
        return {
            "city": city_match["city"],
            "district": city_match["district"],
            "area": city_match["area"],
            "micro_area": city_match["micro_area"],
            "neighborhood": city_match["micro_area"],
            "neighborhood_lat": city_match["lat"],
            "neighborhood_lng": city_match["lng"],
            "neighborhood_id": city_match["id"],
            "location_precision": "city",
            "location_source": "city_alias",
            "location_confidence": 0.86,
            "location_review_needed": False,
            "_matched": city_match,
        }

    country_match = GEORGIA_GENERAL_LOCATION
    return {
        "city": country_match["city"],
        "district": country_match["district"],
        "area": country_match["area"],
        "micro_area": country_match["micro_area"],
        "neighborhood": country_match["micro_area"],
        "neighborhood_lat": country_match["lat"],
        "neighborhood_lng": country_match["lng"],
        "neighborhood_id": country_match["id"],
        "location_precision": "country",
        "location_source": "country_fallback",
        "location_confidence": 0.3,
        "location_review_needed": False,
        "suggested_match": "",
        "_matched": country_match,
    }


def _matches_filter(row: dict, filters: dict) -> bool:
    group = _audience_group(row).lower()
    supporter_type = normalize_location_text(filters.get("supporterType"))
    if supporter_type and supporter_type not in normalize_location_text(group):
        return False
    for key, row_key in [("gender", "gender"), ("ageGroup", "ageGroup")]:
        expected = normalize_location_text(filters.get(key))
        if expected and expected != normalize_location_text(row.get(row_key)):
            return False
    tag = normalize_location_text(filters.get("tag"))
    if tag and tag not in [normalize_location_text(v) for v in _clean_list(row.get("tags"))]:
        return False
    skill = normalize_location_text(filters.get("skill"))
    if skill and skill not in [normalize_location_text(v) for v in _clean_list(row.get("skills"))]:
        return False
    return True


def aggregate_people_by_neighborhood(people: Iterable[dict], filters: dict | None = None) -> list[dict]:
    filters = filters or {}
    groups: dict[str, dict] = {}
    for row in people:
        enriched = {**row, "ageGroup": _age_group(row.get("age"))}
        if not _matches_filter(enriched, filters):
            continue
        location = assign_location_fields(enriched)
        matched = location.get("_matched")
        if not matched:
            continue
        group_id = matched["id"]
        if group_id not in groups:
            groups[group_id] = {
                "id": group_id,
                "city": matched["city"],
                "district": matched["district"],
                "area": matched["area"],
                "microArea": matched["micro_area"],
                "lat": matched["lat"],
                "lng": matched["lng"],
                "total": 0,
                "supporters": 0,
                "members": 0,
                "volunteers": 0,
                "partners": 0,
                "unknown": 0,
                "_tags": Counter(),
                "lastActivityCount30d": 0,
            }
        bucket = groups[group_id]
        bucket["total"] += 1
        group = _audience_group(row)
        if group == "Supporter":
            bucket["supporters"] += 1
        elif group == "Member":
            bucket["members"] += 1
        elif group == "Volunteer":
            bucket["volunteers"] += 1
        elif group == "Partner":
            bucket["partners"] += 1
        else:
            bucket["unknown"] += 1
        bucket["lastActivityCount30d"] += int(_as_float(row.get("lastActivityCount30d")) or 0)
        bucket["_tags"].update(_clean_list(row.get("tags")) + _clean_list(row.get("skills")))
    results = []
    for bucket in groups.values():
        tags = [tag for tag, _ in bucket.pop("_tags").most_common(3)]
        bucket["topTags"] = tags
        results.append(bucket)
    return sorted(results, key=lambda row: (-row["total"], row["microArea"]))


def people_for_map(people: Iterable[dict], filters: dict | None = None) -> list[dict]:
    filters = filters or {}
    rows = []
    for row in people:
        enriched = {**row, "ageGroup": _age_group(row.get("age"))}
        if not _matches_filter(enriched, filters):
            continue
        location = assign_location_fields(enriched)
        matched = location.get("_matched")
        if matched:
            rows.append(_display_person(row, matched))
    return sorted(rows, key=lambda row: (row.get("neighborhood") or "", row["fullName"]))


def people_for_neighborhood(people: Iterable[dict], neighborhood_id: str, filters: dict | None = None) -> list[dict]:
    filters = filters or {}
    rows = []
    for row in people:
        enriched = {**row, "ageGroup": _age_group(row.get("age"))}
        if not _matches_filter(enriched, filters):
            continue
        location = assign_location_fields(enriched)
        matched = location.get("_matched")
        if matched and matched["id"] == neighborhood_id:
            rows.append(_display_person(row, matched))
    return sorted(rows, key=lambda row: row["fullName"])


def unmatched_people(people: Iterable[dict]) -> list[dict]:
    rows = []
    for row in people:
        location = assign_location_fields(row)
        if location.get("_matched"):
            continue
        rows.append(
            {
                "personId": _plain(row.get("personId")) or _plain(row.get("email")),
                "fullName": _display_person(row)["fullName"],
                "addressRaw": _plain(row.get("address")),
                "city": location.get("city") or _plain(row.get("city")) or "Unknown",
                "suggestedMatch": location.get("suggested_match", ""),
                "confidence": location.get("location_confidence", 0),
                "reviewNeeded": True,
            }
        )
    return sorted(rows, key=lambda row: (row["city"], row["fullName"]))






