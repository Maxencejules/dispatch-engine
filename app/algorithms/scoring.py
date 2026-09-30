from dataclasses import dataclass
from datetime import UTC, datetime

from app.algorithms.distance import haversine_km


@dataclass(frozen=True)
class MatchWeights:
    w_distance: float = 1.0
    w_load: float = 2.0
    w_staleness: float = 0.5


DEFAULT_WEIGHTS = MatchWeights()


def staleness_minutes(last_seen_at, *, now: datetime | None = None) -> float:
    if last_seen_at is None:
        return 1e9
    now = now or datetime.now(UTC)
    # last_seen_at from DB may be tz-aware; handle safely
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return max(0.0, (now - last_seen_at).total_seconds() / 60.0)


def courier_score(
    courier_lat: float,
    courier_lng: float,
    pickup_lat: float,
    pickup_lng: float,
    active_assignments: int,
    capacity: int,
    last_seen_at,
    weights: MatchWeights = DEFAULT_WEIGHTS,
    now: datetime | None = None,
) -> tuple[float, dict]:
    distance = haversine_km(courier_lat, courier_lng, pickup_lat, pickup_lng)
    load_ratio = active_assignments / max(capacity, 1)
    stale = staleness_minutes(last_seen_at, now=now)

    score = (
        weights.w_distance * distance + weights.w_load * load_ratio + weights.w_staleness * stale
    )

    explain = {
        "distance_km": distance,
        "load_ratio": load_ratio,
        "staleness_min": stale,
    }
    return score, explain
