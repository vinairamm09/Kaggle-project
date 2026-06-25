import datetime
import json
import logging
import os
import re
import sys
from collections.abc import Generator
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.apps import App, ResumabilityConfig
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.tools import AgentTool
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.workflow import START, Workflow
from google.genai import types
from mcp import StdioServerParameters
from pydantic import BaseModel, Field

from .config import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Pydantic Schemas ---


class WorkflowInput(BaseModel):
    query: str


class GuestInfo(BaseModel):
    name: str
    status: str = Field(description="RSVP Status: attending, declined, or pending")
    dietary: str = Field(
        default="", description="Any dietary restrictions or preferences"
    )


class RSVPResult(BaseModel):
    guests: list[GuestInfo] = Field(default=[], description="List of guests and status")
    summary: str = Field(description="Summary of guest list and dietary needs")


class ExpenseInfo(BaseModel):
    item: str
    paid_by: str
    amount: float


class ExpenseResult(BaseModel):
    expenses: list[ExpenseInfo] = Field(
        default=[], description="List of individual expenses"
    )
    total_cost: float = Field(description="Total cost of all expenses combined")
    split_details: list[str] = Field(
        description="Calculated splitting details showing who owes what to whom"
    )


class OrchestratorOutput(BaseModel):
    rsvp_summary: str = Field(description="Summary of RSVP data extracted")
    expense_summary: str = Field(
        description="Summary of expenses and splits calculated"
    )
    overall_plan_summary: str = Field(
        description="An overall event plan narrative combining the RSVP list and splitting calculations"
    )


class EventState(BaseModel):
    query: str = ""
    sanitized_query: str = ""
    rsvp_data: RSVPResult = RSVPResult(summary="")
    expense_data: ExpenseResult = ExpenseResult(total_cost=0.0, split_details=[])
    orchestrator_summary: str = ""
    review_comments: str = ""
    status: str = "pending"


# --- MCP Toolset Setup ---
current_dir = os.path.dirname(os.path.abspath(__file__))
mcp_server_path = os.path.join(current_dir, "mcp_server.py")

server_params = StdioServerParameters(command=sys.executable, args=[mcp_server_path])
mcp_tools = MCPToolset(
    connection_params=StdioConnectionParams(server_params=server_params)
)

# --- Specialist Sub-Agents ---

rsvp_manager = LlmAgent(
    name="rsvp_manager",
    model=config.model,
    instruction=(
        "You are a specialized RSVP Manager. Extract guest names, their RSVP status "
        "(attending, declined, pending), and any dietary requirements from the event description. "
        "Return a structured JSON object with 'guests' (list of {name, status, dietary}) "
        "and 'summary' (a text summary of guest list and dietary needs)."
    ),
    output_schema=RSVPResult,
    output_key="rsvp_data",
)

expense_calculator = LlmAgent(
    name="expense_calculator",
    model=config.model,
    instruction=(
        "You are a specialized Expense Calculator. Extract financial details (items, cost, who paid) "
        "from the event description. Compute the total cost and split it evenly among all attending guests. "
        "Return a structured JSON with 'expenses' (list of {item, paid_by, amount}), "
        "'total_cost' (float), and 'split_details' (list of strings describing who owes what)."
    ),
    output_schema=ExpenseResult,
    output_key="expense_data",
)

# Expose sub-agents as tools using AgentTool
rsvp_tool = AgentTool(agent=rsvp_manager)
expense_tool = AgentTool(agent=expense_calculator)

# --- Orchestrator Agent ---
# NOTE: output_schema cannot be combined with tools in ADK.
# The orchestrator uses sub-agent tools and writes a text summary to output_key.

event_orchestrator = LlmAgent(
    name="event_orchestrator",
    model=config.model,
    instruction=(
        "You are the Event Orchestrator coordinating event planning. "
        "Call 'rsvp_manager' with the full event description to get the RSVP summary. "
        "Call 'expense_calculator' with the full event description to get the expense breakdown. "
        "After both tools return, compile a comprehensive event plan in this EXACT JSON format:\n"
        "{\n"
        '  "rsvp_summary": "<text summary of guests and dietary needs>",\n'
        '  "expense_summary": "<text summary of expenses and cost splits>",\n'
        '  "overall_plan_summary": "<narrative combining RSVP list and cost splits>"\n'
        "}\n"
        "Output ONLY the JSON object, nothing else."
    ),
    tools=[rsvp_tool, expense_tool],
    output_key="orchestrator_response",
)

# --- Workflow Graph Nodes ---


def security_checkpoint(ctx: Context, node_input: Any) -> Event:
    """Security node to check for PII, prompt injection, and domain-specific rules."""
    # node_input may be a WorkflowInput, a plain string, or a dict
    if isinstance(node_input, WorkflowInput):
        query = node_input.query
    elif isinstance(node_input, dict):
        query = node_input.get("query", str(node_input))
    else:
        query = str(node_input)
    logger.info(f"Security check on query: {query}")

    # Helper for JSON audit logging
    def log_audit(severity: str, event: str, details: str):
        audit_entry = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "severity": severity,
            "event": event,
            "details": details,
            "session_id": ctx.session.id,
        }
        print(f"AUDIT_LOG: {json.dumps(audit_entry)}", file=sys.stderr)

    # 1. PII Redaction/Check (email and phone number)
    if config.pii_redaction_enabled:
        email_detected = bool(
            re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", query)
        )
        phone_detected = bool(
            re.search(
                r"\+?\d{1,4}[-.\s]?\(?\d{1,3}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}", query
            )
        )
        if email_detected or phone_detected:
            pii_type = "email" if email_detected else "phone number"
            log_audit("WARNING", "PII_BLOCKED", f"User query contained {pii_type}.")
            return Event(
                output=f"PII block: {pii_type}s are not allowed.",
                route="SECURITY_EVENT",
            )

    # 2. Prompt Injection Detection
    if config.injection_detection_enabled:
        injection_keywords = [
            "ignore previous instructions",
            "system prompt",
            "overwrite instructions",
            "bypass security",
            "ignore security instructions",
        ]
        for kw in injection_keywords:
            if kw in query.lower():
                log_audit(
                    "CRITICAL", "PROMPT_INJECTION_DETECTED", f"Detected keyword: '{kw}'"
                )
                return Event(
                    output=f"Security violation: Injection attempt detected ('{kw}').",
                    route="SECURITY_EVENT",
                )

    # 3. Domain-Specific Rule: Prevent single expenses >= $5000
    large_expense = re.search(
        r"\$(?:[5-9]\d{3,}|\d{5,})(?:\.\d{2})?|\b[5-9]\d{3,}\s*(?:dollars|USD)\b", query
    )
    if large_expense:
        log_audit(
            "WARNING",
            "FRAUD_LIMIT_TRIGGERED",
            f"Attempted expense value: '{large_expense.group(0)}'",
        )
        return Event(
            output="Policy block: Individual event expenses cannot equal or exceed $5,000 to prevent fraud.",
            route="SECURITY_EVENT",
        )

    # Audit log entry for passing checkpoint
    log_audit("INFO", "SECURITY_PASSED", "Query passed all security checks.")

    return Event(
        output=query,
        route="__DEFAULT__",
        state={"query": query, "sanitized_query": query},
    )


def security_error_node(node_input: str) -> Generator[Event, None, None]:
    """Node called on security policy violations."""
    msg = f"🛡️ **Security Blocked:** {node_input}"
    yield Event(
        content=types.Content(role="model", parts=[types.Part.from_text(text=msg)])
    )
    yield Event(output=msg)


async def human_review(ctx: Context, node_input: Any) -> Generator[Any, None, None]:
    """HITL step using RequestInput to get user approval on the plan."""
    # node_input is the orchestrator's text output (JSON string or dict)
    if isinstance(node_input, dict):
        plan_data = node_input
    else:
        try:
            plan_data = json.loads(str(node_input))
        except Exception:
            plan_data = {"overall_plan_summary": str(node_input)}

    if not ctx.resume_inputs:
        prompt_msg = (
            f"📋 **Draft Event Plan Generated:**\n\n"
            f"**RSVP Summary:**\n{plan_data.get('rsvp_summary', 'N/A')}\n\n"
            f"**Expense Summary:**\n{plan_data.get('expense_summary', 'N/A')}\n\n"
            f"**Overall Plan:**\n{plan_data.get('overall_plan_summary', 'N/A')}\n\n"
            f"✋ Please review the plan. Reply **'Yes'** to approve, or provide changes/feedback."
        )
        yield RequestInput(interrupt_id="approve_event_plan", message=prompt_msg)
        return

    # Process resume inputs
    user_response = ctx.resume_inputs.get("approve_event_plan", "")
    logger.info(f"Received human approval response: {user_response}")

    is_approved = "yes" in user_response.lower()
    status = "approved" if is_approved else "needs_revision"

    yield Event(
        output={"status": status, "feedback": user_response},
        state={"status": status, "review_comments": user_response},
    )


def final_output(node_input: dict) -> Generator[Event, None, None]:
    """Terminal node displaying final result."""
    status = node_input.get("status", "")
    feedback = node_input.get("feedback", "")

    if status == "approved":
        msg = f"✅ **Event Plan Approved & Finalized!**\n\nComments: {feedback}"
    else:
        msg = f"❌ **Plan Rejection/Revision Required.**\n\nFeedback: {feedback}"

    yield Event(
        content=types.Content(role="model", parts=[types.Part.from_text(text=msg)])
    )
    yield Event(output=msg)


# --- Workflow Definition ---

root_agent = Workflow(
    name="event_coordinator",
    state_schema=EventState,
    edges=[
        (START, security_checkpoint),
        (
            security_checkpoint,
            {
                "SECURITY_EVENT": security_error_node,
                "__DEFAULT__": event_orchestrator,
            },
        ),
        (event_orchestrator, human_review),
        (human_review, final_output),
    ],
)

app = App(
    name="app",
    root_agent=root_agent,
    resumability_config=ResumabilityConfig(is_resumable=True),
)
