"""Shared TLS context for outgoing HTTP clients (app/infrastructure/http.py).

Found from traces (D-016): every analysis spent ~0.5 s outside any span,
building a new httpx.Client -- each one loads and parses the whole CA bundle.
"""

import time

from app.infrastructure.elevation_client import ElevationClient
from app.infrastructure.http import shared_ssl_context


def test_the_tls_context_is_built_once_per_process():
    assert shared_ssl_context() is shared_ssl_context()


def test_constructing_a_client_no_longer_reloads_the_ca_bundle():
    ElevationClient().close()  # first one may pay for building the shared context

    started = time.perf_counter()
    for _ in range(10):
        ElevationClient().close()
    per_client = (time.perf_counter() - started) / 10

    # ~450 ms each before the fix on the development machine; a generous
    # bound keeps this from being flaky on slow CI runners.
    assert per_client < 0.1
