import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.algorithms.scoring import courier_score
from app.db import get_db
from app.metrics import dispatch_attempts, dispatch_failure, dispatch_success
from app.models import Assignment, Courier, CourierStatus, Order, OrderStatus

router = APIRouter(prefix="/dispatch", tags=["dispatch"])
logger = logging.getLogger("dispatch")


@router.post("/match")
def match_order(order_id: str, db: Session = Depends(get_db)):
    dispatch_attempts.inc()
    logger.info("dispatch_attempt", extra={"order_id": order_id})

    # Lock the order row to prevent races
    order = db.execute(
        select(Order).where(Order.id == order_id).with_for_update()
    ).scalar_one_or_none()

    if not order:
        dispatch_failure.inc()
        logger.info(
            "dispatch_failure",
            extra={"order_id": order_id, "reason": "order_not_found"},
        )
        raise HTTPException(status_code=404, detail="Order not found")

    # Idempotency: return existing assignment if already assigned
    existing = db.execute(
        select(Assignment).where(Assignment.order_id == order.id)
    ).scalar_one_or_none()

    if existing:
        logger.info(
            "dispatch_idempotent_hit",
            extra={
                "order_id": existing.order_id,
                "courier_id": existing.courier_id,
                "assignment_id": existing.id,
            },
        )
        return {
            "order_id": existing.order_id,
            "courier_id": existing.courier_id,
            "assignment_id": existing.id,
            "score": existing.score,
            "idempotent": True,
        }

    if order.status != OrderStatus.unassigned:
        dispatch_failure.inc()
        logger.info(
            "dispatch_failure",
            extra={"order_id": order_id, "reason": "order_not_eligible"},
        )
        raise HTTPException(status_code=409, detail="Order not eligible for assignment")

    couriers = db.execute(
        select(Courier).where(Courier.status == CourierStatus.available)
    ).scalars().all()

    best = None
    best_meta = None

    for c in couriers:
        active_count = db.execute(
            select(func.count(Assignment.id)).where(Assignment.courier_id == c.id)
        ).scalar_one()

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

    if not best:
        dispatch_failure.inc()
        logger.info(
            "dispatch_failure",
            extra={"order_id": order_id, "reason": "no_available_couriers"},
        )
        raise HTTPException(status_code=409, detail="No couriers available")

    assignment = Assignment(
        order_id=order.id,
        courier_id=best.id,
        score=best_meta["score"],
        reason="transactional_min_score",
    )

    order.status = OrderStatus.assigned
    best.status = CourierStatus.assigned

    try:
        db.add(assignment)
        db.commit()
    except IntegrityError:
        # Another request won the race → idempotent response
        db.rollback()
        dispatch_failure.inc()
        logger.info("dispatch_race_lost", extra={"order_id": order.id})

        winner = db.execute(
            select(Assignment).where(Assignment.order_id == order.id)
        ).scalar_one()

        return {
            "order_id": winner.order_id,
            "courier_id": winner.courier_id,
            "assignment_id": winner.id,
            "score": winner.score,
            "idempotent": True,
        }

    db.refresh(assignment)

    dispatch_success.inc()
    logger.info(
        "dispatch_success",
        extra={
            "order_id": assignment.order_id,
            "courier_id": assignment.courier_id,
            "assignment_id": assignment.id,
            "score": assignment.score,
        },
    )

    return {
        "order_id": assignment.order_id,
        "courier_id": assignment.courier_id,
        "assignment_id": assignment.id,
        "score": assignment.score,
        "explain": best_meta["explain"],
        "idempotent": False,
    }
