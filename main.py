"""
main.py — FastAPI Application for NL2SQL Clinic Chatbot

Provides two custom endpoints:
  POST /chat   — accept a natural-language question, return SQL + results
  GET  /health — database connectivity and agent status check

The Vanna 2.0 Agent is used to generate SQL from natural language. If the
agent pipeline fails, a direct Gemini LLM fallback is used.
"""

import os
import re
import sqlite3
import logging
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# Constants

DB_PATH = "./clinic.db"

# Dangerous SQL keywords / patterns (case-insensitive)
DANGEROUS_PATTERNS: list[str] = [
    r"\bINSERT\b", r"\bUPDATE\b", r"\bDELETE\b", r"\bDROP\b", r"\bALTER\b",
    r"\bEXEC\b", r"\bGRANT\b", r"\bREVOKE\b", r"\bSHUTDOWN\b",
    r"\bxp_", r"\bsp_",
    r"\bsqlite_master\b", r"\bsqlite_temp_master\b",
]

SCHEMA_DESCRIPTION = """
SQLite database with these tables:

patients(id INTEGER PK, first_name TEXT, last_name TEXT, email TEXT, phone TEXT, date_of_birth DATE, gender TEXT ['M','F'], city TEXT, registered_date DATE)
doctors(id INTEGER PK, name TEXT, specialization TEXT ['Dermatology','Cardiology','Orthopedics','General','Pediatrics'], department TEXT, phone TEXT)
appointments(id INTEGER PK, patient_id INTEGER FK→patients.id, doctor_id INTEGER FK→doctors.id, appointment_date DATETIME, status TEXT ['Scheduled','Completed','Cancelled','No-Show'], notes TEXT)
treatments(id INTEGER PK, appointment_id INTEGER FK→appointments.id, treatment_name TEXT, cost REAL, duration_minutes INTEGER)
invoices(id INTEGER PK, patient_id INTEGER FK→patients.id, invoice_date DATE, total_amount REAL, paid_amount REAL, status TEXT ['Paid','Pending','Overdue'])
"""


# SQL validation

def validate_sql(query: str) -> tuple[bool, str]:
    """
    Validate that a SQL query is safe to execute.

    Rules:
      1. Must start with SELECT (after stripping whitespace / comments)
      2. Must not contain dangerous keywords

    Returns:
        (True, "")           if valid
        (False, reason_str)  if invalid
    """
    if not query or not query.strip():
        return False, "Empty query"

    # Strip leading whitespace and single-line comments
    cleaned = re.sub(r"--.*$", "", query, flags=re.MULTILINE).strip()

    # Must start with SELECT
    if not cleaned.upper().startswith("SELECT"):
        return False, "Query must start with SELECT"

    # Check for dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            keyword = pattern.replace(r"\b", "").replace("\\b", "")
            reason = f"Dangerous keyword detected: {keyword}"
            logger.warning("SQL validation rejected: %s — Query: %s", reason, query[:200])
            return False, reason

    return True, ""


# Direct SQL execution

def execute_sql(query: str) -> dict[str, Any]:
    """
    Execute a validated SQL query against clinic.db and return results.

    Returns dict with keys: columns, rows, row_count, error
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(query)
        rows_raw = cur.fetchall()

        columns = [desc[0] for desc in cur.description] if cur.description else []
        rows = [list(row) for row in rows_raw]
        conn.close()

        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "error": None,
        }
    except sqlite3.Error as exc:
        logger.error("SQL execution error: %s — Query: %s", exc, query[:200])
        return {
            "columns": [],
            "rows": [],
            "row_count": 0,
            "error": f"Database error: {exc}",
        }


# Gemini LLM fallback for SQL generation

async def generate_sql_via_gemini(question: str) -> str:
    """
    Generate SQL using the Gemini LLM directly via the google-genai SDK.
    Sends the schema + question to Gemini and parses out a SELECT query.
    Includes retry logic with exponential backoff for rate limit (429) errors.
    """
    import time as _time
    from google import genai
    from google.genai.errors import ClientError

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise EnvironmentError("GOOGLE_API_KEY not set")

    client = genai.Client(api_key=api_key)

    prompt = (
        f"You are a SQL expert. Given this SQLite schema:\n{SCHEMA_DESCRIPTION}\n\n"
        f"Generate ONLY a valid SQLite SELECT query (no explanation, no markdown fences, "
        f"no comments) for this question:\n{question}\n\n"
        f"Rules:\n"
        f"- ONLY output the raw SQL query, nothing else\n"
        f"- Use SQLite syntax (strftime for dates, etc.)\n"
        f"- Only SELECT queries allowed\n"
        f"- Do NOT wrap in markdown code fences\n"
    )

    max_retries = 3
    base_delay = 30  # seconds

    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            sql = response.text.strip()

            # Clean up any stray markdown code fences
            if sql.startswith("```"):
                sql = re.sub(r"```(?:sql)?\n?", "", sql)
                sql = sql.rstrip("`").strip()

            return sql

        except ClientError as exc:
            if exc.status_code in (429, 503) and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "API error %d. Retry %d/%d in %ds…",
                    exc.status_code, attempt + 1, max_retries, delay,
                )
                _time.sleep(delay)
            else:
                raise


# Agent-based SQL generation (Vanna 2.0)

async def generate_sql_via_agent(question: str) -> str | None:
    """
    Try to generate SQL using the Vanna 2.0 Agent pipeline.

    The agent returns an async generator of UiComponent objects. We iterate
    through them looking for SQL content in the rich/simple components.

    Returns the SQL string or None if extraction fails.
    """
    try:
        from vanna_setup import get_agent
        from vanna.core.user import RequestContext
        import traceback

        agent = get_agent()

        # Build a minimal RequestContext for the agent
        request_context = RequestContext(
            headers={"content-type": "application/json"},
            cookies={"vanna_email": "clinic@example.com"},
        )

        sql_query = None

        # send_message returns an async generator of UiComponent
        async for component in agent.send_message(request_context, question):
            # Try to extract SQL from the component
            comp_data = component.model_dump() if hasattr(component, "model_dump") else {}
            logger.debug("Agent component: %s", comp_data)

            # Check rich_component for SQL content
            rich = comp_data.get("rich_component")
            if rich and isinstance(rich, dict):
                # Look for SQL in code blocks or tool results
                content = rich.get("content", "")
                if isinstance(content, str) and content.strip().upper().startswith("SELECT"):
                    sql_query = content.strip()

                # Check for tool result with SQL
                tool_args = rich.get("tool_args", {})
                if isinstance(tool_args, dict) and "sql" in tool_args:
                    sql_query = tool_args["sql"]

                # Check nested data for SQL
                for key in ("sql", "query", "code"):
                    val = rich.get(key)
                    if isinstance(val, str) and val.strip().upper().startswith("SELECT"):
                        sql_query = val.strip()

            # Check simple_component
            simple = comp_data.get("simple_component")
            if simple and isinstance(simple, dict):
                text = simple.get("text", "")
                if isinstance(text, str) and text.strip().upper().startswith("SELECT"):
                    sql_query = text.strip()

        return sql_query

    except Exception as exc:
        import traceback
        logger.warning("Agent-based SQL generation failed: %s\n%s", exc, traceback.format_exc())
        return None


# Pydantic models

class ChatRequest(BaseModel):
    """Request body for the /chat endpoint."""
    question: str = Field(..., min_length=1, max_length=500, description="Natural-language question")


class ChatResponse(BaseModel):
    """Response body for the /chat endpoint."""
    message: str = ""
    sql_query: str | None = None
    columns: list[str] = []
    rows: list[list[Any]] = []
    row_count: int = 0
    chart: dict | None = None
    chart_type: str | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Response body for the /health endpoint."""
    status: str = "ok"
    database: str = "connected"
    agent_memory_items: int = 0


# FastAPI app

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("NL2SQL Clinic Chatbot starting up…")
    # Eagerly initialise the agent so errors surface immediately
    try:
        from vanna_setup import get_agent
        get_agent()
        logger.info("Vanna agent ready")
        
        # Seed memory on startup so the in-memory agent has few-shot examples
        try:
            from seed_memory import seed_memory
            count = await seed_memory()
            logger.info("Seeded %d Q&A pairs into DemoAgentMemory", count)
        except Exception as seed_exc:
            logger.error("Memory seeding failed: %s", seed_exc)
            
    except Exception as exc:
        logger.error("Agent init failed (will use Gemini fallback): %s", exc)
    yield
    logger.info("Shutting down…")


app = FastAPI(
    title="NL2SQL Clinic Chatbot",
    description="Ask natural-language questions about the clinic database",
    version="1.0.0",
    lifespan=lifespan,
)


# Endpoints

@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check database connectivity and agent status."""
    # Database check
    db_status = "connected"
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("SELECT 1")
        conn.close()
    except Exception:
        db_status = "error"

    # Memory count
    mem_count = 0
    try:
        from vanna_setup import get_agent_memory
        memory = get_agent_memory()
        # Access internal storage — DemoAgentMemory uses _items or similar
        for attr in ("_items", "_tool_usages", "items", "_memory"):
            storage = getattr(memory, attr, None)
            if storage is not None and hasattr(storage, "__len__"):
                mem_count = len(storage)
                break
    except Exception:
        pass

    return HealthResponse(
        status="ok" if db_status == "connected" else "degraded",
        database=db_status,
        agent_memory_items=mem_count,
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """
    Accept a natural-language question, generate SQL via the Vanna agent
    (or fallback to direct Gemini), validate and execute it, then return
    structured results.
    """
    question = req.question.strip()

    # Input validation
    if len(question) < 5:
        return ChatResponse(
            error="Please enter a valid question (5–500 characters).",
            message="Question too short.",
        )
    if len(question) > 500:
        return ChatResponse(
            error="Please enter a valid question (5–500 characters).",
            message="Question too long.",
        )

    # Generate SQL
    sql_query = None

    # Use direct Gemini LLM call (the Vanna agent also uses Gemini internally,
    # so skipping it halves API usage — critical for free-tier rate limits).
    try:
        sql_query = await generate_sql_via_gemini(question)
        logger.info("SQL generated: %s", sql_query[:200])
    except Exception as exc:
        import traceback
        logger.error("Gemini SQL generation failed: %s\n%s", exc, traceback.format_exc())
        return ChatResponse(
            error="The AI service is temporarily unavailable. Please try again.",
            message="SQL generation failed.",
        )

    if not sql_query:
        return ChatResponse(
            message="I couldn't generate a query for your question. Please try rephrasing.",
            error="No SQL generated.",
        )

    # Validate SQL
    is_valid, reason = validate_sql(sql_query)
    if not is_valid:
        logger.warning("SQL rejected: %s — SQL: %s", reason, sql_query[:200])
        return ChatResponse(
            sql_query=sql_query,
            error=f"That query type isn't allowed for security reasons: {reason}",
            message="SQL validation failed.",
        )

    # Execute SQL
    result = execute_sql(sql_query)

    if result["error"]:
        return ChatResponse(
            sql_query=sql_query,
            error=f"The query ran into a database error: {result['error']}",
            message="Query execution failed.",
        )

    if result["row_count"] == 0:
        return ChatResponse(
            sql_query=sql_query,
            columns=result["columns"],
            rows=[],
            row_count=0,
            message="No data found matching your question.",
        )

    return ChatResponse(
        message=f"Found {result['row_count']} result(s).",
        sql_query=sql_query,
        columns=result["columns"],
        rows=result["rows"],
        row_count=result["row_count"],
        chart=None,
        chart_type=None,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
