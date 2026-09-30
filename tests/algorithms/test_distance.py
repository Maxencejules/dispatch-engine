import math

import pytest

from app.algorithms.distance import haversine_km


def test_haversine_zero_distance():
    d = haversine_km(0.0, 0.0, 0.0, 0.0)
    assert d == 0.0


def test_haversine_known_distance():
    # Toronto to Montreal ≈ 504 km (rough)
    toronto = (43.6532, -79.3832)
    montreal = (45.5019, -73.5674)

    d = haversine_km(toronto[0], toronto[1], montreal[0], montreal[1])

    assert 480 < d < 530


def test_antipodal_rounding_does_not_raise_for_valid_coordinates():
    distance = haversine_km(
        85.48732191913109, 6.157255195407856, -85.48732191913109, -173.84274480459214
    )
    assert distance == pytest.approx(math.pi * 6371, abs=1e-7)
