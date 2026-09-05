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
Pydantic Schemas for Synthetic Test Cases, Ground Truths, and Test Execution Results.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ThreadTurn(BaseModel):
    turn: int = Field(default=1, description="Message turn index in thread")
    timestamp: str = Field(default="", description="ISO timestamp or date string")
    sender: str = Field(default="", description="Sender name and email")
    snippet: str = Field(default="", description="Cleaned body excerpt for this turn")


class EmailPayload(BaseModel):
    gmail_id: str = Field(description="Unique mock message ID")
    thread_id: str = Field(description="Unique mock thread ID")
    message_id_header: str = Field(default="", description="RFC Message-ID header")
    sender: str = Field(description="Sender name and email header")
    to: str = Field(default="", description="Direct recipient(s)")
    cc: str = Field(default="", description="Carbon copy recipient(s)")
    subject: str = Field(description="Subject line")
    snippet: str = Field(default="", description="Short snippet preview")
    body: str = Field(description="Full text body")
    headers: Dict[str, str] = Field(default_factory=dict, description="Raw RFC headers")
    thread_history: List[ThreadTurn] = Field(default_factory=list, description="Prior conversation turns")


class ExpectedGroundTruth(BaseModel):
    category: str = Field(description="Primary canonical category expected")
    acceptable_categories: List[str] = Field(default_factory=list, description="Other permissible categories for ambiguous cases")
    urgency_score_range: List[int] = Field(default=[1, 10], description="[min_urgency, max_urgency] tolerance window")
    is_reply_necessary: bool = Field(default=False, description="Semantic reply requirement")
    reply_necessity_reason: str = Field(default="", description="Ground truth rationale")
    is_no_reply: bool = Field(default=False, description="Whether sender is automated no-reply")
    is_vip: bool = Field(default=False, description="Whether sender/domain qualifies as VIP")
    has_critical_subject: bool = Field(default=False, description="Whether subject contains critical keywords")
    required_actions: List[Dict[str, Any]] = Field(default_factory=list, description="Actions that must be planned")
    forbidden_actions: List[Dict[str, Any]] = Field(default_factory=list, description="Actions that must NOT be planned")
    expected_tags_contains: List[str] = Field(default_factory=list, description="Context tags expected to be generated")
    should_trigger_calendar: bool = Field(default=False, description="Whether calendar availability should be checked")
    should_queue_pm: bool = Field(default=False, description="Whether a PM task should be queued")
    primary_assignee: str = Field(default="", description="Explicitly assigned person email if actionable")


class SyntheticTestCase(BaseModel):
    id: str = Field(description="Unique test identifier, e.g. TEST-FIN-001")
    suite: str = Field(description="Suite code/slug")
    domain: str = Field(description="Human readable business domain name")
    title: str = Field(description="Short descriptive title of test scenario")
    description: str = Field(default="", description="Detailed scenario explanation")
    email: EmailPayload = Field(description="The mock email input payload")
    expected: ExpectedGroundTruth = Field(description="The ground truth expectations")


class TestResult(BaseModel):
    test_id: str
    suite: str
    domain: str
    title: str
    passed: bool
    category_match: bool
    urgency_match: bool
    reply_necessity_match: bool
    vip_match: bool
    no_reply_match: bool
    actions_match: bool
    predicted_category: str
    predicted_urgency: int
    predicted_confidence: int
    predicted_reply_necessary: bool
    predicted_is_vip: bool
    predicted_is_no_reply: bool
    predicted_actions: List[Dict[str, Any]]
    predicted_tags: List[str]
    reasoning: str
    suggested_reply: str
    duration_ms: float
    error: Optional[str] = None
    expected: ExpectedGroundTruth
    email_snippet: str = ""
    email_sender: str = ""
    email_subject: str = ""
