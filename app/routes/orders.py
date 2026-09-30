from uuid import UUID

from fastapi import APIRouter

from app.db import DbSession
from app.errors import DispatchError
from app.models import Order
from app.schemas import OrderCreate, OrderResponse

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderResponse)
def create_order(payload: OrderCreate, db: DbSession):
    order = Order(
        pickup_lat=payload.pickup_lat,
        pickup_lng=payload.pickup_lng,
        dropoff_lat=payload.dropoff_lat,
        dropoff_lng=payload.dropoff_lng,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: UUID, db: DbSession):
    order = db.get(Order, str(order_id))
    if not order:
        raise DispatchError(404, "order_not_found", "Order not found")
    return order
