"""
validator_agent.py — Phase 4: the honesty layer.

Takes the raw parser output and applies rule-based sanity checks.
Sets needs_review=True and populates review_reason whenever anything
looks wrong — this is what drives the "honest exception list" in the dashboard.

Uses backend.services.calculations for deterministic math checks and
backend.services.categories for allowed-value constants.
"""

from __future__ import annotations

from typing import Any

from backend.services.categories import ALLOWED_CATEGORIES, ALLOWED_TYPES
from backend.services.calculations import (
    AMOUNT_SANITY_LIMIT,
    check_math_consistency,
    is_amount_positive,
    is_amount_sane,
)

# Below this confidence threshold the transaction is always flagged for review
CONFIDENCE_THRESHOLD = 0.6


def validate(parsed_transaction: dict[str, Any]) -> dict[str, Any]:
    """
    Validate a parsed transaction dict and add review metadata.

    Input dict must contain at minimum:
        type, category, amount, confidence

    Returns the same dict enriched with:
        needs_review (bool)
        review_reason (str | None)
        status (str) — "needs_review" | "pending"
    """
    tx = dict(parsed_transaction)  # don't mutate the original
    reasons: list[str] = []

    # ── 1. Type check ────────────────────────────────────────────────
    if tx.get("type") not in ALLOWED_TYPES:
        reasons.append(
            f"Unknown transaction type '{tx.get('type')}' "
            f"(expected: {', '.join(sorted(ALLOWED_TYPES))})"
        )

    # ── 2. Category check ────────────────────────────────────────────
    if tx.get("category") not in ALLOWED_CATEGORIES:
        reasons.append(
            f"Unknown category '{tx.get('category')}' "
            f"(expected: {', '.join(sorted(ALLOWED_CATEGORIES))})"
        )

    # ── 3. Amount checks ─────────────────────────────────────────────
    amount = tx.get("amount", 0)
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        amount = 0.0
        reasons.append("Amount could not be parsed as a number.")

    if not is_amount_positive(amount):
        reasons.append(
            f"Amount is {amount} — must be positive. "
            "No amount was detected in the input."
        )

    if not is_amount_sane(amount):
        reasons.append(
            f"Amount {amount:,.0f} exceeds sanity limit {AMOUNT_SANITY_LIMIT:,.0f} "
            "— possible typo or unit mismatch."
        )

    # ── 4. Deterministic math consistency ────────────────────────────
    consistent, math_reason = check_math_consistency(
        amount=amount,
        quantity=tx.get("quantity"),
        unit_price=tx.get("unit_price"),
    )
    if not consistent and math_reason:
        reasons.append(math_reason)

    # ── 5. Low-confidence check ───────────────────────────────────────
    confidence = tx.get("confidence", 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    if confidence < CONFIDENCE_THRESHOLD:
        reasons.append(
            f"Parser confidence is low ({confidence:.0%}). "
            "Manual review recommended."
        )

    # ── 6. Write results ─────────────────────────────────────────────
    has_issues = len(reasons) > 0
    tx["needs_review"] = has_issues
    tx["review_reason"] = " | ".join(reasons) if reasons else None
    tx["status"] = "needs_review" if has_issues else "pending"

    return tx
