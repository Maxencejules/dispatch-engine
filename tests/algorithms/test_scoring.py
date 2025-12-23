from datetime import datetime, timedelta, timezone

from app.algorithms.scoring import MatchWeights, courier_score


def test_score_prefers_closer_courier():
    weights = MatchWeights(w_distance=1.0, w_load=0.0, w_staleness=0.0)

    near_score, _ = courier_score(
        courier_lat=0.0,
        courier_lng=0.0,
        pickup_lat=0.1,
        pickup_lng=0.1,
        active_assignments=0,
        capacity=1,
        last_seen_at=datetime.now(timezone.utc),
        weights=weights,
    )

    far_score, _ = courier_score(
        courier_lat=0.0,
        courier_lng=0.0,
        pickup_lat=5.0,
        pickup_lng=5.0,
        active_assignments=0,
        capacity=1,
        last_seen_at=datetime.now(timezone.utc),
        weights=weights,
    )

    assert near_score < far_score


def test_score_penalizes_load():
    weights = MatchWeights(w_distance=0.0, w_load=1.0, w_staleness=0.0)

    low_load, _ = courier_score(
        courier_lat=0.0,
        courier_lng=0.0,
        pickup_lat=0.0,
        pickup_lng=0.0,
        active_assignments=0,
        capacity=2,
        last_seen_at=datetime.now(timezone.utc),
        weights=weights,
    )

    high_load, _ = courier_score(
        courier_lat=0.0,
        courier_lng=0.0,
        pickup_lat=0.0,
        pickup_lng=0.0,
        active_assignments=2,
        capacity=2,
        last_seen_at=datetime.now(timezone.utc),
        weights=weights,
    )

    assert low_load < high_load


def test_score_penalizes_staleness():
    weights = MatchWeights(w_distance=0.0, w_load=0.0, w_staleness=1.0)

    fresh_time = datetime.now(timezone.utc)
    stale_time = fresh_time - timedelta(minutes=30)

    fresh_score, _ = courier_score(
        courier_lat=0.0,
        courier_lng=0.0,
        pickup_lat=0.0,
        pickup_lng=0.0,
        active_assignments=0,
        capacity=1,
        last_seen_at=fresh_time,
        weights=weights,
    )

    stale_score, _ = courier_score(
        courier_lat=0.0,
        courier_lng=0.0,
        pickup_lat=0.0,
        pickup_lng=0.0,
        active_assignments=0,
        capacity=1,
        last_seen_at=stale_time,
        weights=weights,
    )

    assert fresh_score < stale_score
