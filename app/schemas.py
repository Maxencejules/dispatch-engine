from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Latitude = Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False, strict=True)]
Longitude = Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False, strict=True)]
Capacity = Annotated[int, Field(ge=1, le=2_147_483_647, strict=True)]


class CourierCreate(BaseModel):
    lat: Latitude
    lng: Longitude
    capacity: Capacity = 1


class CourierUpdateLocation(BaseModel):
    lat: Latitude
    lng: Longitude


class CourierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: str
    lat: float
    lng: float
    capacity: int
    last_seen_at: datetime


class OrderCreate(BaseModel):
    pickup_lat: Latitude
    pickup_lng: Longitude
    dropoff_lat: Latitude
    dropoff_lng: Longitude


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: str
    pickup_lat: float
    pickup_lng: float
    dropoff_lat: float
    dropoff_lng: float
    created_at: datetime


class MatchResponse(BaseModel):
    order_id: str
    courier_id: str
    assignment_id: str
    score: float
    assigned_at: datetime
    reason: str
    explain: dict[str, float] | None
    idempotent: bool
