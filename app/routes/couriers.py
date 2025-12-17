from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Courier, CourierStatus
from app.schemas import (
    CourierCreate,
    CourierResponse,
    CourierUpdateLocation,
)

router = APIRouter(prefix="/couriers", tags=["couriers"])


@router.post("", response_model=CourierResponse)
def create_courier(payload: CourierCreate, db: Session = Depends(get_db)):
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
def get_courier(courier_id: str, db: Session = Depends(get_db)):
    courier = db.get(Courier, courier_id)
    if not courier:
        raise HTTPException(status_code=404, detail="Courier not found")
    return courier


@router.patch("/{courier_id}/location", response_model=CourierResponse)
def update_location(
    courier_id: str,
    payload: CourierUpdateLocation,
    db: Session = Depends(get_db),
):
    courier = db.get(Courier, courier_id)
    if not courier:
        raise HTTPException(status_code=404, detail="Courier not found")

    courier.lat = payload.lat
    courier.lng = payload.lng
    db.commit()
    db.refresh(courier)
    return courier


@router.patch("/{courier_id}/status", response_model=CourierResponse)
def update_status(
    courier_id: str,
    status: CourierStatus,
    db: Session = Depends(get_db),
):
    courier = db.get(Courier, courier_id)
    if not courier:
        raise HTTPException(status_code=404, detail="Courier not found")

    courier.status = status
    db.commit()
    db.refresh(courier)
    return courier
