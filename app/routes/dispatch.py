import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.algorithms.scoring import courier_score
from app.db import DbSession
from app.errors import DispatchError
from app.metrics import dispatch_attempts, dispatch_failure, dispatch_replay, dispatch_success
from app.models import Assignment, Courier, CourierStatus, Order, OrderStatus
from app.schemas import MatchResponse

router = APIRouter(prefix="/dispatch", tags=["dispatch"])
logger = logging.getLogger("dispatch")


def receipt(assignment: Assignment, *, idempotent: bool) -> MatchResponse:
    return MatchResponse(
        order_id=assignment.order_id,
        courier_id=assignment.courier_id,
        assignment_id=assignment.id,
        score=assignment.score,
        assigned_at=assignment.assigned_at.astimezone(UTC),
        reason=assignment.reason,
        explain=assignment.explain,
        idempotent=idempotent,
    )


@router.post("/match", response_model=MatchResponse)
def match_order(order_id: UUID, db: DbSession):
    dispatch_attempts.inc()
    identifier = str(order_id)
    try:
        # Lock order first, then eligible couriers in ascending immutable ID order.
        # Every assignment and status/location writer follows this same courier lock protocol.
        order = db.scalar(select(Order).where(Order.id == identifier).with_for_update())
        if order is None:
            raise DispatchError(404, "order_not_found", "Order not found")
        existing = db.scalar(select(Assignment).where(Assignment.order_id == identifier))
        if existing is not None:
            result = receipt(existing, idempotent=True)
            db.commit()
            dispatch_replay.inc()
            return result
        if order.status != OrderStatus.unassigned:
            raise DispatchError(409, "order_not_eligible", "Order not eligible for assignment")

        couriers = list(
            db.scalars(
                select(Courier)
                .where(Courier.status == CourierStatus.available)
                .order_by(Courier.id)
                .with_for_update()
            )
        )
        # READ COMMITTED gives this post-lock statement a fresh snapshot after a winner commits.
        loads = dict(
            db.execute(
                select(Assignment.courier_id, func.count(Assignment.id))
                .where(Assignment.courier_id.in_([courier.id for courier in couriers]))
                .group_by(Assignment.courier_id)
            ).all()
        )
        best = None
        best_score = None
        best_explain = None
        now = datetime.now(UTC)
        for courier in couriers:
            reserved = loads.get(courier.id, 0)
            if reserved >= courier.capacity:
                continue
            score, explain = courier_score(
                courier_lat=courier.lat,
                courier_lng=courier.lng,
                pickup_lat=order.pickup_lat,
                pickup_lng=order.pickup_lng,
                active_assignments=reserved,
                capacity=courier.capacity,
                last_seen_at=courier.last_seen_at,
                now=now,
            )
            # Sorted IDs break exact score ties, with one shared clock across candidates.
            if best is None or score < best_score:
                best, best_score, best_explain = courier, score, explain
        if best is None:
            raise DispatchError(409, "no_couriers_available", "No couriers available")

        assignment = Assignment(
            order_id=identifier,
            courier_id=best.id,
            score=best_score,
            reason="transactional_min_score",
            explain=best_explain,
        )
        db.add(assignment)
        order.status = OrderStatus.assigned
        if loads.get(best.id, 0) + 1 >= best.capacity:
            best.status = CourierStatus.assigned
        try:
            db.commit()
        except IntegrityError as error:
            db.rollback()
            original = error.orig
            # Recover only the existing PostgreSQL order uniqueness guard; other failures stay errors.
            if (
                getattr(original, "sqlstate", None) == "23505"
                and getattr(getattr(original, "diag", None), "constraint_name", None)
                == "assignments_order_id_key"
            ):
                winner = db.scalar(select(Assignment).where(Assignment.order_id == identifier))
                if winner is not None:
                    result = receipt(winner, idempotent=True)
                    db.commit()
                    dispatch_replay.inc()
                    return result
            raise
        db.refresh(assignment)
        dispatch_success.inc()
        logger.info(
            "dispatch_success order_id=%s courier_id=%s assignment_id=%s",
            identifier,
            assignment.courier_id,
            assignment.id,
        )
        return receipt(assignment, idempotent=False)
    except Exception:
        db.rollback()
        dispatch_failure.inc()
        raise
