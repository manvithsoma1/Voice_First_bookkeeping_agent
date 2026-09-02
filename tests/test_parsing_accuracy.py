"""
test_parsing_accuracy.py — Phase 8: Accuracy benchmark.

Runs all 40 seed transactions through parse_transaction and compares
against manually-labelled expected outputs.

Usage:
    python -m tests.test_parsing_accuracy

Outputs:
    • Overall accuracy %
    • Per-field accuracy breakdown
    • Full list of misses with reasons (your "honest exception list")
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from backend.agents.parser_agent import parse_transaction  # noqa: E402


# ─────────────────────────────────────────────
# Load seed data
# ─────────────────────────────────────────────

SEED_FILE = Path(__file__).parent.parent / "data" / "seed_transactions.json"


def load_seeds() -> list[dict]:
    with open(SEED_FILE, encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────────
# Evaluation logic
# ─────────────────────────────────────────────

AMOUNT_TOLERANCE = 0.05   # 5% relative tolerance for amount matching
SKIP_AMOUNT_IF_EXPECTED_ZERO = True   # ambiguous inputs with amount=0 skip amount check


def evaluate_transaction(parsed: dict, expected: dict) -> dict[str, Any]:
    """
    Compare parsed output to expected labels.
    Returns a result dict with per-field pass/fail and a combined pass bool.
    """
    results: dict[str, Any] = {"fields": {}, "pass": True, "misses": []}

    # Type
    if "type" in expected:
        match = parsed.get("type") == expected["type"]
        results["fields"]["type"] = match
        if not match:
            results["pass"] = False
            results["misses"].append(
                f"type: got '{parsed.get('type')}', expected '{expected['type']}'"
            )

    # Category
    if "category" in expected:
        match = parsed.get("category") == expected["category"]
        results["fields"]["category"] = match
        if not match:
            results["pass"] = False
            results["misses"].append(
                f"category: got '{parsed.get('category')}', expected '{expected['category']}'"
            )

    # Amount (skip if expected is 0 — ambiguous inputs)
    if "amount" in expected:
        exp_amount = float(expected["amount"])
        got_amount = float(parsed.get("amount", 0))

        if exp_amount == 0 and SKIP_AMOUNT_IF_EXPECTED_ZERO:
            results["fields"]["amount"] = "skipped (ambiguous)"
        else:
            rel_err = abs(got_amount - exp_amount) / max(exp_amount, 1)
            match = rel_err <= AMOUNT_TOLERANCE
            results["fields"]["amount"] = match
            if not match:
                results["pass"] = False
                results["misses"].append(
                    f"amount: got {got_amount}, expected {exp_amount} "
                    f"(err={rel_err:.1%})"
                )

    # Confidence max (for ambiguous inputs)
    if "confidence_max" in expected:
        conf_max = float(expected["confidence_max"])
        got_conf = float(parsed.get("confidence", 1.0))
        match = got_conf <= conf_max
        results["fields"]["confidence_ceiling"] = match
        if not match:
            results["pass"] = False
            results["misses"].append(
                f"confidence: got {got_conf:.2f}, expected ≤ {conf_max:.2f} "
                "(ambiguous input should be low-confidence)"
            )

    # Quantity (optional — only checked if present in expected and non-null)
    if "quantity" in expected and expected["quantity"] is not None:
        match = parsed.get("quantity") == expected["quantity"]
        results["fields"]["quantity"] = match
        if not match:
            results["pass"] = False
            results["misses"].append(
                f"quantity: got {parsed.get('quantity')}, expected {expected['quantity']}"
            )

    # Unit price (optional)
    if "unit_price" in expected and expected["unit_price"] is not None:
        exp_up = float(expected["unit_price"])
        got_up = float(parsed.get("unit_price") or 0)
        rel_err = abs(got_up - exp_up) / max(exp_up, 1)
        match = rel_err <= AMOUNT_TOLERANCE
        results["fields"]["unit_price"] = match
        if not match:
            results["pass"] = False
            results["misses"].append(
                f"unit_price: got {got_up}, expected {exp_up}"
            )

    return results


# ─────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────

def run_accuracy_test(verbose: bool = True) -> dict[str, Any]:
    seeds = load_seeds()
    total = len(seeds)
    passed = 0
    failed_items: list[dict] = []

    field_counts: dict[str, list[bool]] = {}

    print(f"\n{'='*60}")
    print(f"  Voice-First Bookkeeping Copilot — Parser Accuracy Test")
    print(f"  Running {total} test cases...")
    print(f"{'='*60}\n")

    for i, seed in enumerate(seeds, 1):
        raw_input = seed["raw_input"]
        expected = seed["expected"]

        if verbose:
            print(f"[{i:02d}/{total}] '{raw_input[:60]}'")

        # Rate-limit to avoid hitting Groq's free-tier limits
        if i > 1:
            time.sleep(0.3)

        try:
            parsed = parse_transaction(raw_input)
        except Exception as exc:
            print(f"       ⚠ EXCEPTION: {exc}")
            failed_items.append({
                "index": i,
                "raw_input": raw_input,
                "exception": str(exc),
                "misses": [f"Parser threw exception: {exc}"],
            })
            continue

        result = evaluate_transaction(parsed, expected)

        # Accumulate per-field stats
        for field, val in result["fields"].items():
            if isinstance(val, bool):
                field_counts.setdefault(field, []).append(val)

        if result["pass"]:
            passed += 1
            if verbose:
                print(f"       ✓ PASS  (confidence={parsed.get('confidence', 0):.2f})")
        else:
            failed_items.append({
                "index": i,
                "raw_input": raw_input,
                "parsed": parsed,
                "expected": expected,
                "misses": result["misses"],
            })
            if verbose:
                print(f"       ✗ FAIL")
                for miss in result["misses"]:
                    print(f"         • {miss}")

    # ── Summary ────────────────────────────────────────────────────────
    accuracy = (passed / total) * 100

    print(f"\n{'='*60}")
    print(f"  OVERALL ACCURACY: {accuracy:.1f}%  ({passed}/{total} passed)")
    print(f"{'='*60}")

    print("\n  Per-field accuracy:")
    for field, vals in sorted(field_counts.items()):
        pct = sum(vals) / len(vals) * 100
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"    {field:<22} {bar} {pct:.0f}%")

    if failed_items:
        print(f"\n  MISSES ({len(failed_items)})  — your honest exception list:")
        print("  " + "─" * 56)
        for item in failed_items:
            print(f"\n  [{item['index']:02d}] \"{item['raw_input']}\"")
            for miss in item.get("misses", []):
                print(f"       → {miss}")
    else:
        print("\n  🎉  All tests passed!")

    print(f"\n{'='*60}\n")

    return {
        "total": total,
        "passed": passed,
        "accuracy_pct": accuracy,
        "failed_items": failed_items,
        "field_accuracy": {
            field: sum(vals) / len(vals) * 100
            for field, vals in field_counts.items()
        },
    }


if __name__ == "__main__":
    run_accuracy_test(verbose=True)
