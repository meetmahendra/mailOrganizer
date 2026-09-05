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
Schema definitions for the Universal Audit Telemetry Engine.
"""
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class LLMCommunication(BaseModel):
    """Telemetry record for a single LLM invocation."""
    step: str = Field(description="Pipeline step: 'classification' | 'draft_generation' | 'fallback'")
    model: str = Field(description="Model name/id used for generation")
    temperature: float = 0.0
    system_prompt: str = Field(default="", description="Verbatim system prompt sent to model")
    human_prompt: str = Field(default="", description="Verbatim human prompt sent to model")
    raw_response: str = Field(default="", description="Raw completion text or serialized structured output")
    duration_ms: float = Field(default=0.0, description="Latency in milliseconds")
    status: str = Field(default="success", description="'success' | 'error' | 'fallback'")


class ConnectorCommunication(BaseModel):
    """Telemetry record for an external connector interaction."""
    connector_id: str = Field(description="Identifier of queried connector (e.g. gmail_search, jira_mcp)")
    routing_tags: List[str] = Field(default_factory=list, description="Tags that matched routing rules")
    query_sent: str = Field(default="", description="Query string and filters dispatched")
    status: str = Field(default="success", description="'success' | 'timeout' | 'unavailable' | 'error'")
    duration_ms: float = Field(default=0.0, description="Latency in milliseconds")
    facts_count: int = Field(default=0, description="Number of facts returned")
    raw_facts_returned: List[Dict[str, Any]] = Field(default_factory=list)


class PipelineNodeTrace(BaseModel):
    """Execution trace of an individual node in the LangGraph pipeline."""
    node: str = Field(description="Name of the node (e.g. pre_check, classify, ownership_gate)")
    duration_ms: float = Field(default=0.0, description="Node runtime in milliseconds")
    routing_decision: Optional[str] = Field(default=None, description="Conditional routing decision if applicable")
    routing_reason: Optional[str] = Field(default=None, description="Explanation for routing path taken")


class AuditRecord(BaseModel):
    """
    Universal Audit Record for a single processed email.
    Captures all Live Benchmark fields + Deep LLM, Connector, and Graph Traversal Telemetry.
    """
    # Origin & Attribution
    entry_point: str = Field(default="DRY_RUN", description="'LIVE_BENCHMARK' | 'DRY_RUN' | 'API_BATCH' | 'LIVE_PIPELINE'")
    dry_run: bool = Field(default=True)
    timestamp: str = Field(description="ISO 8601 UTC timestamp")
    execution_time_seconds: float = Field(default=0.0)

    # Incoming Email Packet
    gmail_id: str = ""
    thread_id: str = ""
    message_id_header: Optional[str] = ""
    sender: str = ""
    to_recipients: List[str] = Field(default_factory=list)
    cc_recipients: List[str] = Field(default_factory=list)
    subject: str = ""
    body: str = Field(default="", description="Verbatim raw body")
    snippet: Optional[str] = ""

    # Intelligence & Intent Reasoning
    category: str = ""
    urgency_score: int = 0
    confidence_score: int = 0
    reasoning: str = ""
    context_tags: List[str] = Field(default_factory=list)
    is_reply_necessary: bool = False
    reply_necessity_reason: str = ""
    is_vip: bool = False
    is_no_reply: bool = False

    # Ownership & Delegation
    responsibility_role: str = ""
    ownership_reason: str = ""
    delegation_target: Optional[Dict[str, Any]] = None

    # Knowledge & Context
    retrieved_facts: str = ""
    calendar_context: str = ""

    # Actions & Verbatim Reply Draft
    planned_actions: List[Dict[str, Any]] = Field(default_factory=list)
    actions_taken: List[Dict[str, Any]] = Field(default_factory=list)
    enriched_draft_reply: str = Field(default="", description="Full verbatim draft reply")
    pending_pm_tasks: List[Dict[str, Any]] = Field(default_factory=list)
    pending_mutations: List[Dict[str, Any]] = Field(default_factory=list)

    # Deep Observability Telemetry
    llm_communications: List[LLMCommunication] = Field(default_factory=list)
    connector_communications: List[ConnectorCommunication] = Field(default_factory=list)
    pipeline_trace: List[PipelineNodeTrace] = Field(default_factory=list)
