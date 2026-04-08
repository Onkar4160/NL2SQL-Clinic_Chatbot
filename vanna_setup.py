"""
vanna_setup.py — Vanna 2.0 Agent Configuration

Configures and returns a Vanna 2.0 Agent instance with:
- Google Gemini (gemini-2.5-flash) as the LLM service
- SQLite runner pointing to clinic.db
- ToolRegistry with RunSqlTool, VisualizeDataTool, and memory tools
- DemoAgentMemory for learning from past interactions
- A default UserResolver for single-user (clinic staff) usage
"""

import os
import logging

from dotenv import load_dotenv

from vanna import Agent
from vanna.core.registry import ToolRegistry
from vanna.core.user import UserResolver, User, RequestContext
from vanna.integrations.google import GeminiLlmService
from vanna.integrations.sqlite import SqliteRunner
from vanna.integrations.local.agent_memory import DemoAgentMemory
from vanna.tools import RunSqlTool, VisualizeDataTool
from vanna.tools.agent_memory import (
    SaveQuestionToolArgsTool,
    SearchSavedCorrectToolUsesTool,
    SaveTextMemoryTool,
)

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DB_PATH = "./clinic.db"
GEMINI_MODEL = "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# User resolver — single default "Clinic User" with admin+user access
# ---------------------------------------------------------------------------

class DefaultUserResolver(UserResolver):
    """Always resolves to a default clinic staff user with full access."""

    async def resolve_user(self, request_context: RequestContext) -> User:
        """Return the default clinic user regardless of request context."""
        return User(
            id="default-clinic-user",
            email="clinic@example.com",
            group_memberships=["admin", "user"],
        )


# ---------------------------------------------------------------------------
# Singleton agent
# ---------------------------------------------------------------------------

_agent: Agent | None = None
_agent_memory: DemoAgentMemory | None = None


def get_agent_memory() -> DemoAgentMemory:
    """Return the shared DemoAgentMemory instance (creates one if needed)."""
    global _agent_memory
    if _agent_memory is None:
        _agent_memory = DemoAgentMemory(max_items=1000)
        logger.info("Initialized DemoAgentMemory (max_items=1000)")
    return _agent_memory


def get_agent() -> Agent:
    """
    Build and return the Vanna 2.0 Agent (singleton).

    The agent is configured with:
    - GeminiLlmService (gemini-2.5-flash)
    - SqliteRunner → clinic.db
    - 5 tools: RunSqlTool, VisualizeDataTool, SaveQuestionToolArgsTool,
      SearchSavedCorrectToolUsesTool, SaveTextMemoryTool
    - DemoAgentMemory for learning from interactions
    """
    global _agent

    if _agent is not None:
        return _agent

    # --- Step 1: LLM Service ------------------------------------------------
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GOOGLE_API_KEY not set. Add it to your .env file or environment."
        )

    llm_service = GeminiLlmService(model=GEMINI_MODEL, api_key=api_key)
    logger.info("LLM service configured: %s", GEMINI_MODEL)

    # --- Step 2: SQL Runner --------------------------------------------------
    sql_runner = SqliteRunner(database_path=DB_PATH)
    logger.info("SQLite runner configured: %s", DB_PATH)

    # --- Step 3: Tool Registry -----------------------------------------------
    tools = ToolRegistry()

    # Core tools
    tools.register_local_tool(
        RunSqlTool(sql_runner=sql_runner),
        access_groups=["admin", "user"],
    )
    tools.register_local_tool(
        VisualizeDataTool(),
        access_groups=["admin", "user"],
    )

    # Memory tools
    tools.register_local_tool(
        SaveQuestionToolArgsTool(),
        access_groups=["admin"],
    )
    tools.register_local_tool(
        SearchSavedCorrectToolUsesTool(),
        access_groups=["admin", "user"],
    )
    tools.register_local_tool(
        SaveTextMemoryTool(),
        access_groups=["admin", "user"],
    )
    logger.info("Registered 5 tools in ToolRegistry")

    # --- Step 4: Agent Memory ------------------------------------------------
    agent_memory = get_agent_memory()

    # --- Step 5: User Resolver -----------------------------------------------
    user_resolver = DefaultUserResolver()

    # --- Step 6: Agent -------------------------------------------------------
    _agent = Agent(
        llm_service=llm_service,
        tool_registry=tools,
        user_resolver=user_resolver,
        agent_memory=agent_memory,
    )
    logger.info("Vanna 2.0 Agent initialized successfully")

    return _agent
