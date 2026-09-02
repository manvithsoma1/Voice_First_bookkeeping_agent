"""
main.py — Phase 6: FastAPI backend.

Endpoints:
  POST  /transactions         — log a new text transaction
  POST  /transactions/audio   — upload audio, transcribe, then log
  GET   /transactions         — list transactions (optional date range)
  GET   /summary              — P&L summary + expenses by category
  GET   /health               — liveness check
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.agents.parser_agent import transcribe_audio
from backend.db import get_db_session, init_db
from backend.graph import run_pipeline
from backend.models import (
    SummaryResponse,
    TransactionCreate,
    TransactionORM,
    TransactionResponse,
)

load_dotenv()

# ─────────────────────────────────────────────
# App init
# ─────────────────────────────────────────────

app = FastAPI(
    title="Voice-First Bookkeeping Copilot API",
    description="Parse voice/text bookkeeping notes into structured ledger entries.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _orm_to_response(obj: TransactionORM) -> TransactionResponse:
    return TransactionResponse.model_validate(obj)


def _apply_date_filter(query, date_from: Optional[datetime], date_to: Optional[datetime]):
    if date_from:
        query = query.filter(TransactionORM.timestamp >= date_from)
    if date_to:
        query = query.filter(TransactionORM.timestamp <= date_to)
    return query


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@app.get("/health", tags=["Meta"])
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.post("/transactions", response_model=TransactionResponse, tags=["Transactions"])
def create_transaction(body: TransactionCreate):
    """
    Accept a plain-text bookkeeping note, run it through the full
    parse → validate → save pipeline, and return the saved record.
    """
    try:
        result = run_pipeline(body.raw_input)
        # run_pipeline returns a dict; re-fetch from DB for the ORM object
        # (simpler than building TransactionResponse from a dict manually)
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}") from exc


@app.post("/transactions/audio", response_model=TransactionResponse, tags=["Transactions"])
async def create_transaction_from_audio(audio: UploadFile = File(...)):
    """
    Accept an audio file upload, transcribe with Whisper, then run the
    same parse → validate → save pipeline.
    """
    import tempfile
    import shutil
    from pathlib import Path

    suffix = Path(audio.filename or "audio.wav").suffix.lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(audio.file, tmp)
        tmp_path = tmp.name

    try:
        text = transcribe_audio(tmp_path)
    except (FileNotFoundError, ValueError) as exc:
        os.unlink(tmp_path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    try:
        result = run_pipeline(text)
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/transactions", response_model=list[TransactionResponse], tags=["Transactions"])
def list_transactions(
    date_from: Optional[datetime] = Query(None, description="ISO datetime, inclusive"),
    date_to: Optional[datetime] = Query(None, description="ISO datetime, inclusive"),
    needs_review: Optional[bool] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db_session),
):
    """Return all transactions, newest first. Optionally filter by date range or review flag."""
    q = db.query(TransactionORM)
    q = _apply_date_filter(q, date_from, date_to)
    if needs_review is not None:
        q = q.filter(TransactionORM.needs_review == needs_review)
    rows = q.order_by(TransactionORM.timestamp.desc()).limit(limit).all()
    return [_orm_to_response(r) for r in rows]


@app.get("/summary", response_model=SummaryResponse, tags=["Analytics"])
def get_summary(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: Session = Depends(get_db_session),
):
    """
    Return P&L summary for the requested date range:
    total income, total expenses, net P&L, needs_review count,
    and a breakdown of expenses by category.
    """
    q = db.query(TransactionORM)
    q = _apply_date_filter(q, date_from, date_to)
    rows = q.all()

    total_income = sum(r.amount for r in rows if r.type == "income")
    total_expenses = sum(r.amount for r in rows if r.type == "expense")
    needs_review_count = sum(1 for r in rows if r.needs_review)

    expenses_by_category: dict[str, float] = {}
    for r in rows:
        if r.type == "expense":
            expenses_by_category[r.category] = (
                expenses_by_category.get(r.category, 0.0) + r.amount
            )

    return SummaryResponse(
        total_income=round(total_income, 2),
        total_expenses=round(total_expenses, 2),
        net_pnl=round(total_income - total_expenses, 2),
        needs_review_count=needs_review_count,
        date_from=date_from,
        date_to=date_to,
        expenses_by_category={k: round(v, 2) for k, v in expenses_by_category.items()},
    )
