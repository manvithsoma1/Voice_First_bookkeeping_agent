"""
insight_agent.py — Phase 2 optional: business insights from stored transaction history.

Queries the DB for recent transactions and asks the Groq LLM to generate
2–4 actionable, grounded insights. The LLM is only allowed to refer to
data it actually receives — it cannot invent financial facts.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
from groq import Groq

load_dotenv()
os.environ.pop("SSLKEYLOGFILE", None)

from backend.db import get_db
from backend.models import TransactionORM

_client: Optional[Groq] = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError("GROQ_API_KEY not set.")
        _client = Groq(api_key=api_key)
    return _client


# ─── Data gathering ────────────────────────────────────────────────────────────

def _gather_stats(days: int = 30) -> dict:
    """
    Query the DB for the last `days` days and summarise transaction data.
    Returns a structured dict that is passed to the LLM as grounded context.
    """
    since = datetime.utcnow() - timedelta(days=days)

    with get_db() as db:
        rows = (
            db.query(TransactionORM)
            .filter(
                TransactionORM.timestamp >= since,
                TransactionORM.status != "rejected",
            )
            .order_by(TransactionORM.timestamp.asc())
            .all()
        )

    if not rows:
        return {}

    income_rows = [r for r in rows if r.type == "income"]
    expense_rows = [r for r in rows if r.type == "expense"]

    total_income = sum(r.amount for r in income_rows)
    total_expenses = sum(r.amount for r in expense_rows)

    # Category breakdown
    expense_by_cat: dict[str, float] = {}
    for r in expense_rows:
        expense_by_cat[r.category] = expense_by_cat.get(r.category, 0.0) + r.amount

    # Weekly revenue (last 4 weeks)
    weekly: dict[str, float] = {}
    for r in income_rows:
        week_key = r.timestamp.strftime("Week of %d %b")
        weekly[week_key] = weekly.get(week_key, 0.0) + r.amount

    # Top income descriptions
    top_sales = sorted(
        [
            {"desc": r.description or r.raw_input[:40], "amount": r.amount}
            for r in income_rows
            if r.amount > 0
        ],
        key=lambda x: x["amount"],
        reverse=True,
    )[:5]

    return {
        "period_days": days,
        "total_transactions": len(rows),
        "total_income": round(total_income, 2),
        "total_expenses": round(total_expenses, 2),
        "net_profit": round(total_income - total_expenses, 2),
        "expense_breakdown": {k: round(v, 2) for k, v in expense_by_cat.items()},
        "weekly_revenue": weekly,
        "top_sales": top_sales,
        "needs_review_count": sum(1 for r in rows if r.needs_review),
    }


# ─── Prompt ───────────────────────────────────────────────────────────────────

INSIGHT_SYSTEM_PROMPT = """You are a financial insight assistant for a small home pickle/condiment business.

You will receive a JSON summary of the business's recent transactions.
Based ONLY on this data, generate 3–4 short, practical insights that would help the owner.

Rules:
- Only reference numbers and facts present in the data.
- Never invent figures or trends not supported by the data.
- Keep each insight to 1–2 sentences.
- Be specific and actionable, not generic.
- Return a JSON array of insight strings. Example:
  ["Your packaging costs represent X% of total expenses.",
   "Weekend revenue is higher than weekdays.",
   "You have 3 transactions pending review."]

Return ONLY the JSON array — no markdown, no explanation."""


def generate_insights(days: int = 30) -> list[str]:
    """
    Generate business insights from the last `days` days of transactions.

    Returns a list of insight strings, or a single "not enough data" message.
    """
    stats = _gather_stats(days)

    if not stats or stats.get("total_transactions", 0) < 3:
        return ["Not enough transaction data yet. Log more transactions to get insights."]

    client = _get_client()
    prompt = json.dumps(stats, indent=2)

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": INSIGHT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=512,
        )

        content = response.choices[0].message.content or "[]"
        # Strip markdown fences if present
        import re
        content = re.sub(r"```(?:json)?", "", content).strip()

        insights = json.loads(content)
        if isinstance(insights, list):
            return [str(i) for i in insights if i]
        return ["Insight generation returned unexpected format."]

    except Exception as exc:
        return [f"Could not generate insights: {exc}"]
