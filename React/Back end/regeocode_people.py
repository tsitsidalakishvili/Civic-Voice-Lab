"""
Re-geocode all people in Neo4j using Nominatim (OpenStreetMap).

Usage:
    python regeocode_people.py

This script:
  - Reads every Person node that has an address.
  - Queries Nominatim for each address with a 1-second delay between requests.
  - Updates p.lat / p.lon in Neo4j.
  - Also stores the parsed neighbourhood/district when available.
  - Writes a CSV file with old vs new coordinates for review.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Optional

import requests

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from deliberation.api.app.core.env import load_backend_env
from deliberation.api.app.db import get_driver

load_backend_env(ROOT_DIR)

USER_AGENT = "FreedomSquare/1.0 (admin@freedomsquare.ge)"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
SLEEP_SECONDS = 1.0  # Nominatim usage policy

# Tbilisi city center coordinates used for empty / nan addresses.
TBILISI_CENTER = {"lat": 41.7151, "lon": 44.8271, "display_name": "Tbilisi, Georgia", "neighbourhood": None}

# In-memory cache for duplicate addresses.
_geocode_cache: dict[str, Optional[dict]] = {}


def _clean_text(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _extract_neighbourhood(result: dict) -> Optional[str]:
    """Try to pull a district / neighbourhood out of the Nominatim display_name."""
    display = result.get("display_name", "")
    if not display:
        return None
    parts = [part.strip() for part in display.split(",")]
    if len(parts) >= 3:
        # Typical OSM display_name: "10, აკაკი წერეთლის გამზირი, დიდუბის რაიონი, დიდუბე, თბილისი, ..."
        # Try the part just before the city name.
        return parts[-3]
    return None


def _looks_like_nan(address: str) -> bool:
    """Return True for empty strings, literal 'nan', or 'none'."""
    return address is None or address.strip().lower() in ("", "nan", "none")


def geocode_with_nominatim(address: str) -> Optional[dict]:
    """Return dict with lat, lon, display_name, neighbourhood or None."""
    if not address or _looks_like_nan(address):
        return None
    key = address.strip().lower()
    if key in _geocode_cache:
        return _geocode_cache[key]
    try:
        resp = requests.get(
            NOMINATIM_SEARCH_URL,
            params={"q": address, "format": "json", "limit": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            _geocode_cache[key] = None
            return None
        first = results[0]
        lat = first.get("lat")
        lon = first.get("lon")
        if lat is None or lon is None:
            _geocode_cache[key] = None
            return None
        result = {
            "lat": float(lat),
            "lon": float(lon),
            "display_name": first.get("display_name", ""),
            "neighbourhood": _extract_neighbourhood(first),
        }
        _geocode_cache[key] = result
        return result
    except Exception:
        _geocode_cache[key] = None
        return None


def load_people(skip_geocoded: bool = False) -> list[dict]:
    driver = get_driver()
    with driver.session() as session:
        rows = session.run(
            """
            MATCH (p:Person)
            OPTIONAL MATCH (p)-[:LIVES_AT]->(addr:Address)
            WITH p, addr,
                 coalesce(p.address, addr.fullAddress) AS address,
                 coalesce(p.lat, addr.lat, addr.latitude) AS lat,
                 coalesce(p.lon, addr.lon, addr.longitude) AS lon
            WHERE $skip_geocoded = false OR p.geocodedAt IS NULL
            RETURN p.email AS email,
                   p.firstName AS firstName,
                   p.lastName AS lastName,
                   address AS address,
                   lat AS lat,
                   lon AS lon,
                   p.neighbourhood AS neighbourhood,
                   p.geocodedAt AS geocodedAt
            """,
            {"skip_geocoded": skip_geocoded},
        ).data()
    return rows


def update_person(email: str, lat: float, lon: float, neighbourhood: Optional[str]) -> None:
    driver = get_driver()
    with driver.session() as session:
        session.run(
            """
            MATCH (p:Person {email: $email})
            OPTIONAL MATCH (p)-[:LIVES_AT]->(addr:Address)
            SET p.lat = $lat,
                p.lon = $lon,
                p.geocodedAt = datetime(),
                p.neighbourhood = CASE
                    WHEN $neighbourhood IS NULL OR trim($neighbourhood) = '' THEN p.neighbourhood
                    ELSE $neighbourhood
                END
            FOREACH (_ IN CASE WHEN addr IS NULL THEN [] ELSE [1] END |
                SET addr.lat = $lat,
                    addr.lon = $lon,
                    addr.latitude = $lat,
                    addr.longitude = $lon
            )
            """,
            {"email": email, "lat": lat, "lon": lon, "neighbourhood": neighbourhood},
        )


def _rows_are_equal(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) < tol


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-geocode people with Nominatim")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N people")
    parser.add_argument("--dry-run", action="store_true", help="Do not update Neo4j, only write CSV")
    parser.add_argument("--skip-geocoded", action="store_true", help="Skip records already marked as geocoded")
    args = parser.parse_args()

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    suffix = "_dryrun" if args.dry_run else ""
    output_path = ROOT_DIR / f"regeocode_people_{timestamp}{suffix}.csv"

    rows = load_people(skip_geocoded=args.skip_geocoded)
    if args.limit:
        rows = rows[: args.limit]
    print(f"Loaded {len(rows)} people with addresses.")

    updated = 0
    failed = 0
    unchanged = 0

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "email",
                "name",
                "address",
                "old_lat",
                "old_lon",
                "new_lat",
                "new_lon",
                "neighbourhood",
                "display_name",
                "status",
            ],
        )
        writer.writeheader()

        for i, row in enumerate(rows, start=1):
            email = _clean_text(row.get("email"))
            address = _clean_text(row.get("address"))
            name = f"{row.get('firstName') or ''} {row.get('lastName') or ''}".strip()
            old_lat = row.get("lat")
            old_lon = row.get("lon")
            old_neighbourhood = row.get("neighbourhood")

            if not email:
                print(f"[{i}/{len(rows)}] skipped: no email for {name or 'unknown'}")
                continue

            # Empty / nan addresses are intentionally placed at Tbilisi center.
            if _looks_like_nan(address):
                result = TBILISI_CENTER
                status = "tbilisi-center"
            else:
                result = geocode_with_nominatim(address)
                status = "ok"
            if result is None:
                failed += 1
                status = "failed"
                new_lat = old_lat
                new_lon = old_lon
                new_neighbourhood = old_neighbourhood
                display_name = ""
            else:
                new_lat = result["lat"]
                new_lon = result["lon"]
                new_neighbourhood = result["neighbourhood"]
                display_name = result.get("display_name", "")
                if not args.dry_run:
                    update_person(email, new_lat, new_lon, new_neighbourhood)
                updated += 1
                if _rows_are_equal(old_lat or 0, new_lat) and _rows_are_equal(old_lon or 0, new_lon):
                    unchanged += 1
                    status = "unchanged"

            writer.writerow(
                {
                    "email": email,
                    "name": name,
                    "address": address,
                    "old_lat": old_lat,
                    "old_lon": old_lon,
                    "new_lat": new_lat,
                    "new_lon": new_lon,
                    "neighbourhood": new_neighbourhood,
                    "display_name": display_name,
                    "status": status,
                }
            )

            print(f"[{i}/{len(rows)}] {status}: {email} -> {new_lat}, {new_lon}")
            if i < len(rows) and not _looks_like_nan(address):
                time.sleep(SLEEP_SECONDS)

    print(f"\nDone. Updated: {updated}, Failed: {failed}, Unchanged: {unchanged}")
    print(f"Results written to: {output_path}")


if __name__ == "__main__":
    main()
