# NL2SQL Clinic Management Chatbot

> Natural-language → SQL → Answers for a clinic management database, powered by **Vanna AI 2.0** + **Google Gemini** + **FastAPI**.

---

## Quick Start

```bash
# 1. Clone & enter the project
cd NL2SQL

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
copy .env.example .env
# Edit .env → paste your GOOGLE_API_KEY

# 5. Create & populate the database
python setup_database.py

# 6. Seed agent memory with example Q&A pairs
python seed_memory.py

# 7. Start the server
python main.py
# → Server runs at http://localhost:8000
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Server (:8000)                   │
│                                                             │
│  POST /chat ──► Vanna Agent ──► Gemini LLM (gemini-2.5-flash)
│       │              │                                      │
│       │              ├── RunSqlTool ──► SQLite (clinic.db)  │
│       │              ├── VisualizeDataTool (Plotly charts)   │
│       │              └── Memory Tools (DemoAgentMemory)      │
│       │                                                     │
│       ▼                                                     │
│  SQL Validation ──► Execute ──► JSON Response               │
│                                                             │
│  GET /health ──► DB + Agent status check                    │
└─────────────────────────────────────────────────────────────┘
```

### Components

| File | Purpose |
|---|---|
| `setup_database.py` | Creates `clinic.db` with 5 tables and realistic dummy data |
| `vanna_setup.py` | Configures Vanna 2.0 Agent (Gemini LLM, tools, memory) |
| `seed_memory.py` | Pre-seeds 15 Q&A pairs for better SQL generation |
| `main.py` | FastAPI app with `/chat` and `/health` endpoints |

### Database Schema

| Table | Key Columns | Rows |
|---|---|---|
| `patients` | id, first_name, last_name, email, phone, gender, city | 200 |
| `doctors` | id, name, specialization, department | 15 |
| `appointments` | id, patient_id, doctor_id, appointment_date, status | 500 |
| `treatments` | id, appointment_id, treatment_name, cost, duration_minutes | 350 |
| `invoices` | id, patient_id, invoice_date, total_amount, paid_amount, status | 300 |

---

## API Reference

### `POST /chat`

Ask a natural-language question about the clinic database.

**Request:**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "How many patients do we have?"}'
```

**Response:**
```json
{
  "message": "Found 1 result(s).",
  "sql_query": "SELECT COUNT(*) AS total_patients FROM patients",
  "columns": ["total_patients"],
  "rows": [[200]],
  "row_count": 1,
  "chart": null,
  "chart_type": null,
  "error": null
}
```

### `GET /health`

Check system status.

```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "ok",
  "database": "connected",
  "agent_memory_items": 15
}
```

---

## LLM Provider

| Setting | Value |
|---|---|
| Provider | Google Gemini |
| Model | `gemini-2.5-flash` |
| API Key Env Var | `GOOGLE_API_KEY` |
| Get a key | [Google AI Studio](https://aistudio.google.com/apikey) |

---

## Security

- **SQL Validation** — All AI-generated SQL is validated before execution. Only `SELECT` queries are allowed. Dangerous keywords (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `EXEC`, etc.) are blocked.
- **No Hardcoded Keys** — API keys are loaded from `.env` via `python-dotenv`.
- **Error Isolation** — Business logic errors return HTTP 200 with an `error` field; stack traces are never exposed.

---

## Example Questions

```
How many patients do we have?
List all doctors and their specializations
Which doctor has the most appointments?
What is the total revenue?
Show revenue by doctor
Top 5 patients by spending
Average treatment cost by specialization
Show monthly appointment count for the past 6 months
Which city has the most patients?
Show unpaid invoices
```

---

## Project Structure

```
NL2SQL/
├── .env.example          # Environment variable template
├── .env                  # Your actual API key (git-ignored)
├── requirements.txt      # Python dependencies
├── setup_database.py     # DB schema + dummy data
├── vanna_setup.py        # Vanna 2.0 Agent configuration
├── seed_memory.py        # Pre-seed agent memory
├── main.py               # FastAPI application
├── clinic.db             # SQLite database (auto-generated)
├── README.md             # This file
└── RESULTS.md            # Test results (20 questions)
```
