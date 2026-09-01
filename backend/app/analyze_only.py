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
import os
import signal

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
    # find_library("c") shells out to ldconfig/gcc and returns None on a slim
    # container that has neither -- which is exactly where this matters most,
    # so the well-known soname is tried directly as well.
    candidates = [ctypes.util.find_library("c"), "libc.so.6", "libc.so"]
    for name in candidates:
        if name is None:
            continue
        try:
            trim = ctypes.CDLL(name).malloc_trim
        except (OSError, AttributeError):
            continue
        trim.argtypes = [ctypes.c_size_t]
        trim.restype = ctypes.c_int
        logger.info("malloc_trim resolved via %s", name)
        return trim
    logger.warning("malloc_trim unavailable; freed heap will not be returned to the OS")
    return None


_malloc_trim = _load_malloc_trim()


# Restart once the resident floor leaves too little room for the next
# analysis's ~170 MB of transient allocation inside the 512 MB cap. Tunable
# without a redeploy, since the right value depends on the host: raise it if
# the server recycles after every request, lower it if it is still being
# OOM-killed.
_RECYCLE_ABOVE_MB = float(os.environ.get("RECYCLE_ABOVE_MB", "335"))


def _rss_mb() -> float | None:
    """Resident set size in MB, read from /proc. None off Linux."""
    try:
        with open("/proc/self/status", encoding="ascii") as status:
            for line in status:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        return None
    return None

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
        before = _rss_mb()
        gc.collect()
        if _malloc_trim is not None:
            try:
                _malloc_trim(0)
            except Exception:  # noqa: BLE001 -- reclaiming memory must never fail a served response
                logger.warning("malloc_trim failed; continuing", exc_info=True)
        after = _rss_mb()
        if before is not None and after is not None:
            # Logged at WARNING so it survives uvicorn's default level: this is
            # the only visibility into memory on a host where the container is
            # capped at 512 MB and an overrun is a SIGKILL with no traceback.
            logger.warning("memory: %.0f MB -> %.0f MB after reclaim (cap 512 MB)", before, after)

        if after is not None and after > _RECYCLE_ABOVE_MB:
            # An analysis needs roughly 170 MB of transient headroom. Once the
            # resident floor is high enough that the *next* request would not
            # fit, restarting now is strictly better than being SIGKILLed
            # mid-request later: this response has already been produced and
            # sent, so nothing in flight is lost, whereas an OOM kill during a
            # request loses that caller's answer entirely.
            #
            # The supervising loop restarts the server (see the deployment
            # command in docs/PHASE1_REPORT.md). SIGTERM rather than os._exit
            # so uvicorn closes its listening socket and finishes the response.
            logger.warning(
                "resident %.0f MB exceeds the %.0f MB recycle threshold; restarting to reclaim",
                after,
                _RECYCLE_ABOVE_MB,
            )
            os.kill(os.getpid(), signal.SIGTERM)
    return response


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
