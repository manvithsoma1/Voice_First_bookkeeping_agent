"""
dashboard/app.py — Phase 7: Streamlit front-end (v2).

Features:
  • Text input to log a new transaction
  • Audio file upload for voice notes
  • P&L overview metrics (income / expenses / net / needs-review count)
  • P&L time-series line chart
  • Expenses-by-category bar chart
  • Transaction ledger with description + status columns
  • Needs-review exception queue with Confirm / Edit / Reject buttons (human-in-the-loop)
  • Business Insights panel (Phase 2, optional — calls insight_agent)
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
os.environ.pop("SSLKEYLOGFILE", None)


# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Voice Bookkeeping Copilot",
    page_icon="📒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# Custom CSS — premium dark theme
# ─────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Dark gradient background */
.stApp {
    background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #16213e 100%);
    color: #e8eaf6;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: rgba(255,255,255,0.04);
    border-right: 1px solid rgba(255,255,255,0.08);
}

/* Metric cards */
[data-testid="metric-container"] {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 12px;
    padding: 16px;
    backdrop-filter: blur(10px);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
[data-testid="metric-container"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 32px rgba(0,0,0,0.3);
}

/* Needs-review badge */
.review-badge {
    background: linear-gradient(135deg, #ff6b6b, #ee5a24);
    color: white;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    display: inline-block;
}

/* Status tags */
.tag-confirmed  { background: linear-gradient(135deg,#00b09b,#96c93d);color:white;padding:2px 10px;border-radius:20px;font-size:.78rem;font-weight:600; }
.tag-needs_review { background: linear-gradient(135deg,#f7971e,#ffd200);color:#1a1a2e;padding:2px 10px;border-radius:20px;font-size:.78rem;font-weight:600; }
.tag-rejected   { background: rgba(255,107,107,.25);color:#ff6b6b;padding:2px 10px;border-radius:20px;font-size:.78rem;font-weight:600; }
.tag-pending    { background: rgba(167,139,250,.25);color:#a78bfa;padding:2px 10px;border-radius:20px;font-size:.78rem;font-weight:600; }

/* Income / expense tags */
.tag-income  { background: linear-gradient(135deg,#00b09b,#96c93d);color:white;padding:2px 10px;border-radius:20px;font-size:.78rem;font-weight:600; }
.tag-expense { background: linear-gradient(135deg,#f7971e,#ffd200);color:#1a1a2e;padding:2px 10px;border-radius:20px;font-size:.78rem;font-weight:600; }

/* Section headers */
h2, h3 { color: #a78bfa !important; }

/* Text input / file upload */
.stTextArea textarea, .stTextInput input {
    background: rgba(255,255,255,0.85) !important;
    border: 1px solid rgba(167,139,250,0.3) !important;
    border-radius: 8px !important;
    color: #000000 !important;
}
.stTextArea textarea:focus, .stTextInput input:focus {
    border-color: #a78bfa !important;
    box-shadow: 0 0 0 2px rgba(167,139,250,0.2) !important;
}

/* Primary button */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #a78bfa, #7c3aed);
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 28px;
    font-weight: 600;
    transition: all 0.2s ease;
}
.stButton > button[kind="primary"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 20px rgba(124,58,237,0.4);
}

/* Insight cards */
.insight-card {
    background: rgba(167,139,250,0.08);
    border: 1px solid rgba(167,139,250,0.2);
    border-left: 4px solid #a78bfa;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 10px;
    line-height: 1.5;
}

/* Dataframe */
[data-testid="stDataFrame"] {
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,0.08);
}

/* Divider */
hr { border-color: rgba(255,255,255,0.1) !important; }

/* Info / success / error boxes */
.stSuccess { background: rgba(0,176,155,0.15) !important; border-left: 4px solid #00b09b !important; }
.stError   { background: rgba(255,107,107,0.15) !important; border-left: 4px solid #ff6b6b !important; }
.stWarning { background: rgba(247,151,30,0.15) !important; border-left: 4px solid #f7971e !important; }
.stInfo    { background: rgba(167,139,250,0.15) !important; border-left: 4px solid #a78bfa !important; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# API helpers
# ─────────────────────────────────────────────

def api_post_text(raw_input: str) -> dict:
    r = requests.post(f"{API_BASE}/transactions", json={"raw_input": raw_input}, timeout=30)
    r.raise_for_status()
    return r.json()


def api_post_audio(file_bytes: bytes, filename: str) -> dict:
    r = requests.post(
        f"{API_BASE}/transactions/audio",
        files={"audio": (filename, file_bytes)},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def api_get_transactions(
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    exclude_rejected: bool = True,
) -> list[dict]:
    params: dict = {}
    if date_from:
        params["date_from"] = date_from.isoformat()
    if date_to:
        params["date_to"] = date_to.isoformat()
    r = requests.get(f"{API_BASE}/transactions", params=params, timeout=15)
    r.raise_for_status()
    rows = r.json()
    if exclude_rejected:
        rows = [t for t in rows if t.get("status") != "rejected"]
    return rows


def api_get_summary(date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> dict:
    params: dict = {}
    if date_from:
        params["date_from"] = date_from.isoformat()
    if date_to:
        params["date_to"] = date_to.isoformat()
    r = requests.get(f"{API_BASE}/summary", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def api_patch_transaction(tx_id: int, payload: dict) -> dict:
    r = requests.patch(f"{API_BASE}/transactions/{tx_id}", json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


def api_delete_transaction(tx_id: int) -> dict:
    r = requests.delete(f"{API_BASE}/transactions/{tx_id}", timeout=15)
    r.raise_for_status()
    return r.json()


def check_api_health() -> bool:
    try:
        r = requests.get(f"{API_BASE}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


# ─────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📒 Bookkeeping Copilot")
    st.markdown("---")

    api_ok = check_api_health()
    if api_ok:
        st.success("✅  API connected", icon=None)
    else:
        st.error(f"❌  API unreachable at `{API_BASE}`\n\nRun: `uvicorn backend.main:app --reload`")

    st.markdown("---")
    st.markdown("### 📅 Date Filter")
    use_date_filter = st.checkbox("Filter by date range", value=False)
    if use_date_filter:
        date_from = st.date_input("From", datetime.now() - timedelta(days=7))
        date_to = st.date_input("To", datetime.now())
        dt_from = datetime.combine(date_from, datetime.min.time())
        dt_to = datetime.combine(date_to, datetime.max.time())
    else:
        dt_from = None
        dt_to = None

    st.markdown("---")
    show_rejected = st.checkbox("Show rejected transactions", value=False)

    st.markdown("---")
    st.markdown(
        "<small style='color: #666; font-size:0.75rem;'>"
        "Powered by Groq + LangGraph + FastAPI"
        "</small>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────

st.markdown(
    """
    <div style='text-align:center; padding: 2rem 0 1rem;'>
        <h1 style='font-size: 2.4rem; font-weight: 700;
                   background: linear-gradient(135deg, #a78bfa, #7c3aed, #4f46e5);
                   -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                   margin-bottom: 0.3rem;'>
            🎙️ Voice-First Bookkeeping Copilot
        </h1>
        <p style='color: #888; font-size: 1rem; margin-top: 0;'>
            Speak or type your business transactions — AI handles the rest.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# P&L Summary Metrics
# ─────────────────────────────────────────────

st.markdown("### 📊 P&L Overview")

try:
    summary = api_get_summary(dt_from, dt_to)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("💰 Total Income", f"₹{summary['total_income']:,.0f}")
    with c2:
        st.metric("🧾 Total Expenses", f"₹{summary['total_expenses']:,.0f}")
    with c3:
        net = summary["net_pnl"]
        st.metric(
            "📈 Net P&L",
            f"₹{net:,.0f}",
            delta=f"{'Profit' if net >= 0 else 'Loss'}",
            delta_color="normal" if net >= 0 else "inverse",
        )
    with c4:
        nr = summary["needs_review_count"]
        st.metric(
            "⚠️ Needs Review",
            str(nr),
            delta="action required" if nr > 0 else "all clear",
            delta_color="inverse" if nr > 0 else "normal",
        )
except Exception as e:
    if not api_ok:
        st.info("Start the backend API to see metrics.", icon="ℹ️")
    else:
        st.error(f"Could not load summary: {e}")

st.markdown("---")

# ─────────────────────────────────────────────
# Log a Transaction
# ─────────────────────────────────────────────

left, right = st.columns([1, 1], gap="large")

with left:
    st.markdown("### ✍️ Log via Text")
    text_input = st.text_area(
        "Type your bookkeeping note",
        placeholder="e.g. sold 5 jars today 200 each\nor: paid 300 for packaging material",
        height=120,
        key="text_input_area",
        label_visibility="collapsed",
    )
    if st.button("📨 Log Transaction", type="primary", key="btn_text", use_container_width=True):
        if not text_input.strip():
            st.warning("Please enter a transaction note.")
        elif not api_ok:
            st.error("API is not reachable. Please start the backend.")
        else:
            with st.spinner("Parsing & saving…"):
                try:
                    result = api_post_text(text_input.strip())
                    if result.get("needs_review"):
                        st.warning(
                            f"⚠️ Saved (flagged for review)\n\n"
                            f"**Reason:** {result.get('review_reason', 'Low confidence')}"
                        )
                    else:
                        desc = f" — *{result['description']}*" if result.get("description") else ""
                        st.success(
                            f"✅ Saved!  **{result['type'].upper()}** — "
                            f"₹{result['amount']:,.0f}  ({result['category']}){desc}"
                        )
                    st.rerun()
                except requests.HTTPError as e:
                    st.error(f"API error: {e.response.text}")
                except Exception as e:
                    st.error(f"Unexpected error: {e}")

with right:
    st.markdown("### 🎙️ Log via Voice Note")
    audio_file = st.file_uploader(
        "Upload audio (mp3, wav, m4a, webm)",
        type=["mp3", "wav", "m4a", "webm", "ogg"],
        key="audio_uploader",
        label_visibility="collapsed",
    )
    if audio_file is not None:
        st.audio(audio_file, format=f"audio/{audio_file.name.split('.')[-1]}")
        if st.button("🚀 Transcribe & Log", type="primary", key="btn_audio", use_container_width=True):
            if not api_ok:
                st.error("API is not reachable. Please start the backend.")
            else:
                with st.spinner("Transcribing & parsing…"):
                    try:
                        result = api_post_audio(audio_file.read(), audio_file.name)
                        st.info(f"📝 Transcribed: *{result.get('raw_input', '')}*")
                        if result.get("needs_review"):
                            st.warning(
                                f"⚠️ Saved (flagged for review)\n\n"
                                f"**Reason:** {result.get('review_reason', 'Low confidence')}"
                            )
                        else:
                            st.success(
                                f"✅ Saved!  **{result['type'].upper()}** — "
                                f"₹{result['amount']:,.0f}  ({result['category']})"
                            )
                        st.rerun()
                    except requests.HTTPError as e:
                        st.error(f"API error: {e.response.text}")
                    except Exception as e:
                        st.error(f"Unexpected error: {e}")

st.markdown("---")

# ─────────────────────────────────────────────
# ⚠️ Human-in-the-Loop: Review Queue
# ─────────────────────────────────────────────

try:
    all_transactions = api_get_transactions(dt_from, dt_to, exclude_rejected=False)
    review_items = [t for t in all_transactions if t.get("needs_review") and t.get("status") != "rejected"]

    if review_items:
        st.markdown(f"### ⚠️ Review Queue — {len(review_items)} item(s) need your attention")
        st.markdown(
            "<p style='color:#888; font-size:0.9rem; margin-top:-0.5rem;'>"
            "The AI was uncertain about these transactions. Review and confirm, edit, or reject each one."
            "</p>",
            unsafe_allow_html=True,
        )

        for item in review_items:
            tx_id = item["id"]
            label = f"[#{tx_id}]  \"{item['raw_input'][:70]}\""

            with st.expander(f"⚠️ {label}", expanded=True):
                # ── Current parse result ──────────────────────────────────
                col_info, col_actions = st.columns([1.6, 1])

                with col_info:
                    st.markdown(f"**Type:** `{item['type']}`")
                    st.markdown(f"**Category:** `{item['category']}`")
                    if item.get("description"):
                        st.markdown(f"**Description:** {item['description']}")
                    st.markdown(f"**Amount:** ₹{item['amount']:,.0f}")
                    if item.get("quantity"):
                        st.markdown(f"**Quantity:** {item['quantity']}")
                    if item.get("unit_price"):
                        st.markdown(f"**Unit Price:** ₹{item['unit_price']:,.0f}")
                    st.markdown(f"**Confidence:** {item['confidence']:.0%}")
                    st.markdown(
                        f"<div style='margin-top:8px; padding:8px 12px; "
                        f"background:rgba(255,107,107,0.1); border-left:3px solid #ff6b6b; "
                        f"border-radius:4px; font-size:0.85rem;'>"
                        f"🔍 {item.get('review_reason', 'Uncertain parse')}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                with col_actions:
                    st.markdown("**Actions**")

                    # ── Quick Confirm ──
                    if st.button(
                        "✅ Confirm as-is",
                        key=f"confirm_{tx_id}",
                        use_container_width=True,
                    ):
                        try:
                            api_patch_transaction(
                                tx_id,
                                {"status": "confirmed", "needs_review": False, "review_reason": None},
                            )
                            st.success("Confirmed!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")

                    # ── Reject ──
                    if st.button(
                        "🗑️ Reject",
                        key=f"reject_{tx_id}",
                        use_container_width=True,
                    ):
                        try:
                            api_delete_transaction(tx_id)
                            st.info("Rejected and excluded from P&L.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")

                # ── Edit form ────────────────────────────────────────────
                with st.expander("✏️ Edit and confirm", expanded=False):
                    CATEGORIES = ["sales", "raw_materials", "packaging", "transport", "other"]
                    TYPES = ["income", "expense"]

                    e_type = st.selectbox(
                        "Type",
                        TYPES,
                        index=TYPES.index(item["type"]) if item["type"] in TYPES else 0,
                        key=f"edit_type_{tx_id}",
                    )
                    e_cat = st.selectbox(
                        "Category",
                        CATEGORIES,
                        index=CATEGORIES.index(item["category"]) if item["category"] in CATEGORIES else 0,
                        key=f"edit_cat_{tx_id}",
                    )
                    e_desc = st.text_input(
                        "Description",
                        value=item.get("description") or "",
                        key=f"edit_desc_{tx_id}",
                    )
                    e_amount = st.number_input(
                        "Amount (₹)",
                        value=float(item["amount"]),
                        min_value=0.0,
                        step=1.0,
                        key=f"edit_amount_{tx_id}",
                    )
                    e_qty = st.number_input(
                        "Quantity (optional)",
                        value=int(item["quantity"]) if item.get("quantity") else 0,
                        min_value=0,
                        step=1,
                        key=f"edit_qty_{tx_id}",
                    )
                    e_price = st.number_input(
                        "Unit Price (₹, optional)",
                        value=float(item["unit_price"]) if item.get("unit_price") else 0.0,
                        min_value=0.0,
                        step=1.0,
                        key=f"edit_price_{tx_id}",
                    )

                    if st.button("💾 Save Edits & Confirm", key=f"save_{tx_id}", type="primary"):
                        try:
                            payload = {
                                "type": e_type,
                                "category": e_cat,
                                "description": e_desc or None,
                                "amount": e_amount,
                                "quantity": int(e_qty) if e_qty > 0 else None,
                                "unit_price": float(e_price) if e_price > 0 else None,
                                "status": "confirmed",
                                "needs_review": False,
                                "review_reason": None,
                            }
                            api_patch_transaction(tx_id, payload)
                            st.success("Saved and confirmed!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error saving: {e}")

        st.markdown("---")

except Exception as e:
    if api_ok:
        st.error(f"Could not load review queue: {e}")


# ─────────────────────────────────────────────
# Charts
# ─────────────────────────────────────────────

try:
    transactions = api_get_transactions(dt_from, dt_to, exclude_rejected=not show_rejected)

    if transactions:
        df = pd.DataFrame(transactions)
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        chart_col1, chart_col2 = st.columns(2)

        # ── P&L Time-Series ──
        with chart_col1:
            st.markdown("### 📈 P&L Over Time")
            df_ts = df.copy()
            df_ts["date"] = df_ts["timestamp"].dt.date
            daily = df_ts.groupby(["date", "type"])["amount"].sum().reset_index()

            income_daily = daily[daily["type"] == "income"].rename(columns={"amount": "Income"})
            expense_daily = daily[daily["type"] == "expense"].rename(columns={"amount": "Expenses"})
            merged = pd.merge(
                income_daily[["date", "Income"]],
                expense_daily[["date", "Expenses"]],
                on="date",
                how="outer",
            ).fillna(0).sort_values("date")
            merged["Profit"] = merged["Income"] - merged["Expenses"]

            if len(merged) > 0:
                fig_ts = go.Figure()
                fig_ts.add_trace(go.Scatter(
                    x=merged["date"], y=merged["Income"],
                    name="Income", line=dict(color="#00b09b", width=2),
                    fill="tozeroy", fillcolor="rgba(0,176,155,0.1)"
                ))
                fig_ts.add_trace(go.Scatter(
                    x=merged["date"], y=merged["Expenses"],
                    name="Expenses", line=dict(color="#f7971e", width=2),
                    fill="tozeroy", fillcolor="rgba(247,151,30,0.1)"
                ))
                fig_ts.add_trace(go.Scatter(
                    x=merged["date"], y=merged["Profit"],
                    name="Profit", line=dict(color="#a78bfa", width=2, dash="dot"),
                ))
                fig_ts.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(255,255,255,0.02)",
                    font=dict(family="Inter", color="#e8eaf6"),
                    legend=dict(bgcolor="rgba(0,0,0,0)"),
                    margin=dict(l=0, r=0, t=20, b=20),
                    height=280,
                    xaxis=dict(showgrid=False),
                    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
                )
                st.plotly_chart(fig_ts, use_container_width=True)
            else:
                st.info("Log more transactions to see the time-series chart.")

        # ── Expenses by Category ──
        with chart_col2:
            summary_data = api_get_summary(dt_from, dt_to)
            by_cat = summary_data.get("expenses_by_category", {})
            if by_cat:
                st.markdown("### 🧾 Expenses by Category")
                df_cat = pd.DataFrame(
                    list(by_cat.items()), columns=["Category", "Amount"]
                ).sort_values("Amount", ascending=True)

                fig_cat = px.bar(
                    df_cat, x="Amount", y="Category", orientation="h",
                    color="Amount",
                    color_continuous_scale=["#4f46e5", "#a78bfa", "#7c3aed"],
                    text="Amount",
                    template="plotly_dark",
                )
                fig_cat.update_traces(
                    texttemplate="₹%{text:,.0f}", textposition="outside"
                )
                fig_cat.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(255,255,255,0.03)",
                    font=dict(family="Inter", color="#e8eaf6"),
                    coloraxis_showscale=False,
                    margin=dict(l=0, r=60, t=20, b=20),
                    height=280,
                )
                st.plotly_chart(fig_cat, use_container_width=True)
            else:
                st.info("No expense data to chart yet.", icon="📊")

        st.markdown("---")

except Exception:
    pass


# ─────────────────────────────────────────────
# Transaction Ledger
# ─────────────────────────────────────────────

st.markdown("### 🗂️ Transaction Ledger")

try:
    transactions = api_get_transactions(dt_from, dt_to, exclude_rejected=not show_rejected)
    if not transactions:
        st.info("No transactions yet. Log your first one above!", icon="📭")
    else:
        df = pd.DataFrame(transactions)

        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%d %b %Y  %H:%M")
        df["amount_fmt"] = df["amount"].apply(lambda x: f"₹{x:,.0f}")
        df["confidence_fmt"] = df["confidence"].apply(lambda x: f"{x:.0%}")
        df["description"] = df.get("description", pd.Series([""] * len(df))).fillna("")

        display_cols = {
            "timestamp": "Date/Time",
            "type": "Type",
            "category": "Category",
            "description": "Description",
            "amount_fmt": "Amount",
            "confidence_fmt": "Confidence",
            "status": "Status",
            "raw_input": "Original Note",
        }
        df_display = df[
            [c for c in display_cols.keys() if c in df.columns]
        ].rename(columns=display_cols)

        def highlight_row(row):
            status_val = row.get("Status", "")
            if status_val == "needs_review":
                return ["background-color: rgba(247,151,30,0.10); border-left: 3px solid #f7971e"] * len(row)
            if status_val == "rejected":
                return ["background-color: rgba(255,107,107,0.06); opacity:0.6"] * len(row)
            if status_val == "confirmed":
                return ["background-color: rgba(0,176,155,0.05)"] * len(row)
            return [""] * len(row)

        styled = df_display.style.apply(highlight_row, axis=1)
        st.dataframe(styled, use_container_width=True, height=420)

except Exception as e:
    if not api_ok:
        st.info("Start the backend API to see your ledger.", icon="ℹ️")
    else:
        st.error(f"Could not load transactions: {e}")

st.markdown("---")

# ─────────────────────────────────────────────
# Business Insights (Phase 2 — optional)
# ─────────────────────────────────────────────

with st.expander("💡 Business Insights (AI-generated)", expanded=False):
    st.markdown(
        "<p style='color:#888; font-size:0.88rem;'>"
        "Insights are generated from your stored transaction history. "
        "The AI only references data it was given — it never invents financial facts."
        "</p>",
        unsafe_allow_html=True,
    )

    col_insight, col_btn = st.columns([3, 1])
    with col_btn:
        insight_days = st.selectbox("Period", [7, 14, 30, 90], index=2, key="insight_days")
        gen_btn = st.button("🔍 Generate Insights", key="btn_insights", type="primary")

    if gen_btn:
        if not api_ok:
            st.error("API is not reachable.")
        else:
            with st.spinner("Analysing your transaction history…"):
                try:
                    # Call insight endpoint directly (we'll add it to the API later)
                    # For now, import and call the agent from within the dashboard
                    import sys, os as _os
                    _os.chdir(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
                    sys.path.insert(0, _os.getcwd())
                    from backend.agents.insight_agent import generate_insights
                    insights = generate_insights(days=insight_days)
                    for insight in insights:
                        st.markdown(
                            f"<div class='insight-card'>💡 {insight}</div>",
                            unsafe_allow_html=True,
                        )
                except Exception as e:
                    st.error(f"Could not generate insights: {e}")
