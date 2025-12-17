from datetime import datetime
from typing import Optional
from pydantic import BaseModel


# -------- Couriers --------

class CourierCreate(BaseModel):
    lat: float
    lng: float
    capacity: int = 1


class CourierUpdateLocation(BaseModel):
    lat: float
    lng: float


class CourierResponse(BaseModel):
    id: str
    status: str
    lat: float
    lng: float
    capacity: int
    last_seen_at: datetime

    class Config:
        from_attributes = True


# -------- Orders --------

class OrderCreate(BaseModel):
    pickup_lat: float
    pickup_lng: float
    dropoff_lat: float
    dropoff_lng: float


class OrderResponse(BaseModel):
    id: str
    status: str
    pickup_lat: float
    pickup_lng: float
    dropoff_lat: float
    dropoff_lng: float
    created_at: datetime

    class Config:
        from_attributes = True
