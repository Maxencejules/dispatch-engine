from datetime import datetime
from pydantic import BaseModel, ConfigDict


# -------- Couriers --------

class CourierCreate(BaseModel):
    lat: float
    lng: float
    capacity: int = 1


class CourierUpdateLocation(BaseModel):
    lat: float
    lng: float


class CourierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    lat: float
    lng: float
    capacity: int
    last_seen_at: datetime


# -------- Orders --------

class OrderCreate(BaseModel):
    pickup_lat: float
    pickup_lng: float
    dropoff_lat: float
    dropoff_lng: float


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    pickup_lat: float
    pickup_lng: float
    dropoff_lat: float
    dropoff_lng: float
    created_at: datetime
