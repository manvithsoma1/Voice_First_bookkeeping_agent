"""
dashboard/app.py — Phase 7: Streamlit front-end.

Features:
  • Text input to log a new transaction
  • Audio file upload for voice notes
  • Transaction table with ⚠ highlighting for needs_review rows
  • Weekly P&L metrics (income / expenses / net)
  • Expenses-by-category bar chart
  • Needs-review exception list
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

/* Income / expense tags */
.tag-income {
    background: linear-gradient(135deg, #00b09b, #96c93d);
    color: white;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
}
.tag-expense {
    background: linear-gradient(135deg, #f7971e, #ffd200);
    color: #1a1a2e;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
}

/* Section headers */
h2, h3 { color: #a78bfa !important; }

/* Text input / file upload */
.stTextArea textarea, .stTextInput input {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(167,139,250,0.3) !important;
    border-radius: 8px !important;
    color: #e8eaf6 !important;
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


def api_get_transactions(date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> list[dict]:
    params: dict = {}
    if date_from:
        params["date_from"] = date_from.isoformat()
    if date_to:
        params["date_to"] = date_to.isoformat()
    r = requests.get(f"{API_BASE}/transactions", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def api_get_summary(date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> dict:
    params: dict = {}
    if date_from:
        params["date_from"] = date_from.isoformat()
    if date_to:
        params["date_to"] = date_to.isoformat()
    r = requests.get(f"{API_BASE}/summary", params=params, timeout=15)
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

    # API status indicator
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
        st.metric(
            "💰 Total Income",
            f"₹{summary['total_income']:,.0f}",
            delta=None,
        )
    with c2:
        st.metric(
            "🧾 Total Expenses",
            f"₹{summary['total_expenses']:,.0f}",
            delta=None,
        )
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
                        st.success(
                            f"✅ Saved!  **{result['type'].upper()}** — "
                            f"₹{result['amount']:,.0f}  ({result['category']})"
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
# Expenses by Category Chart
# ─────────────────────────────────────────────

try:
    summary_data = api_get_summary(dt_from, dt_to)
    by_cat = summary_data.get("expenses_by_category", {})
    if by_cat:
        st.markdown("### 📊 Expenses by Category")
        df_cat = pd.DataFrame(
            list(by_cat.items()), columns=["Category", "Amount"]
        ).sort_values("Amount", ascending=True)

        fig = px.bar(
            df_cat,
            x="Amount",
            y="Category",
            orientation="h",
            color="Amount",
            color_continuous_scale=["#4f46e5", "#a78bfa", "#7c3aed"],
            text="Amount",
            template="plotly_dark",
        )
        fig.update_traces(
            texttemplate="₹%{text:,.0f}",
            textposition="outside",
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(255,255,255,0.03)",
            font=dict(family="Inter", color="#e8eaf6"),
            coloraxis_showscale=False,
            margin=dict(l=0, r=60, t=20, b=20),
            height=max(250, len(by_cat) * 55),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("---")
except Exception:
    pass   # silently skip chart if API unavailable


# ─────────────────────────────────────────────
# Transaction Table
# ─────────────────────────────────────────────

st.markdown("### 🗂️ Transaction Ledger")

try:
    transactions = api_get_transactions(dt_from, dt_to)
    if not transactions:
        st.info("No transactions yet. Log your first one above!", icon="📭")
    else:
        df = pd.DataFrame(transactions)

        # Format columns
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%d %b %Y  %H:%M")
        df["amount_fmt"] = df["amount"].apply(lambda x: f"₹{x:,.0f}")
        df["confidence_fmt"] = df["confidence"].apply(lambda x: f"{x:.0%}")

        # Build display dataframe
        display_cols = {
            "timestamp": "Date/Time",
            "type": "Type",
            "category": "Category",
            "amount_fmt": "Amount",
            "confidence_fmt": "Confidence",
            "needs_review": "⚠ Review",
            "raw_input": "Original Note",
        }
        df_display = df[[c for c in display_cols.keys() if c in df.columns]].rename(
            columns=display_cols
        )

        # Style: highlight needs_review rows in amber
        def highlight_review(row):
            if row.get("⚠ Review") is True:
                return ["background-color: rgba(247,151,30,0.12); border-left: 3px solid #f7971e"] * len(row)
            return [""] * len(row)

        styled = df_display.style.apply(highlight_review, axis=1)
        st.dataframe(styled, use_container_width=True, height=400)

        # Needs-review exception list
        review_df = df[df["needs_review"] == True]
        if not review_df.empty:
            st.markdown(f"#### ⚠️ Exception List — {len(review_df)} item(s) needing review")
            for _, row in review_df.iterrows():
                with st.expander(f"[{row['timestamp']}]  \"{row['raw_input'][:70]}\""):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**Type:** `{row['type']}`")
                        st.markdown(f"**Category:** `{row['category']}`")
                        st.markdown(f"**Amount:** ₹{row['amount']:,.0f}")
                    with col2:
                        st.markdown(f"**Confidence:** {row['confidence']:.0%}")
                        st.markdown(f"**Reason:** {row.get('review_reason', 'Unknown')}")

except Exception as e:
    if not api_ok:
        st.info("Start the backend API to see your ledger.", icon="ℹ️")
    else:
        st.error(f"Could not load transactions: {e}")
