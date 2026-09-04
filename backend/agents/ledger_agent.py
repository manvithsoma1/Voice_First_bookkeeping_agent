"""
ledger_agent.py — Phase 5 helper: persistence layer for the LangGraph save_node.

All DB writes go through here so graph.py stays clean of SQLAlchemy details.

Schema v2: persists description and status fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.db import get_db
from backend.models import TransactionORM


def save_transaction(validated: dict[str, Any]) -> dict[str, Any]:
    """
    Persist a validated transaction dict to the database.

    Returns the same data enriched with the DB-assigned `id` and `timestamp`.
    """
    # Determine status: if already "needs_review" keep it, else "confirmed"
    status = validated.get("status", "pending")
    if status not in {"needs_review", "confirmed", "rejected"}:
        status = "needs_review" if validated.get("needs_review") else "confirmed"

    with get_db() as db:
        orm_obj = TransactionORM(
            timestamp=datetime.utcnow(),
            raw_input=validated["raw_input"],
            type=validated["type"],
            category=validated["category"],
            description=validated.get("description"),
            amount=validated["amount"],
            quantity=validated.get("quantity"),
            unit_price=validated.get("unit_price"),
            confidence=validated["confidence"],
            needs_review=validated.get("needs_review", False),
            review_reason=validated.get("review_reason"),
            status=status,
        )
        db.add(orm_obj)
        db.flush()        # get the auto-generated id before commit
        db.refresh(orm_obj)

        saved = {
            "id": orm_obj.id,
            "timestamp": orm_obj.timestamp.isoformat(),
            "raw_input": orm_obj.raw_input,
            "type": orm_obj.type,
            "category": orm_obj.category,
            "description": orm_obj.description,
            "amount": orm_obj.amount,
            "quantity": orm_obj.quantity,
            "unit_price": orm_obj.unit_price,
            "confidence": orm_obj.confidence,
            "needs_review": orm_obj.needs_review,
            "review_reason": orm_obj.review_reason,
            "status": orm_obj.status,
        }

    return saved
