"""Seed the first demo village. See docs/DECISIONS.md D-004.

Run from backend/ with the venv active and the DB migrated:
    python scripts/seed_villages.py
"""

import uuid

from geoalchemy2.shape import from_shape
from shapely.geometry import Point, box

from app.infrastructure.db import SessionLocal
from app.infrastructure.models import Village

VILLAGES = [
    {
        "name": "Hiware Bazar",
        "state": "Maharashtra",
        "district": "Ahmednagar (Ahilyanagar)",
        "lat": 19.0679874,
        "lon": 74.6012297,
        "half_extent_deg": 0.03,  # ~3km — village + surrounding catchment
    },
]


def main() -> None:
    session = SessionLocal()
    try:
        for v in VILLAGES:
            existing = session.query(Village).filter_by(name=v["name"], state=v["state"]).first()
            if existing:
                print(f"skip {v['name']} — already seeded ({existing.id})")
                continue

            centroid = Point(v["lon"], v["lat"])
            e = v["half_extent_deg"]
            bounds = box(v["lon"] - e, v["lat"] - e, v["lon"] + e, v["lat"] + e)

            village = Village(
                id=uuid.uuid4(),
                name=v["name"],
                state=v["state"],
                district=v["district"],
                centroid=from_shape(centroid, srid=4326),
                bounds=from_shape(bounds, srid=4326),
            )
            session.add(village)
            print(f"seeded {v['name']} ({village.id})")

        session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    main()
