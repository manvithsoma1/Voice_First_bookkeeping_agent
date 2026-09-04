"""
categories.py — Single source of truth for allowed transaction types and categories.

Import from here instead of hard-coding strings across multiple modules.
"""

from __future__ import annotations

# ─── Allowed values ────────────────────────────────────────────────────────────

ALLOWED_TYPES: frozenset[str] = frozenset({"income", "expense"})

ALLOWED_CATEGORIES: frozenset[str] = frozenset(
    {"sales", "raw_materials", "packaging", "transport", "other"}
)

ALLOWED_STATUSES: frozenset[str] = frozenset(
    {"pending", "confirmed", "needs_review", "rejected"}
)

# ─── Category descriptions (for prompts and UI) ────────────────────────────────

CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "sales": "Selling products, received payment, customer orders",
    "raw_materials": "Ingredients, spices, produce bought for making products",
    "packaging": "Jars, lids, labels, boxes, wrapping",
    "transport": "Delivery, shipping, fuel, courier fees",
    "other": "Anything that doesn't fit the above categories",
}

# ─── Human-readable display names ──────────────────────────────────────────────

CATEGORY_DISPLAY: dict[str, str] = {
    "sales": "Sales",
    "raw_materials": "Raw Materials",
    "packaging": "Packaging",
    "transport": "Transport",
    "other": "Other",
}

TYPE_DISPLAY: dict[str, str] = {
    "income": "Income",
    "expense": "Expense",
}

STATUS_DISPLAY: dict[str, str] = {
    "pending": "Pending",
    "confirmed": "Confirmed",
    "needs_review": "Needs Review",
    "rejected": "Rejected",
}
