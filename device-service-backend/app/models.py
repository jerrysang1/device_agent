from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Customer(Base):
    """设备归属客户（对应 Agent 的 sender_id / customer_id）。"""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    nickname: Mapped[str] = mapped_column(String(100))
    level: Mapped[str] = mapped_column(String(32))
    mobile_masked: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime)

    devices: Mapped[list["Device"]] = relationship(back_populates="customer")
    tickets: Mapped[list["ServiceTicket"]] = relationship(back_populates="customer")


class Device(Base):
    """设备档案。"""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    model: Mapped[str] = mapped_column(String(128))
    serial_number: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(64))
    purchase_date: Mapped[datetime] = mapped_column(DateTime)
    warranty_months: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    attributes_json: Mapped[dict] = mapped_column(JSON)
    cover_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    customer: Mapped[Customer] = relationship(back_populates="devices")
    tickets: Mapped[list["ServiceTicket"]] = relationship(back_populates="device")
    histories: Mapped[list["DeviceHistory"]] = relationship(back_populates="device")


class DeviceHistory(Base):
    """设备历史事件（巡检、维修、更换等）。"""

    __tablename__ = "device_histories"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    event_time: Mapped[datetime] = mapped_column(DateTime)
    event_type: Mapped[str] = mapped_column(String(64))
    event_desc: Mapped[str] = mapped_column(String(255))

    device: Mapped[Device] = relationship(back_populates="histories")


class ServiceTicket(Base):
    """售后工单。"""

    __tablename__ = "service_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    problem_type: Mapped[str] = mapped_column(String(64))
    problem_desc: Mapped[str] = mapped_column(Text)
    tried_steps: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    status_desc: Mapped[str] = mapped_column(String(255))
    contact_name: Mapped[str] = mapped_column(String(64))
    contact_phone_masked: Mapped[str] = mapped_column(String(32))
    contact_address: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    device: Mapped[Device] = relationship(back_populates="tickets")
    customer: Mapped[Customer] = relationship(back_populates="tickets")
    repair_records: Mapped[list["RepairRecord"]] = relationship(back_populates="ticket")
    transfers: Mapped[list["HumanTransfer"]] = relationship(back_populates="ticket")


class RepairRecord(Base):
    """维修/寄送轨迹，对应电商物流轨迹。"""

    __tablename__ = "repair_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("service_tickets.id"))
    logistics_company: Mapped[str] = mapped_column(String(64))
    tracking_number: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    status_desc: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    ticket: Mapped[ServiceTicket] = relationship(back_populates="repair_records")
    traces: Mapped[list["RepairTrace"]] = relationship(back_populates="record")


class RepairTrace(Base):
    __tablename__ = "repair_traces"

    id: Mapped[int] = mapped_column(primary_key=True)
    repair_record_id: Mapped[int] = mapped_column(ForeignKey("repair_records.id"))
    trace_time: Mapped[datetime] = mapped_column(DateTime)
    trace_desc: Mapped[str] = mapped_column(String(255))

    record: Mapped[RepairRecord] = relationship(back_populates="traces")


class HumanTransfer(Base):
    """转人工记录。"""

    __tablename__ = "human_transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("service_tickets.id"), nullable=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    reason: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32))
    status_desc: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)

    ticket: Mapped[ServiceTicket | None] = relationship(back_populates="transfers")
