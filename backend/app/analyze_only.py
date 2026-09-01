"""A deployment entrypoint carrying only POST /analyzeContour.

`app.main` mounts all seven routers, which transitively imports SQLAlchemy,
GeoAlchemy2, Celery and MinIO -- roughly 19 MB of resident memory for
endpoints that need a database, a broker and object storage, none of which
are deployed alongside the contour analysis. The Phase 1 host caps the
container at 512 MB against a measured peak of 539 MB, so that 19 MB is
worth reclaiming (see docs/DECISIONS.md D-012).

The analysis itself is untouched: same router, same parser, same domain
code, same response. Run this instead of app.main where only the contour
endpoint is needed:

    uvicorn app.analyze_only:app --host 0.0.0.0 --port 3000

`app.main` remains the full application for local development and for any
deployment that runs the whole stack.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analyze_contour
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Contour-map terrain and catchment analysis.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_contour.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
