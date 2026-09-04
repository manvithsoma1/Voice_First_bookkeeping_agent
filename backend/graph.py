"""
graph.py — Phase 5: LangGraph orchestration.

Pipeline: parse_node → validate_node → save_node

State flows as a plain dict through the graph so each node can read
prior outputs and add its own. The final state is returned to the caller.

Schema v2: includes description and status in PipelineState.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from backend.agents.ledger_agent import save_transaction
from backend.agents.parser_agent import parse_transaction
from backend.agents.validator_agent import validate
from backend.db import init_db


# ─────────────────────────────────────────────
# Shared state schema
# ─────────────────────────────────────────────

class PipelineState(TypedDict, total=False):
    # Input
    raw_input: str

    # After parse_node
    type: str
    category: str
    description: str | None
    amount: float
    quantity: int | None
    unit_price: float | None
    confidence: float

    # After validate_node
    needs_review: bool
    review_reason: str | None
    status: str

    # After save_node
    id: int
    timestamp: str

    # Error handling
    error: str | None


# ─────────────────────────────────────────────
# Nodes
# ─────────────────────────────────────────────

def parse_node(state: PipelineState) -> PipelineState:
    """Call the LLM parser and merge results into state."""
    try:
        parsed = parse_transaction(state["raw_input"])
        return {**state, **parsed}
    except Exception as exc:
        return {**state, "error": f"parse_node failed: {exc}"}


def validate_node(state: PipelineState) -> PipelineState:
    """Run rule-based validation and flag needs_review if applicable."""
    if state.get("error"):
        return state  # skip on upstream error

    try:
        validated = validate(dict(state))
        return {**state, **validated}
    except Exception as exc:
        return {**state, "error": f"validate_node failed: {exc}"}


def save_node(state: PipelineState) -> PipelineState:
    """Persist the transaction to the database."""
    if state.get("error"):
        return state  # skip on upstream error

    try:
        saved = save_transaction(dict(state))
        return {**state, **saved}
    except Exception as exc:
        return {**state, "error": f"save_node failed: {exc}"}


# ─────────────────────────────────────────────
# Graph assembly
# ─────────────────────────────────────────────

def _build_graph() -> Any:
    graph = StateGraph(PipelineState)

    graph.add_node("parse", parse_node)
    graph.add_node("validate", validate_node)
    graph.add_node("save", save_node)

    graph.set_entry_point("parse")
    graph.add_edge("parse", "validate")
    graph.add_edge("validate", "save")
    graph.add_edge("save", END)

    return graph.compile()


_compiled_graph = None


def _get_graph() -> Any:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _build_graph()
    return _compiled_graph


# ─────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────

def run_pipeline(raw_input: str) -> dict[str, Any]:
    """
    Run the full parse → validate → save pipeline.

    Args:
        raw_input: The original voice/text note string.

    Returns:
        The final pipeline state dict (includes id, timestamp, etc.).

    Raises:
        RuntimeError: If any node sets an error and propagates it.
    """
    # Ensure tables exist before first write
    init_db()

    graph = _get_graph()
    initial_state: PipelineState = {"raw_input": raw_input}
    final_state = graph.invoke(initial_state)

    if final_state.get("error"):
        raise RuntimeError(final_state["error"])

    return dict(final_state)
