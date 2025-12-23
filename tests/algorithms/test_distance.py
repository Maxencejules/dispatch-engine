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
