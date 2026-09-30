from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select

from app.db import DbSession
from app.errors import DispatchError
from app.models import Courier, CourierStatus
from app.schemas import (
    CourierCreate,
    CourierResponse,
    CourierUpdateLocation,
)

router = APIRouter(prefix="/couriers", tags=["couriers"])


@router.post("", response_model=CourierResponse)
def create_courier(payload: CourierCreate, db: DbSession):
    courier = Courier(
        lat=payload.lat,
        lng=payload.lng,
        capacity=payload.capacity,
    )
    db.add(courier)
    db.commit()
    db.refresh(courier)
    return courier


@router.get("/{courier_id}", response_model=CourierResponse)
def get_courier(courier_id: UUID, db: DbSession):
    courier = db.get(Courier, str(courier_id))
    if not courier:
        raise DispatchError(404, "courier_not_found", "Courier not found")
    return courier


@router.patch("/{courier_id}/location", response_model=CourierResponse)
def update_location(
    courier_id: UUID,
    payload: CourierUpdateLocation,
    db: DbSession,
):
    courier = db.scalar(select(Courier).where(Courier.id == str(courier_id)).with_for_update())
    if not courier:
        raise DispatchError(404, "courier_not_found", "Courier not found")

    courier.lat = payload.lat
    courier.lng = payload.lng
    courier.last_seen_at = datetime.now(UTC)
    db.commit()
    db.refresh(courier)
    return courier


@router.patch("/{courier_id}/status", response_model=CourierResponse)
def update_status(
    courier_id: UUID,
    status: CourierStatus,
    db: DbSession,
):
    courier = db.scalar(select(Courier).where(Courier.id == str(courier_id)).with_for_update())
    if not courier:
        raise DispatchError(404, "courier_not_found", "Courier not found")

    courier.status = status
    db.commit()
    db.refresh(courier)
    return courier
