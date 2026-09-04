# 🎙️ Voice-First Bookkeeping Copilot

> **"Describe what happened. We handle the bookkeeping — and tell you when we're not sure."**

An AI-powered bookkeeping assistant for small and home-based businesses. Speak or type what happened; the system converts it into structured bookkeeping data, validates it, asks for human review when uncertain, saves confirmed transactions, and shows live profit-and-loss information.

---

## Architecture

```
       SPEAK / TYPE
             ↓
    Speech-to-Text (Groq Whisper)
             ↓
       PARSER AGENT  (Groq LLaMA 3.3 70B)
       Natural Language → Structured Transaction
             ↓
       VALIDATION LAYER
       LLM confidence + Python deterministic math
             ↓
           DECISION
          /        \
    CONFIDENT    UNCERTAIN
        ↓              ↓
   Confirmation   Review Queue
        |         Confirm/Edit/Reject
        └────┬────┘
             ↓
       LEDGER AGENT
       Save to SQLite / PostgreSQL
             ↓
       FASTAPI BACKEND
             ↓
       STREAMLIT DASHBOARD
       P&L + Charts + Insights
```

**LangGraph** orchestrates the `parse → validate → save` pipeline as a stateful graph.

---

## Core Design Principle: Trust

> The system must not silently guess important financial information.

When information is missing or ambiguous:

```
User: "Bought some bottles today."

System:
⚠️ NEEDS REVIEW
  Expense detected
  Category: Packaging
  Item: Bottles
  Amount: MISSING — please enter the amount.
```

The human-in-the-loop review queue in the dashboard lets you **Confirm**, **Edit**, or **Reject** every flagged transaction.

---

## Technology Stack

| Component | Technology |
|---|---|
| LLM | Groq API — LLaMA 3.3 70B |
| Speech-to-Text | Groq Whisper Large V3 Turbo |
| Agent orchestration | LangGraph |
| Backend | FastAPI |
| Data validation | Pydantic v2 |
| Database (dev) | SQLite |
| Database (prod) | PostgreSQL |
| ORM | SQLAlchemy 2.0 |
| Dashboard | Streamlit |

---

## Quick Start

### 1. Clone and install

```bash
git clone <your-repo-url>
cd voice-bookkeeping-copilot

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Set up environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```env
GROQ_API_KEY=your_groq_api_key_here   # Get free key at console.groq.com
DATABASE_URL=sqlite:///./bookkeeping.db
API_BASE_URL=http://localhost:8000
```

### 3. Start the backend

```bash
uvicorn backend.main:app --reload
```

API docs available at: http://localhost:8000/docs

### 4. Start the dashboard

```bash
streamlit run dashboard/app.py
```

Dashboard at: http://localhost:8501

---

## Project Structure

```
voice-bookkeeping-copilot/
│
├── backend/
│   ├── main.py              # FastAPI app + endpoints
│   ├── graph.py             # LangGraph orchestration
│   ├── db.py                # SQLAlchemy engine + session factory
│   ├── models.py            # Pydantic + ORM schemas
│   │
│   ├── agents/
│   │   ├── parser_agent.py  # LLM: natural language → structured JSON
│   │   ├── validator_agent.py   # Rule-based honesty layer
│   │   ├── ledger_agent.py  # DB persistence
│   │   └── insight_agent.py # Phase 2: business insights
│   │
│   └── services/
│       ├── calculations.py  # Deterministic financial math
│       ├── categories.py    # Shared constants (types, categories, statuses)
│       └── transcription.py # Whisper STT wrapper
│
├── dashboard/
│   └── app.py               # Streamlit UI
│
├── data/
│   ├── seed_transactions.json   # 60 labelled accuracy test cases
│   └── test_cases.json          # Structured test table
│
├── tests/
│   ├── test_validator.py    # Validator unit tests (no LLM)
│   ├── test_calculations.py # Math helper unit tests
│   ├── test_pipeline.py     # Pipeline integration tests (mocked LLM)
│   └── test_parsing_accuracy.py  # Full LLM accuracy benchmark
│
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Transaction Schema

Every transaction stores:

| Field | Type | Description |
|---|---|---|
| `id` | int | Auto-assigned primary key |
| `timestamp` | datetime | UTC time of logging |
| `raw_input` | text | Original user sentence (audit trail) |
| `type` | enum | `income` \| `expense` |
| `category` | enum | `sales` \| `raw_materials` \| `packaging` \| `transport` \| `other` |
| `description` | text | Short item description (e.g., "mango pickle jars") |
| `amount` | float | Total transaction amount |
| `quantity` | int | Number of units (if mentioned) |
| `unit_price` | float | Price per unit (if mentioned) |
| `confidence` | float | Parser confidence 0.0–1.0 |
| `needs_review` | bool | True if flagged for human review |
| `review_reason` | text | Why review was flagged |
| `status` | enum | `pending` \| `confirmed` \| `needs_review` \| `rejected` |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/transactions` | Log a text transaction |
| `POST` | `/transactions/audio` | Upload audio → transcribe → log |
| `GET` | `/transactions` | List all transactions |
| `PATCH` | `/transactions/{id}` | Update / resolve a review item |
| `DELETE` | `/transactions/{id}` | Soft-reject a transaction |
| `GET` | `/summary` | P&L summary + category breakdown |
| `GET` | `/health` | Liveness check |

Interactive API docs: http://localhost:8000/docs

---

## Running Tests

```bash
# Fast deterministic tests — no LLM calls, no DB setup required (~1 second)
python -m pytest tests/test_validator.py tests/test_calculations.py -v

# Integration tests — mocked LLM, isolated in-memory DB (~3 seconds)
python -m pytest tests/test_pipeline.py -v

# Full LLM accuracy benchmark — calls Groq API, ~60 test cases (~2–3 minutes)
python -m tests.test_parsing_accuracy
```

---

## Dashboard Features

| Section | What it shows |
|---|---|
| P&L Overview | Revenue, Expenses, Net Profit, Review count |
| Log via Text | Free-text input box |
| Log via Voice | Audio file upload + transcription |
| **Review Queue** | ⚠️ Flagged items with Confirm / Edit / Reject |
| P&L Over Time | Line chart: income vs expenses by date |
| Expenses by Category | Horizontal bar chart |
| Transaction Ledger | Full table with status + description |
| Business Insights | AI-generated observations from stored data |

---

## Demo Script (Section 27)

### Demo 1 — Normal sale
> "Sold five mango pickle jars today, two hundred each."

Expected result: `✅ Income · Sales · ₹1,000 · Confirmed`

### Demo 2 — Expense
> "Paid 300 for bottles."

Expected result: `✅ Expense · Packaging · ₹300 · Confirmed`

### Demo 3 — Uncertainty (the trust feature)
> "Bought some bottles today."

Expected result: `⚠️ Needs Review — Amount missing`

### Demo 4 — Voice input
Upload a `.wav` / `.mp3` file with any of the above sentences.

---

## Security

- API keys stored in `.env` (never committed to git)
- `.env` is in `.gitignore`
- Raw inputs always preserved for audit trail
- Rejected transactions soft-deleted (kept in DB, excluded from P&L)
- All financial arithmetic done in Python, not trusted to LLM

---

## Deployment

### PostgreSQL (production)

```env
DATABASE_URL=postgresql://user:password@host:5432/bookkeeping
```

### Streamlit Cloud

Deploy `dashboard/app.py` from the Streamlit Cloud UI.
Set `API_BASE_URL` in Streamlit secrets to point to your deployed backend.

---

## Build Roadmap

| Phase | Status |
|---|---|
| 1. Database + Models | ✅ Complete |
| 2. Parser Agent | ✅ Complete |
| 3. Deterministic Calculations | ✅ Complete |
| 4. Validator Agent | ✅ Complete |
| 5. LangGraph Pipeline | ✅ Complete |
| 6. FastAPI Backend | ✅ Complete |
| 7. Streamlit Dashboard | ✅ Complete |
| 8. Voice (Whisper) | ✅ Complete |
| 9. Human-in-the-Loop Review | ✅ Complete |
| 10. Accuracy Testing (60 cases) | ✅ Complete |
| 11. Business Insights | ✅ Complete |
| 12. Deployment | 🔲 Optional |

---

*Built with Groq · LangGraph · FastAPI · Streamlit*
