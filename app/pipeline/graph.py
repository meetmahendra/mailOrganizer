# Copyright 2026 Mahendra GURAV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
LangGraph StateGraph assembly for the V3 email automation pipeline.

Graph flow (V3 — with ownership gate and enrichment subgraph):

  pre_check_email          (Layer 1: encoding, no-reply, VIP)
      |
  classify_email           (Layer 2: LLM, confidence, tags, reply necessity)
      |
  ownership_gate           (Layer 2.5: delegation, OOO, multi-To disambiguation)
      |
  +-- role in {OBSERVER, TEAMMATE, OOO}? --+
  | YES (suppress draft)                   | NO (proceed to enrich)
  |                                        |
  |                              enrich_context (parallel connector queries)
  |                                        |
  |                           generate_enriched_draft (fact-grounded draft)
  |                                        |
  +----------------------------------------+
      |
  plan_gmail_actions       (Layer 3: external rules engine + VIP enforcement)
      |
  +-- category == "Calendar/Scheduling"? --+
  | YES                                    | NO
  handle_calendar                          |
      +------------------------------------+
                     |
              execute_actions              (Layer 4: Gmail API + PM queue)
                     |
                log_result                (Layer 5: DB persistence)
                     |
                    END
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.graph import StateGraph, END

from pipeline.state import EmailState
from pipeline.nodes import (
    pre_check_email,
    classify_email,
    ownership_gate,
    enrich_context,
    generate_enriched_draft,
    plan_gmail_actions,
    handle_calendar,
    execute_actions,
    log_result,
)


def _traced_node(node_name: str, fn):
    """Decorator that records node runtime into pipeline_trace."""
    def wrapped(state: EmailState) -> dict:
        t0 = time.perf_counter()
        result = fn(state) or {}
        duration_ms = round((time.perf_counter() - t0) * 1000, 2)
        trace = list(state.get("pipeline_trace") or [])
        trace.append({"node": node_name, "duration_ms": duration_ms})
        result["pipeline_trace"] = trace
        return result
    return wrapped


# ── Conditional routers ──────────────────────────────────────────────────────

def _route_after_ownership(state: EmailState) -> str:
    """
    Route based on ownership decision.
    If draft should be suppressed (OBSERVER_ONLY, TEAMMATE_HANDLING, OOO_SENDER),
    skip enrichment and go straight to action planning.
    Otherwise, proceed to context enrichment.
    """
    role = state.get("responsibility_role", "PRIMARY_ACTIONEE")
    suppress_roles = {"OBSERVER_ONLY", "TEAMMATE_HANDLING", "OOO_SENDER"}
    trace = list(state.get("pipeline_trace") or [])

    if role in suppress_roles:
        trace.append({
            "node": "ownership_gate",
            "duration_ms": 0.0,
            "routing_decision": "plan_actions",
            "routing_reason": f"Role '{role}' suppresses draft -> skipped enrich_context",
        })
        state["pipeline_trace"] = trace
        return "plan_actions"

    trace.append({
        "node": "ownership_gate",
        "duration_ms": 0.0,
        "routing_decision": "enrich_context",
        "routing_reason": f"Role '{role}' requires drafting -> proceeded to enrich_context",
    })
    state["pipeline_trace"] = trace
    return "enrich_context"


def _route_after_planning(state: EmailState) -> str:
    cat = state.get("category", "")
    trace = list(state.get("pipeline_trace") or [])
    if cat == "Calendar/Scheduling":
        trace.append({
            "node": "plan_actions",
            "duration_ms": 0.0,
            "routing_decision": "handle_calendar",
            "routing_reason": "Category is Calendar/Scheduling -> routed to calendar handler",
        })
        state["pipeline_trace"] = trace
        return "handle_calendar"

    trace.append({
        "node": "plan_actions",
        "duration_ms": 0.0,
        "routing_decision": "execute",
        "routing_reason": f"Category is '{cat}' -> skipped calendar handler",
    })
    state["pipeline_trace"] = trace
    return "execute"


# ── Graph assembly ────────────────────────────────────────────────────────────

def build_graph():
    workflow = StateGraph(EmailState)

    workflow.add_node("pre_check",       _traced_node("pre_check", pre_check_email))
    workflow.add_node("classify",        _traced_node("classify", classify_email))
    workflow.add_node("ownership_gate",  _traced_node("ownership_gate", ownership_gate))
    workflow.add_node("enrich_context",  _traced_node("enrich_context", enrich_context))
    workflow.add_node("generate_draft",  _traced_node("generate_draft", generate_enriched_draft))
    workflow.add_node("plan_actions",    _traced_node("plan_actions", plan_gmail_actions))
    workflow.add_node("handle_calendar", _traced_node("handle_calendar", handle_calendar))
    workflow.add_node("execute",         _traced_node("execute", execute_actions))
    workflow.add_node("log_result",      _traced_node("log_result", log_result))

    workflow.set_entry_point("pre_check")

    workflow.add_edge("pre_check",       "classify")
    workflow.add_edge("classify",        "ownership_gate")

    # Ownership gate routes to either enrichment or straight to planning
    workflow.add_conditional_edges(
        "ownership_gate",
        _route_after_ownership,
        {
            "enrich_context": "enrich_context",
            "plan_actions":   "plan_actions",
        },
    )

    workflow.add_edge("enrich_context",  "generate_draft")
    workflow.add_edge("generate_draft",  "plan_actions")

    workflow.add_conditional_edges(
        "plan_actions",
        _route_after_planning,
        {
            "handle_calendar": "handle_calendar",
            "execute":         "execute",
        },
    )
    workflow.add_edge("handle_calendar", "execute")
    workflow.add_edge("execute",         "log_result")
    workflow.add_edge("log_result",      END)

    return workflow.compile()


# Singleton compiled graph — import this everywhere
email_pipeline = build_graph()


# ── Public runner helper ──────────────────────────────────────────────────────

def run_pipeline(email_data: dict, creds, user_id: int, dry_run: bool, entry_point: str = "DRY_RUN") -> dict:
    """
    Run a single email through the compiled LangGraph pipeline.

    Args:
        email_data:  dict with keys: gmail_id, thread_id, subject, sender,
                     body, snippet, message_id_header, to_recipients,
                     cc_recipients, auto_reply_headers
        creds:       google.oauth2.credentials.Credentials
        user_id:     integer user ID from the local DB
        dry_run:     True -> CSV only;  False -> real Gmail mutations
        entry_point: Source attribution tag ("LIVE_BENCHMARK", "DRY_RUN", "API_BATCH", etc.)

    Returns:
        Final EmailState dict after all nodes have run.
    """
    initial_state: EmailState = {
        # Raw email fields
        "gmail_id":          email_data.get("gmail_id", ""),
        "thread_id":         email_data.get("thread_id", ""),
        "subject":           email_data.get("subject", ""),
        "sender":            email_data.get("sender", ""),
        "body":              email_data.get("body", ""),
        "snippet":           email_data.get("snippet", ""),
        "message_id_header": email_data.get("message_id_header", ""),
        "to_recipients":     email_data.get("to_recipients", []),
        "cc_recipients":     email_data.get("cc_recipients", []),
        "auto_reply_headers": email_data.get("auto_reply_headers", {}),
        "thread_history":    email_data.get("thread_history", []),
        # Layer 1 pre-check flags (filled by pre_check node)
        "is_no_reply":          False,
        "is_vip":               False,
        "has_critical_subject": False,
        # Classification placeholders (filled by classify node)
        "category":              "",
        "urgency_score":         0,
        "confidence_score":      0,
        "reasoning":             "",
        "suggested_reply":       "",
        "context_tags":          [],
        "is_reply_necessary":    False,
        "reply_necessity_reason": "",
        # Action placeholders
        "gmail_actions":   [],
        "pending_pm_tasks": [],
        "calendar_context": "",
        # Ownership & Delegation (filled by ownership_gate)
        "responsibility_role": "",
        "delegation_target":   None,
        "ownership_reason":    "",
        # Enrichment (filled by enrich_context)
        "retrieved_facts": "",
        # Consolidated draft (filled by generate_enriched_draft)
        "enriched_draft_reply": "",
        # Pending mutations
        "pending_mutations": [],
        # Execution context & Attribution
        "dry_run":  dry_run,
        "creds":    creds,
        "user_id":  user_id,
        "entry_point": entry_point,
        # Deep telemetry containers
        "llm_communications": [],
        "connector_communications": [],
        "pipeline_trace": [],
        "pipeline_start_time": time.time(),
        # Results
        "actions_taken": [],
        "error":         None,
    }
    return email_pipeline.invoke(initial_state)
