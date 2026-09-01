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

import ctypes
import ctypes.util
import gc
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import analyze_contour
from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


def _load_malloc_trim():
    """glibc's malloc_trim, or None where it doesn't exist.

    An analysis frees hundreds of megabytes, but glibc keeps that memory on
    the process heap rather than returning it to the OS, so RSS stays high
    and the *next* request starts from a raised floor. Measured across three
    consecutive requests the peak crept 497 -> 511 -> 513 MB and crossed the
    512 MB cgroup limit on the third (docs/DECISIONS.md D-012).

    Absent on Windows and macOS, where this is a no-op and the caller simply
    relies on gc.
    """
    try:
        libc_name = ctypes.util.find_library("c")
        if libc_name is None:
            return None
        libc = ctypes.CDLL(libc_name)
        return libc.malloc_trim
    except (OSError, AttributeError):
        return None


_malloc_trim = _load_malloc_trim()

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


@app.middleware("http")
async def release_memory_after_request(request: Request, call_next):
    """Returns the request's freed heap to the OS before the next one starts.

    Without this each analysis raises the floor the next one builds on, and
    the third consecutive request exceeds the container's memory limit even
    though the first two fit. Runs after the response is produced, so it
    costs nothing a client waits on.
    """
    response = await call_next(request)
    if request.url.path == "/analyzeContour":
        gc.collect()
        if _malloc_trim is not None:
            try:
                _malloc_trim(0)
            except Exception:  # noqa: BLE001 -- reclaiming memory must never fail a served response
                logger.warning("malloc_trim failed; continuing", exc_info=True)
    return response


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
