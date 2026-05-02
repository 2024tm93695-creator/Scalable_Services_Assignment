"""SQLAlchemy ORM models for Customer Service"""
from datetime import datetime
from sqlalchemy import String, DateTime, func, CheckConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("kyc_status IN ('PENDING','VERIFIED','REJECTED')", name="chk_kyc_status"),
    )

    customer_id: Mapped[int]   = mapped_column(primary_key=True, autoincrement=True)
    name:        Mapped[str]   = mapped_column(String(100), nullable=False)
    email:       Mapped[str]   = mapped_column(String(150), unique=True, nullable=False)
    phone:       Mapped[str]   = mapped_column(String(15), nullable=False)
    kyc_status:  Mapped[str]   = mapped_column(String(20), nullable=False, default="PENDING")
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
