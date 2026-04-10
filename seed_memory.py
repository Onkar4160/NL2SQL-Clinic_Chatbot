"""
seed_memory.py — Pre-seed Agent Memory with Example Q&A Pairs

Populates DemoAgentMemory with 15+ curated question → SQL pairs so the
Vanna agent can use them as few-shot examples for better SQL generation.

Uses ``DemoAgentMemory.save_tool_usage()`` with a minimal ``ToolContext``
to store each question → SQL mapping as a RunSqlTool example.

Categories covered:
  - Patient queries (3)
  - Doctor queries (3)
  - Appointment queries (3)
  - Financial queries (3)
  - Time-based / trend queries (3)
"""

import asyncio
import logging

from vanna.core.tool import ToolContext
from vanna.core.user import User

from vanna_setup import get_agent_memory

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

# Question → SQL pairs organised by category

SEED_PAIRS: list[dict[str, str]] = [
    # Patient Queries
    {
        "question": "How many patients do we have?",
        "sql": "SELECT COUNT(*) AS total_patients FROM patients",
    },
    {
        "question": "List all patients from Mumbai",
        "sql": "SELECT * FROM patients WHERE city = 'Mumbai'",
    },
    {
        "question": "How many male vs female patients?",
        "sql": "SELECT gender, COUNT(*) AS count FROM patients GROUP BY gender",
    },

    # Doctor Queries
    {
        "question": "List all doctors and their specializations",
        "sql": "SELECT name, specialization FROM doctors",
    },
    {
        "question": "Which doctor has the most appointments?",
        "sql": (
            "SELECT d.name, COUNT(a.id) AS appt_count "
            "FROM doctors d JOIN appointments a ON d.id = a.doctor_id "
            "GROUP BY d.name ORDER BY appt_count DESC LIMIT 1"
        ),
    },
    {
        "question": "Show all cardiologists",
        "sql": "SELECT * FROM doctors WHERE specialization = 'Cardiology'",
    },

    # Appointment Queries
    {
        "question": "Show me appointments for last month",
        "sql": "SELECT * FROM appointments WHERE appointment_date >= date('now', '-1 month')",
    },
    {
        "question": "How many cancelled appointments?",
        "sql": "SELECT COUNT(*) FROM appointments WHERE status = 'Cancelled'",
    },
    {
        "question": "What percentage of appointments are no-shows?",
        "sql": (
            "SELECT ROUND(COUNT(CASE WHEN status='No-Show' THEN 1 END)*100.0/COUNT(*), 2) "
            "AS no_show_pct FROM appointments"
        ),
    },

    # Financial Queries
    {
        "question": "What is the total revenue?",
        "sql": "SELECT SUM(total_amount) AS total_revenue FROM invoices WHERE status = 'Paid'",
    },
    {
        "question": "Show unpaid invoices",
        "sql": "SELECT * FROM invoices WHERE status != 'Paid' ORDER BY invoice_date DESC",
    },
    {
        "question": "Show revenue by doctor",
        "sql": (
            "SELECT d.name, SUM(i.total_amount) AS revenue "
            "FROM doctors d "
            "JOIN appointments a ON d.id = a.doctor_id "
            "JOIN invoices i ON i.patient_id = a.patient_id "
            "GROUP BY d.name ORDER BY revenue DESC"
        ),
    },

    # Time-Based / Trend Queries
    {
        "question": "Show monthly appointment count for past 6 months",
        "sql": (
            "SELECT strftime('%Y-%m', appointment_date) AS month, COUNT(*) AS count "
            "FROM appointments WHERE appointment_date >= date('now', '-6 months') "
            "GROUP BY month ORDER BY month"
        ),
    },
    {
        "question": "Show patient registration trend by month",
        "sql": (
            "SELECT strftime('%Y-%m', registered_date) AS month, COUNT(*) AS new_patients "
            "FROM patients GROUP BY month ORDER BY month"
        ),
    },
    {
        "question": "Revenue trend by month",
        "sql": (
            "SELECT strftime('%Y-%m', invoice_date) AS month, SUM(total_amount) AS revenue "
            "FROM invoices GROUP BY month ORDER BY month"
        ),
    },
]


async def seed_memory() -> int:
    """
    Seed the DemoAgentMemory with curated Q&A pairs.

    Uses ``save_tool_usage()`` with a minimal ToolContext to store
    question → SQL mappings as RunSqlTool examples.

    Returns the number of pairs successfully seeded.
    """
    memory = get_agent_memory()
    seeded = 0

    # Build a minimal ToolContext for seeding
    default_user = User(
        id="default-clinic-user",
        email="clinic@example.com",
        group_memberships=["admin", "user"],
    )
    context = ToolContext(
        user=default_user,
        conversation_id="seed-session",
        request_id="seed-request",
        agent_memory=memory,
    )

    for pair in SEED_PAIRS:
        try:
            await memory.save_tool_usage(
                question=pair["question"],
                tool_name="run_sql",
                args={"sql": pair["sql"]},
                context=context,
                success=True,
            )
            seeded += 1
            logger.info("Seeded: %s", pair["question"])
        except Exception as exc:
            logger.error("Failed to seed '%s': %s", pair["question"], exc)

    return seeded


def main() -> None:
    """Entry point — seed memory and print summary."""
    count = asyncio.run(seed_memory())
    print(f"\n✅ Seeded {count}/{len(SEED_PAIRS)} Q&A pairs into DemoAgentMemory\n")


if __name__ == "__main__":
    main()
