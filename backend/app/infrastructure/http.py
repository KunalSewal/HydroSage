"""One TLS context per process, shared by every outgoing httpx client.

httpx builds a new SSL context for each Client, which loads and parses the
whole CA bundle: ~450 ms per client on the development machine. The app
creates short-lived clients per request (ElevationClient on every analysis,
even when the DEM comes from cache), so that cost landed on every request.
It was invisible until OpenTelemetry traces showed ~0.5 s inside
`analysis.area` that no child span accounted for (docs/DECISIONS.md D-016).
"""

import ssl
from functools import lru_cache

import certifi


@lru_cache(maxsize=1)
def shared_ssl_context() -> ssl.SSLContext:
    # The same trust store httpx uses by default (certifi), built once.
    return ssl.create_default_context(cafile=certifi.where())
