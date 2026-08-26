import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db import Base


class Village(Base):
    __tablename__ = "villages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
    district: Mapped[str] = mapped_column(String, nullable=False)

    # Centroid used to anchor DEM/imagery/rainfall lookups for the village.
    centroid: Mapped[str] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)

    # Bounding box covering the area of interest for terrain/catchment analysis.
    # A curated rectangle for now (see docs/ARCHITECTURE.md open question #3),
    # not an authoritative administrative boundary.
    bounds: Mapped[str] = mapped_column(Geometry(geometry_type="POLYGON", srid=4326), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
