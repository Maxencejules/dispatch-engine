import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models import Assignment, Courier, CourierStatus, Order, OrderStatus


def courier(client, capacity=1):
    result = client.post("/couriers", json={"lat": 43.65, "lng": -79.38, "capacity": capacity})
    assert result.status_code == 200, result.text
    return result.json()["id"]


def order(client):
    result = client.post(
        "/orders",
        json={
            "pickup_lat": 43.65,
            "pickup_lng": -79.38,
            "dropoff_lat": 43.70,
            "dropoff_lng": -79.40,
        },
    )
    assert result.status_code == 200, result.text
    return result.json()["id"]


def match(client, identifier):
    return client.post("/dispatch/match", params={"order_id": identifier})


def overlap(engine, held_sql, parameters, requests):
    """Force all independent HTTP transactions to reach a real PostgreSQL row lock."""
    start = threading.Event()
    with ThreadPoolExecutor(max_workers=len(requests)) as pool, engine.connect() as holder:
        transaction = holder.begin()
        try:
            holder.execute(text(held_sql), parameters)

            def invoke(request):
                assert start.wait(5)
                return request()

            futures = [pool.submit(invoke, request) for request in requests]
            start.set()
            deadline = time.monotonic() + 10
            blocked = 0
            while time.monotonic() < deadline:
                with engine.connect() as observer:
                    blocked = observer.scalar(
                        text("""
                        SELECT count(*) FROM pg_stat_activity
                        WHERE datname = current_database() AND wait_event_type = 'Lock'
                        AND pid <> pg_backend_pid()
                    """)
                    )
                if blocked == len(requests):
                    break
                time.sleep(0.02)
            assert blocked == len(requests), "Every request must overlap behind a PostgreSQL lock"
            transaction.commit()
            return [future.result(timeout=10) for future in futures]
        finally:
            if transaction.is_active:
                transaction.rollback()


def test_same_order_requests_have_one_assignment_under_independent_transactions(
    client, engine, db_session
):
    courier_id = courier(client)
    order_id = order(client)
    responses = overlap(
        engine,
        "SELECT id FROM orders WHERE id = :id FOR UPDATE",
        {"id": order_id},
        [lambda: match(client, order_id)] * 4,
    )
    assert [response.status_code for response in responses] == [200] * 4
    receipts = [response.json() for response in responses]
    assert len({receipt["assignment_id"] for receipt in receipts}) == 1
    assert all(receipt["courier_id"] == courier_id for receipt in receipts)
    assert sorted(receipt["idempotent"] for receipt in receipts) == [False, True, True, True]
    assert db_session.scalar(select(func.count()).select_from(Assignment)) == 1


def test_different_orders_cannot_overbook_one_courier(client, engine, db_session):
    courier_id = courier(client, capacity=1)
    order_ids = [order(client), order(client)]
    responses = overlap(
        engine,
        "SELECT id FROM couriers WHERE id = :id FOR UPDATE",
        {"id": courier_id},
        [lambda identifier=identifier: match(client, identifier) for identifier in order_ids],
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert db_session.scalar(select(func.count()).select_from(Assignment)) == 1
    statuses = list(db_session.scalars(select(Order.status)))
    assert sorted(status.value for status in statuses) == ["assigned", "unassigned"]
    assert db_session.get(Courier, courier_id).status == CourierStatus.assigned


def test_capacity_two_can_be_used_then_full_courier_is_ineligible(client, db_session):
    courier_id = courier(client, capacity=2)
    first, second, third = [order(client) for _ in range(3)]
    assert match(client, first).status_code == 200
    assert client.get(f"/couriers/{courier_id}").json()["status"] == "available"
    assert match(client, second).status_code == 200
    assert client.get(f"/couriers/{courier_id}").json()["status"] == "assigned"
    assert match(client, third).status_code == 409
    assert db_session.scalar(select(func.count()).select_from(Assignment)) == 2


def test_offline_change_committed_before_reservation_is_respected(client, engine, db_session):
    courier_id = courier(client)
    order_id = order(client)
    responses = overlap(
        engine,
        "UPDATE couriers SET status = 'offline' WHERE id = :id",
        {"id": courier_id},
        [lambda: match(client, order_id)],
    )
    assert responses[0].status_code == 409
    assert db_session.scalar(select(func.count()).select_from(Assignment)) == 0
    assert db_session.get(Courier, courier_id).status == CourierStatus.offline
    assert db_session.get(Order, order_id).status == OrderStatus.unassigned


def test_location_report_refreshes_last_seen_at(client, db_session):
    courier_id = courier(client)
    old = datetime.now(UTC) - timedelta(hours=2)
    db_session.execute(
        text("UPDATE couriers SET last_seen_at = :old WHERE id = :id"),
        {"old": old, "id": courier_id},
    )
    db_session.commit()
    result = client.patch(f"/couriers/{courier_id}/location", json={"lat": 44.0, "lng": -80.0})
    assert result.status_code == 200
    assert datetime.fromisoformat(result.json()["last_seen_at"]) > old


def test_replay_keeps_the_original_scoring_explanation(client):
    courier(client)
    order_id = order(client)
    first = match(client, order_id).json()
    replay = match(client, order_id).json()
    assert first["explain"] == replay["explain"]
    assert first["score"] == replay["score"]
    assert first["assignment_id"] == replay["assignment_id"]


@pytest.mark.parametrize(
    "payload",
    [
        {"lat": 91, "lng": 0, "capacity": 1},
        {"lat": 0, "lng": -181, "capacity": 1},
        {"lat": 0, "lng": 0, "capacity": 0},
        {"lat": 0, "lng": 0, "capacity": -1},
        {"lat": 0, "lng": 0, "capacity": True},
    ],
)
def test_invalid_courier_input_does_not_create_rows(client, db_session, payload):
    response = client.post("/couriers", json=payload)
    assert response.status_code == 422
    assert db_session.scalar(select(func.count()).select_from(Courier)) == 0


def test_nonfinite_coordinates_have_a_parseable_validation_error(client, db_session):
    response = client.post(
        "/couriers",
        content='{"lat":NaN,"lng":0,"capacity":1}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert db_session.scalar(select(func.count()).select_from(Courier)) == 0


def test_unrelated_integrity_error_is_not_reported_as_a_duplicate_assignment(client, db_session):
    courier_id = courier(client)
    order_id = order(client)

    def unrelated_foreign_key_failure(mapper, connection, target):
        connection.execute(
            text("""
            INSERT INTO assignments (id, order_id, courier_id, score, reason)
            VALUES (:id, :missing_order, :courier, 1, 'failure fixture')
        """),
            {"id": str(uuid.uuid4()), "missing_order": str(uuid.uuid4()), "courier": courier_id},
        )

    event.listen(Assignment, "before_insert", unrelated_foreign_key_failure)
    try:
        response = match(client, order_id)
    finally:
        event.remove(Assignment, "before_insert", unrelated_foreign_key_failure)
    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "foreign key" not in response.text.lower()
    assert db_session.scalar(select(func.count()).select_from(Assignment)) == 0
    assert db_session.get(Order, order_id).status == OrderStatus.unassigned
    assert db_session.get(Courier, courier_id).status == CourierStatus.available


def test_three_parallel_orders_use_exactly_two_slots(client, engine, db_session):
    courier_id = courier(client, capacity=2)
    identifiers = [order(client) for _ in range(3)]
    responses = overlap(
        engine,
        "SELECT id FROM couriers WHERE id = :id FOR UPDATE",
        {"id": courier_id},
        [lambda identifier=identifier: match(client, identifier) for identifier in identifiers],
    )
    assert sorted(response.status_code for response in responses) == [200, 200, 409]
    assert db_session.scalar(select(func.count()).select_from(Assignment)) == 2
    assert db_session.get(Courier, courier_id).status == CourierStatus.assigned


def test_status_writer_waits_for_matching_courier_lock(client, engine, db_session):
    courier_id = courier(client)
    responses = overlap(
        engine,
        "SELECT id FROM couriers WHERE id = :id FOR UPDATE",
        {"id": courier_id},
        [lambda: client.patch(f"/couriers/{courier_id}/status", params={"status": "offline"})],
    )
    assert responses[0].status_code == 200
    assert db_session.get(Courier, courier_id).status == CourierStatus.offline


def test_exact_score_ties_use_courier_id_order(client, db_session):
    identifiers = [courier(client) for _ in range(3)]
    db_session.execute(text("UPDATE couriers SET last_seen_at = :now"), {"now": datetime.now(UTC)})
    db_session.commit()
    assert match(client, order(client)).json()["courier_id"] == min(identifiers)


def test_order_uniqueness_guard_rejects_duplicate_and_keeps_original_receipt(client, db_session):
    courier_id = courier(client)
    identifier = order(client)
    original = match(client, identifier).json()
    with pytest.raises(IntegrityError) as failure, db_session.begin_nested():
        db_session.add(
            Assignment(
                order_id=identifier, courier_id=courier_id, score=99, reason="duplicate fixture"
            )
        )
        db_session.flush()
    assert failure.value.orig.sqlstate == "23505"
    assert failure.value.orig.diag.constraint_name == "assignments_order_id_key"
    db_session.rollback()
    replay = match(client, identifier).json()
    assert {key: value for key, value in replay.items() if key != "idempotent"} == {
        key: value for key, value in original.items() if key != "idempotent"
    }
    assert replay["idempotent"] is True


@pytest.mark.parametrize("route", ["/couriers", "/orders", "/dispatch/match"])
def test_invalid_and_missing_identifiers_have_json_contracts(client, route):
    def request(identifier):
        return (
            match(client, identifier)
            if route == "/dispatch/match"
            else client.get(f"{route}/{identifier}")
        )

    assert request("not-a-uuid").json()["code"] == "invalid_request"
    missing = request(str(uuid.uuid4()))
    assert missing.status_code == 404
    assert missing.json()["code"].endswith("_not_found")


@pytest.mark.parametrize(
    "field,bad",
    [("pickup_lat", 91), ("pickup_lng", -181), ("dropoff_lat", -91), ("dropoff_lng", 181)],
)
def test_invalid_order_coordinates_are_rejected(client, db_session, field, bad):
    payload = dict(pickup_lat=0, pickup_lng=0, dropoff_lat=0, dropoff_lng=0)
    payload[field] = bad
    assert client.post("/orders", json=payload).status_code == 422
    assert db_session.scalar(select(func.count()).select_from(Order)) == 0


@pytest.mark.parametrize("status", [OrderStatus.cancelled, OrderStatus.delivered])
def test_ineligible_order_does_not_reserve_capacity(client, db_session, status):
    courier_id = courier(client)
    identifier = order(client)
    db_session.get(Order, identifier).status = status
    db_session.commit()
    response = match(client, identifier)
    assert response.status_code == 409
    assert response.json()["code"] == "order_not_eligible"
    assert db_session.scalar(select(func.count()).select_from(Assignment)) == 0
    assert db_session.get(Courier, courier_id).status == CourierStatus.available


def test_unavailable_database_has_sanitized_json_contract(client, engine):
    def fail_read(connection, cursor, statement, parameters, context, executemany):
        if statement.strip() == "SELECT 1":
            raise OperationalError(statement, parameters, RuntimeError("private database details"))

    event.listen(engine, "before_cursor_execute", fail_read)
    try:
        response = client.get("/health")
    finally:
        event.remove(engine, "before_cursor_execute", fail_read)
    assert response.status_code == 503
    assert response.json()["code"] == "database_unavailable"
    assert "private" not in response.text
