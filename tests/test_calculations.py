"""
test_calculations.py — Unit tests for backend.services.calculations.

All purely deterministic — no LLM, no DB, no network.

Usage:
    python -m pytest tests/test_calculations.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from backend.services.calculations import (
    AMOUNT_SANITY_LIMIT,
    MATH_TOLERANCE,
    calculate_amount,
    check_math_consistency,
    is_amount_positive,
    is_amount_sane,
)


# ─── calculate_amount ─────────────────────────────────────────────────────────

def test_basic_multiplication():
    assert calculate_amount(5, 200) == 1000.0


def test_decimal_quantity():
    assert calculate_amount(2.5, 100) == 250.0


def test_none_quantity_returns_none():
    assert calculate_amount(None, 200) is None


def test_none_unit_price_returns_none():
    assert calculate_amount(5, None) is None


def test_both_none_returns_none():
    assert calculate_amount(None, None) is None


def test_zero_quantity_returns_none():
    # Zero quantity is not a valid transaction
    assert calculate_amount(0, 200) is None


def test_zero_price_returns_none():
    assert calculate_amount(5, 0) is None


def test_large_values():
    assert calculate_amount(100, 500) == 50_000.0


def test_rounding():
    # 3 × 33.33 = 99.99
    result = calculate_amount(3, 33.33)
    assert result == 99.99


# ─── check_math_consistency ───────────────────────────────────────────────────

def test_consistent_values_pass():
    ok, reason = check_math_consistency(amount=1000, quantity=5, unit_price=200)
    assert ok is True
    assert reason is None


def test_inconsistent_values_fail():
    ok, reason = check_math_consistency(amount=1200, quantity=5, unit_price=200)
    assert ok is False
    assert reason is not None
    assert "1,000" in reason or "1000" in reason


def test_within_tolerance_passes():
    # 3 × 45 = 135, stated 135.5 (well within 1%)
    ok, reason = check_math_consistency(amount=135.5, quantity=3, unit_price=45)
    assert ok is True


def test_none_quantity_skips_check():
    ok, reason = check_math_consistency(amount=500, quantity=None, unit_price=100)
    assert ok is True
    assert reason is None


def test_none_unit_price_skips_check():
    ok, reason = check_math_consistency(amount=500, quantity=5, unit_price=None)
    assert ok is True
    assert reason is None


def test_none_amount_skips_check():
    ok, reason = check_math_consistency(amount=None, quantity=5, unit_price=100)
    assert ok is True
    assert reason is None


def test_zero_amount_skips_math_check():
    # Zero-amount is an "amount missing" case, handled elsewhere
    ok, reason = check_math_consistency(amount=0, quantity=5, unit_price=200)
    assert ok is True


# ─── is_amount_positive ───────────────────────────────────────────────────────

def test_positive_amount_is_positive():
    assert is_amount_positive(100) is True


def test_zero_is_not_positive():
    assert is_amount_positive(0) is False


def test_negative_is_not_positive():
    assert is_amount_positive(-50) is False


def test_none_is_not_positive():
    assert is_amount_positive(None) is False


def test_string_number_is_positive():
    assert is_amount_positive("250") is True


# ─── is_amount_sane ──────────────────────────────────────────────────────────

def test_normal_amount_is_sane():
    assert is_amount_sane(1000) is True


def test_amount_at_limit_is_sane():
    assert is_amount_sane(AMOUNT_SANITY_LIMIT) is True


def test_amount_above_limit_is_not_sane():
    assert is_amount_sane(AMOUNT_SANITY_LIMIT + 1) is False


def test_zero_is_sane():
    assert is_amount_sane(0) is True


def test_none_is_sane():
    # None is treated as sane — other checks handle missing amounts
    assert is_amount_sane(None) is True
