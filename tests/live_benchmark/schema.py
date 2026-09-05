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
Schema definitions for the High-Fidelity Live Benchmark Suite (Phase 7).

NOTE: This is a completely separate schema from `tests/synthetic/schema.py`.
SyntheticTestCase tests deterministic rules and classification tags offline.
LiveBenchmarkTestCase evaluates end-to-end outcome-based business impact:
  - Multi-To and CC ownership resolution
  - Fact-grounded draft quality (must mention facts, must not stall)
  - Hard safety guardrails (OOO loop block, VIP preservation, phishing, subpoena lockdown)
  - Connector enrichment and action planning
"""
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class EmailPayload(BaseModel):
    """Raw email inputs provided to the pipeline."""
    gmail_id: str = Field(default="live_bench_msg_001")
    thread_id: str = Field(default="live_bench_thread_001")
    subject: str
    sender: str
    body: str
    snippet: Optional[str] = ""
    to_recipients: List[str] = Field(default_factory=list)
    cc_recipients: List[str] = Field(default_factory=list)
    auto_reply_headers: Dict[str, str] = Field(default_factory=dict)
    message_id_header: Optional[str] = "<msg_001@company.com>"


class DraftRequirements(BaseModel):
    """Requirements on the generated reply draft."""
    should_draft: bool = Field(description="Whether an auto-draft reply should be generated")
    must_mention: List[str] = Field(
        default_factory=list,
        description="Key facts or data points that MUST appear in the draft (e.g. ticket numbers, dates, policy caps)"
    )
    must_not_contain: List[str] = Field(
        default_factory=list,
        description="Boilerplate stalling or generic phrases that MUST NOT appear (e.g. 'I will look into this shortly')"
    )


class EvaluationCriteria(BaseModel):
    """Business outcome evaluation criteria for a benchmark scenario."""
    inbox_placement: str = Field(
        default="MUST_KEEP_INBOX",
        description="Expected inbox action: 'MUST_KEEP_INBOX', 'REMOVE_INBOX', 'SAFE_ARCHIVE', or 'DONT_CARE'"
    )
    urgency_level: str = Field(
        default="HIGH",
        description="Expected urgency tier: 'HIGH' (8-10), 'MEDIUM' (4-7), 'LOW' (1-3)"
    )
    expected_responsibility: str = Field(
        default="PRIMARY_ACTIONEE",
        description="Expected ownership: PRIMARY_ACTIONEE | OBSERVER_ONLY | DELEGATOR | TEAMMATE_HANDLING | NEEDS_INTERNAL_INPUT | OOO_SENDER"
    )
    draft_requirements: DraftRequirements
    safety_assertions: List[str] = Field(
        default_factory=list,
        description="Assertions: e.g. 'zero_draft_to_ooo', 'zero_vip_loss', 'no_auto_reply_to_no_reply', 'confidential_review_on_sensitive'"
    )


class LiveBenchmarkTestCase(BaseModel):
    """Complete specification of a live benchmark scenario."""
    id: str = Field(description="Unique scenario ID (e.g. 'OWN-001', 'SRE-002')")
    title: str = Field(description="Short human-readable scenario title")
    domain: str = Field(description="Domain category (e.g. 'ownership_delegation', 'fintech', 'cloud_sre')")
    description: Optional[str] = ""
    email: EmailPayload
    connector_fixtures: Dict[str, Any] = Field(
        default_factory=dict,
        description="Mock connector fixtures (facts, calendar slots, past threads) to inject for evaluation"
    )
    evaluation_criteria: EvaluationCriteria


class BenchmarkEvaluationResult(BaseModel):
    """Result of running and scoring a single benchmark test case."""
    test_id: str
    title: str
    domain: str
    passed: bool
    score: float = Field(ge=0.0, le=100.0, description="Overall outcome score 0-100")
    
    # Sub-dimension scores
    safety_passed: bool
    responsibility_passed: bool
    inbox_placement_passed: bool
    draft_requirements_passed: bool

    # Detailed evaluation notes
    actual_responsibility: str
    actual_inbox_action: str
    actual_draft: str
    failure_reasons: List[str] = Field(default_factory=list)
    execution_time_seconds: float = 0.0

    # Full Information Audit Fields
    sender: str = ""
    to_recipients: List[str] = Field(default_factory=list)
    cc_recipients: List[str] = Field(default_factory=list)
    subject: str = ""
    body: str = ""
    category: str = ""
    urgency_score: int = 0
    context_tags: List[str] = Field(default_factory=list)
    reasoning: str = ""
    ownership_reason: str = ""
    delegation_target: Optional[Dict[str, Any]] = None
    retrieved_facts: str = ""
    planned_actions: List[Dict[str, Any]] = Field(default_factory=list)
    verified_keywords: List[str] = Field(default_factory=list)
    missing_keywords: List[str] = Field(default_factory=list)
    score_breakdown: Dict[str, float] = Field(default_factory=dict)
