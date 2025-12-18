from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Assignment, Courier, CourierStatus, Order, OrderStatus
from app.algorithms.scoring import courier_score

router = APIRouter(prefix="/dispatch", tags=["dispatch"])


@router.post("/match")
def match_order(order_id: str, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != OrderStatus.unassigned:
        raise HTTPException(status_code=409, detail="Order already assigned or not eligible")

    # Gather candidate couriers
    couriers = db.execute(
        select(Courier).where(Courier.status == CourierStatus.available)
    ).scalars().all()

    if not couriers:
        raise HTTPException(status_code=409, detail="No available couriers")

    best = None
    best_meta = None

    for c in couriers:
        active_count = db.execute(
            select(func.count(Assignment.id)).where(Assignment.courier_id == c.id)
        ).scalar_one()

        # capacity guard
        if active_count >= c.capacity:
            continue

        score, explain = courier_score(
            courier_lat=c.lat,
            courier_lng=c.lng,
            pickup_lat=order.pickup_lat,
            pickup_lng=order.pickup_lng,
            active_assignments=active_count,
            capacity=c.capacity,
            last_seen_at=c.last_seen_at,
        )

        if best is None or score < best_meta["score"]:
            best = c
            best_meta = {"score": score, "explain": explain}

    if best is None:
        raise HTTPException(status_code=409, detail="No couriers under capacity")

    assignment = Assignment(
        order_id=order.id,
        courier_id=best.id,
        score=best_meta["score"],
        reason=f"min_score distance_km={best_meta['explain']['distance_km']:.3f} load_ratio={best_meta['explain']['load_ratio']:.2f} staleness_min={best_meta['explain']['staleness_min']:.2f}",
    )

    order.status = OrderStatus.assigned
    best.status = CourierStatus.assigned

    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return {
        "order_id": order.id,
        "courier_id": best.id,
        "assignment_id": assignment.id,
        "score": assignment.score,
        "explain": best_meta["explain"],
    }
