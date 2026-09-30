"""Exercise the actual Alembic upgrade with isolated PostgreSQL legacy schemas."""

import uuid

import pytest
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command

LEGACY = "d9d03487bba6"


@pytest.fixture
def legacy(engine):
    schema = "migration_" + uuid.uuid4().hex
    with engine.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.commit()
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.upgrade(config, LEGACY)
        connection.commit()
        try:
            yield connection, config
        finally:
            connection.rollback()
            connection.execute(text("SET search_path TO public"))
            # Only this fixture's generated schema is removed; public data is untouched.
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            connection.commit()


def seed(connection, *, capacity=2, lat=43.65, pickup_lat=43.65, assignments=1):
    courier_id = str(uuid.uuid4())
    connection.execute(
        text("""
        INSERT INTO couriers (id,status,lat,lng,capacity)
        VALUES (:id,'available',:lat,-79.38,:capacity)
    """),
        dict(id=courier_id, lat=lat, capacity=capacity),
    )
    for _ in range(assignments):
        order_id = str(uuid.uuid4())
        connection.execute(
            text("""
            INSERT INTO orders (id,status,pickup_lat,pickup_lng,dropoff_lat,dropoff_lng)
            VALUES (:id,'assigned',:lat,-79.38,43.70,-79.40)
        """),
            dict(id=order_id, lat=pickup_lat),
        )
        connection.execute(
            text("""
            INSERT INTO assignments (id,order_id,courier_id,score,reason)
            VALUES (:id,:order_id,:courier_id,2.5,'legacy decision')
        """),
            dict(id=str(uuid.uuid4()), order_id=order_id, courier_id=courier_id),
        )
    connection.commit()


def snapshot(connection):
    return {
        table: connection.execute(text(f"SELECT * FROM {table} ORDER BY id")).all()
        for table in ("couriers", "orders", "assignments")
    }


def test_upgrade_preserves_legacy_history_without_fabricating_explanation(legacy):
    connection, config = legacy
    seed(connection)
    before = snapshot(connection)
    connection.commit()
    command.upgrade(config, "head")
    connection.commit()
    after = snapshot(connection)
    assert after["couriers"] == before["couriers"]
    assert after["orders"] == before["orders"]
    assert [tuple(row[:-1]) for row in after["assignments"]] == before["assignments"]
    assert all(row[-1] is None for row in after["assignments"])
    assert "ix_assignments_courier_id" in {
        index["name"] for index in inspect(connection).get_indexes("assignments")
    }
    # Rollback removes only the new schema additions; upgrading again retains all old rows.
    connection.commit()
    command.downgrade(config, LEGACY)
    connection.commit()
    assert snapshot(connection) == before
    connection.commit()
    command.upgrade(config, "head")
    connection.commit()
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(text("UPDATE couriers SET capacity = 0"))
    connection.rollback()


@pytest.mark.parametrize(
    "payload",
    [
        {"capacity": 0},
        {"lat": 91},
        {"lat": float("nan")},
        {"lat": float("inf")},
        {"pickup_lat": -91},
        {"capacity": 1, "assignments": 2},
    ],
)
def test_invalid_legacy_data_is_refused_before_schema_or_history_changes(legacy, payload):
    connection, config = legacy
    seed(connection, **payload)
    before = snapshot(connection)
    connection.commit()
    with pytest.raises(RuntimeError, match="Dispatch upgrade refused"):
        command.upgrade(config, "head")
    connection.rollback()
    after = snapshot(connection)
    # NaN does not compare equal; compare immutable row representations for that fixture.
    assert repr(after) == repr(before)
    assert connection.scalar(text("SELECT version_num FROM alembic_version")) == LEGACY
    assert "explain" not in {
        column["name"] for column in inspect(connection).get_columns("assignments")
    }
    assert not inspect(connection).get_check_constraints("couriers")
    assert not inspect(connection).get_check_constraints("orders")
    assert "ix_assignments_courier_id" not in {
        index["name"] for index in inspect(connection).get_indexes("assignments")
    }
