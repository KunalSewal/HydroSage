import os

import pytest

from app.infrastructure.geocoding_client import GeocodingClient


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="hits the live Nominatim API; set RUN_INTEGRATION_TESTS=1 to run",
)
def test_search_finds_hiware_bazar():
    client = GeocodingClient()
    results = client.search("Hiware Bazar, Maharashtra, India", limit=1)
    assert len(results) == 1
    assert "Hiware" in results[0]["display_name"]
    assert float(results[0]["lat"]) == pytest.approx(19.0679874, abs=0.01)
    client.close()


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="hits the live Nominatim API; set RUN_INTEGRATION_TESTS=1 to run",
)
def test_reverse_resolves_a_known_point():
    client = GeocodingClient()
    result = client.reverse(21.1938, 81.3509)  # Bhilai/Durg default map center
    assert result is not None
    assert "Chhattisgarh" in result["display_name"]
    client.close()


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="hits the live Nominatim API; set RUN_INTEGRATION_TESTS=1 to run",
)
def test_reverse_returns_none_for_unresolvable_point():
    client = GeocodingClient()
    result = client.reverse(0, 0)  # open ocean
    assert result is None
    client.close()
