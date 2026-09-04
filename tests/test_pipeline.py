"""
test_pipeline.py — Integration tests for the LangGraph pipeline.

The LLM (parse_transaction) is mocked so these tests are deterministic,
fast, and don't consume API quota.

Tests the full parse → validate → save flow using an isolated temp SQLite DB.

Usage:
    python -m pytest tests/test_pipeline.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """
    Each test gets its own SQLite file + fresh graph so there is no state
    bleed between runs.
    """
    db_file = str(tmp_path / "test_bookkeeping.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    # Re-create engine/session for the new DB path
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import backend.db as db_mod
    import backend.models as models_mod

    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    models_mod.Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(db_mod, "engine", engine)
    monkeypatch.setattr(db_mod, "SessionLocal", sessionmaker(bind=engine))

    # Reset the compiled graph so it picks up the fresh engine
    import backend.graph as graph_mod
    monkeypatch.setattr(graph_mod, "_compiled_graph", None)

    yield


def _mock_parse(
    type_="income", category="sales", amount=1000.0,
    quantity=5, unit_price=200.0, confidence=0.95,
    description="pickle jars", raw_input="test input",
) -> dict:
    """Return a mock parsed-transaction dict."""
    return {
        "type": type_,
        "category": category,
        "description": description,
        "amount": amount,
        "quantity": quantity,
        "unit_price": unit_price,
        "confidence": confidence,
        "raw_input": raw_input,
    }


# The parse_node inside graph.py calls parse_transaction from parser_agent.
# We must patch the reference inside graph.py's own namespace.
PARSE_PATH = "backend.graph.parse_transaction"


# ─── Full pipeline: confident transaction ─────────────────────────────────────

def test_confident_transaction_saved_as_confirmed():
    """A high-confidence, valid transaction should be saved with status=confirmed."""
    mock_result = _mock_parse()

    with patch(PARSE_PATH, return_value=mock_result):
        from backend.graph import run_pipeline
        result = run_pipeline("sold 5 jars today 200 each")

    assert result["type"] == "income"
    assert result["category"] == "sales"
    assert result["amount"] == 1000.0
    assert result["needs_review"] is False
    assert result["status"] == "confirmed"
    assert result["id"] is not None
    assert result["timestamp"] is not None


def test_description_persisted():
    """The description field should be stored in the database."""
    mock_result = _mock_parse(description="mango pickle jars")

    with patch(PARSE_PATH, return_value=mock_result):
        from backend.graph import run_pipeline
        result = run_pipeline("sold mango pickle jars")

    assert result["description"] == "mango pickle jars"


def test_raw_input_preserved():
    """The original raw input must always be stored for audit trail."""
    raw = "sold five jars two hundred each"
    mock_result = _mock_parse(raw_input=raw)

    with patch(PARSE_PATH, return_value=mock_result):
        from backend.graph import run_pipeline
        result = run_pipeline(raw)

    assert result["raw_input"] == raw


# ─── Full pipeline: uncertain transaction ─────────────────────────────────────

def test_zero_amount_flagged_for_review():
    """A transaction with amount=0 must be flagged for review."""
    mock_result = _mock_parse(
        amount=0, quantity=None, unit_price=None, confidence=0.45
    )

    with patch(PARSE_PATH, return_value=mock_result):
        from backend.graph import run_pipeline
        result = run_pipeline("bought some bottles today")

    assert result["needs_review"] is True
    assert result["status"] == "needs_review"
    assert result["review_reason"] is not None


def test_low_confidence_flagged_for_review():
    """Low parser confidence should trigger review flag."""
    mock_result = _mock_parse(confidence=0.35, amount=0)

    with patch(PARSE_PATH, return_value=mock_result):
        from backend.graph import run_pipeline
        result = run_pipeline("made some money today")

    assert result["needs_review"] is True


def test_math_conflict_flagged_for_review():
    """Quantity × unit_price mismatch should trigger review."""
    # 5 × 200 = 1000, but amount stated as 1200
    mock_result = _mock_parse(amount=1200, quantity=5, unit_price=200, confidence=0.9)

    with patch(PARSE_PATH, return_value=mock_result):
        from backend.graph import run_pipeline
        result = run_pipeline("5 jars at 200 each total 1200")

    assert result["needs_review"] is True
    assert "1,000" in result["review_reason"] or "1000" in result["review_reason"]


# ─── Validator: deterministic decisions ───────────────────────────────────────

def test_expense_with_valid_amount_passes():
    mock_result = _mock_parse(
        type_="expense", category="packaging",
        amount=300, quantity=None, unit_price=None,
        confidence=0.9, description="glass jars",
    )

    with patch(PARSE_PATH, return_value=mock_result):
        from backend.graph import run_pipeline
        result = run_pipeline("paid 300 for glass jars")

    assert result["type"] == "expense"
    assert result["category"] == "packaging"
    assert not result["needs_review"]
    assert result["status"] == "confirmed"


def test_transport_expense_passes():
    mock_result = _mock_parse(
        type_="expense", category="transport",
        amount=150, quantity=None, unit_price=None,
        confidence=0.92, description="delivery charges",
    )

    with patch(PARSE_PATH, return_value=mock_result):
        from backend.graph import run_pipeline
        result = run_pipeline("delivery charges 150 rupees")

    assert result["category"] == "transport"
    assert not result["needs_review"]


# ─── Pipeline error handling ──────────────────────────────────────────────────

def test_parser_exception_propagates():
    """If the parser raises, the error surfaces in the pipeline state."""
    with patch(PARSE_PATH, side_effect=Exception("Groq API down")):
        from backend.graph import run_pipeline
        # parse_node catches the exception and sets state["error"];
        # run_pipeline then raises RuntimeError
        with pytest.raises(RuntimeError, match="parse_node failed"):
            run_pipeline("some input")
