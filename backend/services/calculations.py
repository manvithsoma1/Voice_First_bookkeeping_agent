"""
calculations.py — Deterministic financial math helpers.

The master plan principle: "Let AI interpret; let Python calculate."
All arithmetic is done here — never trusted to the LLM alone.
"""

from __future__ import annotations

from typing import Optional


# ─── Amount calculation ────────────────────────────────────────────────────────

def calculate_amount(
    quantity: Optional[int | float],
    unit_price: Optional[float],
) -> Optional[float]:
    """
    Compute total = quantity × unit_price.

    Returns None if either operand is missing or invalid.
    """
    if quantity is None or unit_price is None:
        return None
    try:
        q = float(quantity)
        p = float(unit_price)
        if q <= 0 or p <= 0:
            return None
        return round(q * p, 2)
    except (TypeError, ValueError):
        return None


# ─── Math consistency check ───────────────────────────────────────────────────

MATH_TOLERANCE = 0.01  # 1% relative error allowed


def check_math_consistency(
    amount: Optional[float],
    quantity: Optional[int | float],
    unit_price: Optional[float],
) -> tuple[bool, Optional[str]]:
    """
    Verify that stated amount ≈ quantity × unit_price.

    Returns:
        (consistent: bool, reason: str | None)
        - consistent=True, reason=None → all good or not enough info to check
        - consistent=False, reason=str → conflict detected with description
    """
    calculated = calculate_amount(quantity, unit_price)
    if calculated is None or amount is None:
        # Not enough information to check — not a failure
        return True, None

    try:
        stated = float(amount)
    except (TypeError, ValueError):
        return True, None

    if stated <= 0:
        # Amount-missing case is handled elsewhere
        return True, None

    rel_error = abs(calculated - stated) / max(stated, 1)
    if rel_error > MATH_TOLERANCE:
        return False, (
            f"Amount ₹{stated:,.0f} doesn't match "
            f"quantity × unit_price ({quantity} × ₹{unit_price} = ₹{calculated:,.0f}). "
            f"Difference: ₹{abs(calculated - stated):,.0f}"
        )
    return True, None


# ─── Amount validation helpers ────────────────────────────────────────────────

AMOUNT_SANITY_LIMIT: float = 500_000  # ₹5 lakh — flag suspiciously large amounts


def is_amount_positive(amount: Optional[float]) -> bool:
    """Return True if amount is a positive number."""
    try:
        return float(amount) > 0  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def is_amount_sane(amount: Optional[float]) -> bool:
    """Return True if amount is below the sanity limit."""
    try:
        return float(amount) <= AMOUNT_SANITY_LIMIT  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return True  # non-numeric will be caught elsewhere
