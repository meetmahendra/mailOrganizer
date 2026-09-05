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
EmailState — the single data packet that flows through every LangGraph node.

Every node receives the full state and returns a dict of only the keys it mutates.
LangGraph merges the returned dict back into the state automatically.

V2 additions:
  Pre-check flags: is_no_reply, is_vip, has_critical_subject
  LLM outputs:     confidence_score, reasoning, is_reply_necessary, reply_necessity_reason
  Execution:       mode (shadow/assistive/autonomous), pending_pm_tasks
"""
from typing import TypedDict, Optional, List, Any


class EmailState(TypedDict):
    # ── Input: raw email data ─────────────────────────────────────────────────
    gmail_id: str
    thread_id: str
    subject: str
    sender: str
    body: str
    snippet: str
    message_id_header: str   # 'Message-ID' header, used for threading replies

    # ── Recipient fields (populated by gmail_service / pre_check) ────────────
    to_recipients: List[str]       # All addresses in To: header
    cc_recipients: List[str]       # All addresses in Cc: header

    # ── Auto-reply detection headers (populated by gmail_service) ────────────
    auto_reply_headers: dict       # Raw headers for OOO detection (Auto-Submitted, Precedence, etc.)

    # ── Thread History (optional past turns) ─────────────────────────────────
    thread_history: Optional[List[dict]]  # Past messages in this thread for context/ownership

    # ── Layer 1: Pre-check flags (populated by pre_check node) ───────────────
    is_no_reply: bool            # Sender is automated / no-reply address
    is_vip: bool                 # Sender matched VIP rules
    has_critical_subject: bool   # Subject contains a critical keyword

    # ── LLM classification outputs (populated by classify_email node) ─────────
    category: str            # One of the canonical categories
    urgency_score: int       # 1 (lowest) – 10 (critical)
    confidence_score: int    # 1–100: LLM's self-reported confidence in category
    reasoning: str           # Brief explanation of category choice
    suggested_reply: str     # Draft reply body; empty for non-reply categories
    context_tags: List[str]  # 8–15 taxonomy-guided context tags
    is_reply_necessary: bool # True if email semantically warrants a reply
    reply_necessity_reason: str  # LLM explanation of reply decision

    # ── Action planning (populated by plan_gmail_actions node) ────────────────
    gmail_actions: List[dict]  # e.g. [{"action": "apply_label", "label": "@Urgent"}]

    # ── PM tasks (populated by execute_actions node) ──────────────────────────
    pending_pm_tasks: List[dict]  # Tasks queued for user approval

    # ── Calendar enrichment (populated by handle_calendar node) ──────────────
    calendar_context: str    # Human-readable free/busy + upcoming events summary

    # ── Ownership & Delegation (populated by ownership_gate node) ─────────
    responsibility_role: str          # PRIMARY_ACTIONEE | OBSERVER_ONLY | DELEGATOR | etc.
    delegation_target: Optional[dict] # Resolved delegatee info if DELEGATOR
    ownership_reason: str             # Human-readable explanation of ownership decision

    # ── Context Enrichment (populated by enrich_context node) ─────────────
    retrieved_facts: str              # Synthesized fact bullets from connectors

    # ── Consolidated Draft (populated by generate_enriched_draft node) ────
    enriched_draft_reply: str         # Definitive draft from the single authoritative path

    # ── Pending Mutations (populated by enrichment subgraph) ──────────────
    pending_mutations: List[dict]     # Queued external system updates for review

    # ── Execution context & Source Attribution ───────────────────────────────
    dry_run: bool            # True → CSV only;  False → real Gmail API calls
    creds: Any               # google.oauth2.credentials.Credentials object
    user_id: int
    entry_point: str         # "LIVE_BENCHMARK" | "DRY_RUN" | "API_BATCH" | "LIVE_PIPELINE"

    # ── Deep Telemetry (Universal Audit Engine) ──────────────────────────────
    llm_communications: List[dict]        # Exact system/human prompts, model, latency, output
    connector_communications: List[dict]  # Dispatched queries, connector latency, raw facts
    pipeline_trace: List[dict]            # Node traversal order, node durations, routing reasons
    pipeline_start_time: float            # Monotonic start time for end-to-end latency

    # ── Result tracking (populated by execute_actions / log_result nodes) ────
    actions_taken: List[dict]  # Each action with its execution status
    error: Optional[str]
