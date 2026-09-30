"""Preserve decision explanations and enforce dispatch input invariants.

Revision ID: e7a46bc91208
Revises: d9d03487bba6
"""

from alembic import op
import sqlalchemy as sa

revision = "e7a46bc91208"
down_revision = "d9d03487bba6"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    # Refuse inconsistent old data before DDL; never delete/reassign or fabricate explanations.
    invalid_courier = connection.scalar(
        sa.text("""
        SELECT EXISTS(SELECT 1 FROM couriers WHERE capacity < 1
          OR NOT(lat BETWEEN -90 AND 90 AND lng BETWEEN -180 AND 180))
    """)
    )
    invalid_order = connection.scalar(
        sa.text("""
        SELECT EXISTS(SELECT 1 FROM orders WHERE NOT(
          pickup_lat BETWEEN -90 AND 90 AND pickup_lng BETWEEN -180 AND 180
          AND dropoff_lat BETWEEN -90 AND 90 AND dropoff_lng BETWEEN -180 AND 180))
    """)
    )
    overbooked = connection.scalar(
        sa.text("""
        SELECT EXISTS(SELECT 1 FROM couriers c JOIN assignments a ON a.courier_id = c.id
          GROUP BY c.id, c.capacity HAVING count(a.id) > c.capacity)
    """)
    )
    if invalid_courier or invalid_order or overbooked:
        raise RuntimeError(
            "Dispatch upgrade refused: invalid legacy coordinates/capacity or "
            "overbooked courier history. Reconcile the data before retrying; "
            "no history has been changed."
        )
    op.add_column("assignments", sa.Column("explain", sa.JSON(), nullable=True))
    op.create_check_constraint("ck_couriers_capacity_positive", "couriers", "capacity >= 1")
    op.create_check_constraint(
        "ck_couriers_coordinates", "couriers", "lat BETWEEN -90 AND 90 AND lng BETWEEN -180 AND 180"
    )
    op.create_check_constraint(
        "ck_orders_coordinates",
        "orders",
        "pickup_lat BETWEEN -90 AND 90 AND pickup_lng BETWEEN -180 AND 180 "
        "AND dropoff_lat BETWEEN -90 AND 90 AND dropoff_lng BETWEEN -180 AND 180",
    )
    op.create_index("ix_assignments_courier_id", "assignments", ["courier_id"])


def downgrade():
    op.drop_index("ix_assignments_courier_id", table_name="assignments")
    op.drop_constraint("ck_orders_coordinates", "orders", type_="check")
    op.drop_constraint("ck_couriers_coordinates", "couriers", type_="check")
    op.drop_constraint("ck_couriers_capacity_positive", "couriers", type_="check")
    op.drop_column("assignments", "explain")
