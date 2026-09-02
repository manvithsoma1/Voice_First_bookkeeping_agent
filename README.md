# 🎙️ Voice-First Bookkeeping Copilot

AI-powered bookkeeping for small home businesses. Speak or type your transaction — the AI parses, validates, and logs it to your ledger automatically.

## Tech Stack

| Layer | Tech |
|---|---|
| LLM / STT | Groq (Llama 3.3 70B + Whisper Large V3 Turbo) |
| Orchestration | LangGraph |
| Backend API | FastAPI + Uvicorn |
| Database | SQLite (local) / Postgres (production) |
| Dashboard | Streamlit + Plotly |

## Quick Start

### 1. Get your Groq API key
Sign up at [console.groq.com](https://console.groq.com) — free, no card required.

### 2. Add your key to `.env`
```
GROQ_API_KEY=your_actual_key_here
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Start the backend API
```bash
uvicorn backend.main:app --reload
```
API docs: http://localhost:8000/docs

### 5. Start the dashboard (new terminal)
```bash
streamlit run dashboard/app.py
```
Dashboard: http://localhost:8501

## Running Tests

### Parser accuracy benchmark (40 test cases)
```bash
python -m tests.test_parsing_accuracy
```

## Project Structure

```
├── backend/
│   ├── main.py              # FastAPI endpoints
│   ├── graph.py             # LangGraph pipeline (parse → validate → save)
│   ├── models.py            # Pydantic + SQLAlchemy schemas
│   ├── db.py                # SQLite/Postgres engine
│   └── agents/
│       ├── parser_agent.py  # Groq LLM parser + Whisper transcription
│       ├── validator_agent.py
│       └── ledger_agent.py
├── dashboard/
│   └── app.py               # Streamlit UI
├── data/
│   └── seed_transactions.json
└── tests/
    └── test_parsing_accuracy.py
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/transactions` | Log a text transaction |
| POST | `/transactions/audio` | Upload audio → transcribe → log |
| GET | `/transactions` | List all transactions |
| GET | `/summary` | P&L summary + expenses by category |
| GET | `/health` | Health check |

## Deployment

- **Backend:** Render free tier or `ngrok` for demo tunnelling  
- **Dashboard:** Streamlit Community Cloud (free)  
- **Database:** Switch `DATABASE_URL` to Neon/Supabase Postgres before deploying
