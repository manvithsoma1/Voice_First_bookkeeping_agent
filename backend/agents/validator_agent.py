"""
validator_agent.py — Phase 4: the honesty layer.

Takes the raw parser output and applies rule-based sanity checks.
Sets needs_review=True and populates review_reason whenever anything
looks wrong — this is what drives the "honest exception list" in the dashboard.
"""

from __future__ import annotations

from typing import Any

ALLOWED_TYPES = {"income", "expense"}
ALLOWED_CATEGORIES = {"sales", "raw_materials", "packaging", "transport", "other"}

# Below this confidence threshold the transaction is always flagged for review
CONFIDENCE_THRESHOLD = 0.6

# Suspiciously large single amounts (could be typos)
AMOUNT_SANITY_LIMIT = 500_000


def validate(parsed_transaction: dict[str, Any]) -> dict[str, Any]:
    """
    Validate a parsed transaction dict and add review metadata.

    Input dict must contain at minimum:
        type, category, amount, confidence

    Returns the same dict enriched with:
        needs_review (bool)
        review_reason (str | None)
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

    # ── 3. Amount check ──────────────────────────────────────────────
    amount = tx.get("amount", 0)
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        amount = 0.0
        reasons.append("Amount could not be parsed as a number.")

    if amount <= 0:
        reasons.append(
            f"Amount is {amount} — must be positive. "
            "No amount was detected in the input."
        )

    if amount > AMOUNT_SANITY_LIMIT:
        reasons.append(
            f"Amount {amount:,.0f} exceeds sanity limit {AMOUNT_SANITY_LIMIT:,.0f} "
            "— possible typo or unit mismatch."
        )

    # ── 4. Quantity / unit_price consistency ─────────────────────────
    quantity = tx.get("quantity")
    unit_price = tx.get("unit_price")

    if quantity is not None and unit_price is not None:
        expected_amount = quantity * unit_price
        # Allow 1 % rounding tolerance
        if abs(expected_amount - amount) / max(amount, 1) > 0.01:
            reasons.append(
                f"Amount ({amount}) doesn't match quantity × unit_price "
                f"({quantity} × {unit_price} = {expected_amount})."
            )

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
    tx["needs_review"] = len(reasons) > 0
    tx["review_reason"] = " | ".join(reasons) if reasons else None

    return tx
