from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from deliberation.api.app.core.env import load_backend_env
from deliberation.api.app.db import get_driver

load_backend_env(ROOT_DIR)

TBILISI_LAT = 41.7151
TBILISI_LON = 44.8271


def main() -> None:
    driver = get_driver()
    with driver.session() as session:
        # Find records at the Kabul coordinates
        kabul_rows = session.run(
            """
            MATCH (p:Person)
            OPTIONAL MATCH (p)-[:LIVES_AT]->(addr:Address)
            WITH p, addr,
                 coalesce(p.lat, addr.lat, addr.latitude) AS lat,
                 coalesce(p.lon, addr.lon, addr.longitude) AS lon,
                 coalesce(p.address, addr.fullAddress) AS address
            WHERE round(lat, 4) = 34.2204 AND round(lon, 4) = 70.3800
            RETURN p.email AS email, address AS address, lat, lon
            """
        ).data()
        print(f"Found {len(kabul_rows)} records at Kabul coordinates.")
        for row in kabul_rows[:5]:
            print(row)

        # Update nan/empty address records to Tbilisi center
        result = session.run(
            """
            MATCH (p:Person)
            OPTIONAL MATCH (p)-[:LIVES_AT]->(addr:Address)
            WITH p, addr,
                 coalesce(p.address, addr.fullAddress) AS address,
                 coalesce(p.lat, addr.lat, addr.latitude) AS lat,
                 coalesce(p.lon, addr.lon, addr.longitude) AS lon
            WHERE address IS NULL OR trim(address) = '' OR toLower(address) IN ['nan', 'none']
            SET p.lat = $lat,
                p.lon = $lon,
                p.geocodedAt = datetime()
            FOREACH (_ IN CASE WHEN addr IS NULL THEN [] ELSE [1] END |
                SET addr.lat = $lat,
                    addr.lon = $lon,
                    addr.latitude = $lat,
                    addr.longitude = $lon
            )
            RETURN count(p) AS updated
            """,
            {"lat": TBILISI_LAT, "lon": TBILISI_LON},
        )
        print("Updated nan/empty records:", result.single()["updated"])


if __name__ == "__main__":
    main()
