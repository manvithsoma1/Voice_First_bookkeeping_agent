"""
test_validator.py — Unit tests for the validator agent.

These tests are deterministic (no LLM calls) and should run in milliseconds.

Usage:
    python -m pytest tests/test_validator.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from backend.agents.validator_agent import validate


# ─── Helpers ──────────────────────────────────────────────────────────────────

def base_tx(**kwargs) -> dict:
    """Minimal valid transaction dict, overridable via kwargs."""
    tx = {
        "raw_input": "test input",
        "type": "income",
        "category": "sales",
        "amount": 1000.0,
        "quantity": None,
        "unit_price": None,
        "confidence": 0.95,
        "description": None,
    }
    tx.update(kwargs)
    return tx


# ─── Type / Category validation ───────────────────────────────────────────────

def test_valid_income_passes():
    result = validate(base_tx(type="income", category="sales", amount=500))
    assert not result["needs_review"]
    assert result["review_reason"] is None
    assert result["status"] == "pending"


def test_valid_expense_passes():
    result = validate(base_tx(type="expense", category="packaging", amount=200))
    assert not result["needs_review"]


def test_invalid_type_flags_review():
    result = validate(base_tx(type="transfer"))
    assert result["needs_review"]
    assert "type" in result["review_reason"].lower()


def test_invalid_category_flags_review():
    result = validate(base_tx(category="salary"))
    assert result["needs_review"]
    assert "category" in result["review_reason"].lower()


# ─── Amount checks ────────────────────────────────────────────────────────────

def test_zero_amount_flags_review():
    result = validate(base_tx(amount=0))
    assert result["needs_review"]
    assert "amount" in result["review_reason"].lower()


def test_negative_amount_flags_review():
    result = validate(base_tx(amount=-100))
    assert result["needs_review"]


def test_suspiciously_large_amount_flags_review():
    result = validate(base_tx(amount=600_000))
    assert result["needs_review"]
    assert "sanity" in result["review_reason"].lower() or "limit" in result["review_reason"].lower()


def test_positive_amount_ok():
    result = validate(base_tx(amount=1.0))
    assert not result["needs_review"]


# ─── Math consistency ─────────────────────────────────────────────────────────

def test_consistent_math_passes():
    # 5 × 200 = 1000
    result = validate(base_tx(amount=1000, quantity=5, unit_price=200))
    assert not result["needs_review"]


def test_inconsistent_math_flags_review():
    # 5 × 200 = 1000, but stated 1200
    result = validate(base_tx(amount=1200, quantity=5, unit_price=200))
    assert result["needs_review"]
    assert "1,000" in result["review_reason"] or "1000" in result["review_reason"]


def test_math_within_tolerance_passes():
    # 3 × 45 = 135, allow 1% tolerance → 135.00 stated as 135 is fine
    result = validate(base_tx(amount=135, quantity=3, unit_price=45))
    assert not result["needs_review"]


def test_missing_unit_price_skips_math_check():
    # Can't check math without unit_price — should not flag
    result = validate(base_tx(amount=500, quantity=5, unit_price=None))
    assert not result["needs_review"]


def test_missing_quantity_skips_math_check():
    result = validate(base_tx(amount=500, quantity=None, unit_price=100))
    assert not result["needs_review"]


# ─── Confidence threshold ─────────────────────────────────────────────────────

def test_low_confidence_flags_review():
    result = validate(base_tx(confidence=0.4))
    assert result["needs_review"]
    assert "confidence" in result["review_reason"].lower()


def test_confidence_at_threshold_passes():
    # Threshold is 0.6 — exactly at threshold is borderline
    result = validate(base_tx(confidence=0.6))
    # < 0.6 flags, so 0.6 should pass
    assert not result["needs_review"]


def test_confidence_just_below_threshold_flags():
    result = validate(base_tx(confidence=0.59))
    assert result["needs_review"]


# ─── Status field ─────────────────────────────────────────────────────────────

def test_clean_transaction_status_is_pending():
    result = validate(base_tx())
    assert result["status"] == "pending"


def test_review_transaction_status_is_needs_review():
    result = validate(base_tx(amount=0))
    assert result["status"] == "needs_review"


# ─── Multiple issues accumulate ───────────────────────────────────────────────

def test_multiple_issues_all_appear_in_reason():
    result = validate(base_tx(amount=0, confidence=0.3))
    assert result["needs_review"]
    reason = result["review_reason"]
    # Should mention both amount and confidence
    assert "amount" in reason.lower()
    assert "confidence" in reason.lower()
