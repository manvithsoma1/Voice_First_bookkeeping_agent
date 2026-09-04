"""
main.py — Phase 6: FastAPI backend.

Endpoints:
  POST   /transactions          — log a new text transaction
  POST   /transactions/audio    — upload audio, transcribe, then log
  GET    /transactions          — list transactions (optional date range)
  PATCH  /transactions/{id}     — update / resolve a review item
  DELETE /transactions/{id}     — soft-reject a transaction
  GET    /summary               — P&L summary + expenses by category
  GET    /health                — liveness check
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

load_dotenv()
os.environ.pop("SSLKEYLOGFILE", None)

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
    TransactionUpdate,
)

# ─────────────────────────────────────────────
# App init
# ─────────────────────────────────────────────

app = FastAPI(
    title="Voice-First Bookkeeping Copilot API",
    description="Parse voice/text bookkeeping notes into structured ledger entries.",
    version="2.0.0",
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


def _get_or_404(db: Session, tx_id: int) -> TransactionORM:
    obj = db.query(TransactionORM).filter(TransactionORM.id == tx_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail=f"Transaction {tx_id} not found.")
    return obj


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
    status: Optional[str] = Query(None, description="Filter by status: pending|confirmed|needs_review|rejected"),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db_session),
):
    """Return all transactions, newest first. Optionally filter by date range, review flag, or status."""
    q = db.query(TransactionORM)
    q = _apply_date_filter(q, date_from, date_to)
    if needs_review is not None:
        q = q.filter(TransactionORM.needs_review == needs_review)
    if status is not None:
        q = q.filter(TransactionORM.status == status)
    rows = q.order_by(TransactionORM.timestamp.desc()).limit(limit).all()
    return [_orm_to_response(r) for r in rows]


@app.patch("/transactions/{tx_id}", response_model=TransactionResponse, tags=["Transactions"])
def update_transaction(
    tx_id: int,
    body: TransactionUpdate,
    db: Session = Depends(get_db_session),
):
    """
    Update / resolve a review item. Used by the dashboard Confirm/Edit flow.

    Typical use cases:
    - Confirm as-is:   send {status: "confirmed", needs_review: false}
    - Edit and confirm: send corrected fields + {status: "confirmed", needs_review: false}
    - Re-flag:         send {needs_review: true}
    """
    obj = _get_or_404(db, tx_id)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        # Convert enum values to their string representation for SQLAlchemy
        if hasattr(value, "value"):
            value = value.value
        setattr(obj, field, value)

    db.commit()
    db.refresh(obj)
    return _orm_to_response(obj)


@app.delete("/transactions/{tx_id}", tags=["Transactions"])
def delete_transaction(
    tx_id: int,
    db: Session = Depends(get_db_session),
):
    """
    Soft-reject a transaction — sets status='rejected'.
    The record is preserved in the DB for audit trail purposes (raw_input is kept).
    """
    obj = _get_or_404(db, tx_id)
    obj.status = "rejected"
    obj.needs_review = False
    db.commit()
    return {"message": f"Transaction {tx_id} rejected.", "id": tx_id, "status": "rejected"}


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

    Rejected transactions are excluded from the P&L.
    """
    q = db.query(TransactionORM)
    q = _apply_date_filter(q, date_from, date_to)
    # Exclude rejected transactions from P&L
    q = q.filter(TransactionORM.status != "rejected")
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
