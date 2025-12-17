import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CourierStatus(str, enum.Enum):
    available = "available"
    assigned = "assigned"
    offline = "offline"


class OrderStatus(str, enum.Enum):
    unassigned = "unassigned"
    assigned = "assigned"
    picked_up = "picked_up"
    delivered = "delivered"
    cancelled = "cancelled"


class Courier(Base):
    __tablename__ = "couriers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[CourierStatus] = mapped_column(Enum(CourierStatus, name="courier_status"), default=CourierStatus.available, nullable=False)

    lat: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    lng: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    assignments: Mapped[list["Assignment"]] = relationship(back_populates="courier")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, name="order_status"), default=OrderStatus.unassigned, nullable=False)

    pickup_lat: Mapped[float] = mapped_column(Float, nullable=False)
    pickup_lng: Mapped[float] = mapped_column(Float, nullable=False)
    dropoff_lat: Mapped[float] = mapped_column(Float, nullable=False)
    dropoff_lng: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    assignment: Mapped["Assignment | None"] = relationship(back_populates="order", uselist=False)


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True)
    courier_id: Mapped[str] = mapped_column(String(36), ForeignKey("couriers.id", ondelete="CASCADE"), nullable=False)

    score: Mapped[float] = mapped_column(Float, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")

    order: Mapped[Order] = relationship(back_populates="assignment")
    courier: Mapped[Courier] = relationship(back_populates="assignments")
