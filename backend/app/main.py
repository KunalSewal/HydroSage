from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    analyze_contour,
    geocode,
    rainfall,
    recommend,
    report,
    satellite,
    villages,
)
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Terrain, catchment, and rainfall analysis to recommend pond construction sites.",
    version="0.1.0",
)

# The frontend runs on a different origin than this API, so the browser
# blocks every request without explicit CORS headers here — not just
# POSTs, GETs too, and preflight OPTIONS requests 405 without this. This
# exact gap shipped once already (docs/DECISIONS.md D-005) because the
# allowlist was hardcoded to localhost; it's a setting now specifically
# so a deployment can't silently repeat that by forgetting to edit code.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(villages.router)
app.include_router(rainfall.router)
app.include_router(satellite.router)
app.include_router(recommend.router)
app.include_router(report.router)
app.include_router(geocode.router)
app.include_router(analyze_contour.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
