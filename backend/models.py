"""
models.py — Pydantic + SQLAlchemy schemas for the Transaction ledger.

Pydantic models handle API validation/serialisation.
SQLAlchemy models handle persistence.
Both share the same field names so conversions are trivial.

Schema v2: adds `description` and `status` fields per master plan section 9.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from enum import Enum

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, String, Text
)
from sqlalchemy.orm import DeclarativeBase


# ─────────────────────────────────────────────
# Enums (single source of truth for categories)
# ─────────────────────────────────────────────

class TransactionType(str, Enum):
    income = "income"
    expense = "expense"


class TransactionCategory(str, Enum):
    sales = "sales"
    raw_materials = "raw_materials"
    packaging = "packaging"
    transport = "transport"
    other = "other"


class TransactionStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    needs_review = "needs_review"
    rejected = "rejected"


# ─────────────────────────────────────────────
# SQLAlchemy ORM model
# ─────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class TransactionORM(Base):
    __tablename__ = "transactions"

    id: int = Column(Integer, primary_key=True, autoincrement=True, index=True)
    timestamp: datetime = Column(DateTime, default=datetime.utcnow, nullable=False)
    raw_input: str = Column(Text, nullable=False)
    type: str = Column(String(10), nullable=False)           # "income" | "expense"
    category: str = Column(String(20), nullable=False)       # TransactionCategory values
    description: Optional[str] = Column(Text, nullable=True) # e.g. "mango pickle jars"
    amount: float = Column(Float, nullable=False)
    quantity: Optional[int] = Column(Integer, nullable=True)
    unit_price: Optional[float] = Column(Float, nullable=True)
    confidence: float = Column(Float, default=0.0, nullable=False)
    needs_review: bool = Column(Boolean, default=False, nullable=False)
    review_reason: Optional[str] = Column(Text, nullable=True)
    status: str = Column(String(20), default="pending", nullable=False)


# ─────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────

class TransactionCreate(BaseModel):
    """Input schema — only raw_input is required; everything else comes from the pipeline."""
    raw_input: str = Field(..., min_length=1, description="The original voice/text note")


class TransactionParsed(BaseModel):
    """Intermediate schema returned by the parser agent."""
    type: TransactionType
    category: TransactionCategory
    description: Optional[str] = None
    amount: float
    quantity: Optional[int] = None
    unit_price: Optional[float] = None
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("amount")
    @classmethod
    def amount_must_be_non_negative(cls, v: float) -> float:
        # Allow 0 for ambiguous inputs — validator will flag them for review
        if v < 0:
            raise ValueError("amount must be non-negative")
        return v


class TransactionValidated(TransactionParsed):
    """Parser output + validator fields."""
    needs_review: bool = False
    review_reason: Optional[str] = None
    status: TransactionStatus = TransactionStatus.pending


class TransactionResponse(TransactionValidated):
    """Full schema returned to API callers — includes DB-assigned fields."""
    id: int
    timestamp: datetime
    raw_input: str

    model_config = {"from_attributes": True}


class TransactionUpdate(BaseModel):
    """Payload for PATCH /transactions/{id} — all fields optional."""
    type: Optional[TransactionType] = None
    category: Optional[TransactionCategory] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    quantity: Optional[int] = None
    unit_price: Optional[float] = None
    status: Optional[TransactionStatus] = None
    needs_review: Optional[bool] = None
    review_reason: Optional[str] = None


class SummaryResponse(BaseModel):
    """Response schema for GET /summary."""
    total_income: float
    total_expenses: float
    net_pnl: float
    needs_review_count: int
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    expenses_by_category: dict[str, float] = {}
