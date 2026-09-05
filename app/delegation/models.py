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
Delegation Data Models.

Defines the core types used throughout the ownership subsystem:
  - OwnershipRole: The six possible responsibility outcomes
  - DelegationTarget: The resolved person to delegate to
  - ResponsibilityDecision: The complete evaluation result
"""
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class OwnershipRole(str, Enum):
    """The six possible ownership outcomes for an incoming email."""

    # User is the primary person who should act on this email
    PRIMARY_ACTIONEE = "PRIMARY_ACTIONEE"

    # User was CC'd or is one of many To: recipients but not specifically addressed
    OBSERVER_ONLY = "OBSERVER_ONLY"

    # User should delegate to the resolved specialist and loop them in
    DELEGATOR = "DELEGATOR"

    # A teammate already claimed ownership ("I'm on it") in the thread
    TEAMMATE_HANDLING = "TEAMMATE_HANDLING"

    # Email requires internal information before a real reply can be drafted
    NEEDS_INTERNAL_INPUT = "NEEDS_INTERNAL_INPUT"

    # Sender is an OOO auto-responder — hard block all drafts
    OOO_SENDER = "OOO_SENDER"


class DelegationTarget(BaseModel):
    """The resolved person or team to delegate to."""
    name: str = Field(description="Full name of the resolved delegatee")
    email: str = Field(description="Email address of the delegatee")
    role: str = Field(default="", description="Job title or role descriptor")
    resolver_used: str = Field(default="", description="Which resolver found this person")
    delegation_message: str = Field(
        default="",
        description="Pre-formatted loop-in message from delegation template"
    )


class ResponsibilityDecision(BaseModel):
    """Complete ownership evaluation result for a single email."""
    role: OwnershipRole = Field(description="The determined ownership role")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="How confident the evaluator is in this decision"
    )
    reason: str = Field(
        default="",
        description="Human-readable explanation of why this role was assigned"
    )
    delegation_target: Optional[DelegationTarget] = Field(
        default=None,
        description="Populated only when role is DELEGATOR"
    )
    suppress_draft: bool = Field(
        default=False,
        description="If True, the pipeline must not generate any reply draft"
    )
    holding_reply: Optional[str] = Field(
        default=None,
        description="If set, use this as the draft instead of generating one (e.g. NEEDS_INTERNAL_INPUT)"
    )

    @property
    def should_enrich_and_draft(self) -> bool:
        """Whether the pipeline should proceed to context enrichment and draft generation."""
        return self.role in (
            OwnershipRole.PRIMARY_ACTIONEE,
            OwnershipRole.DELEGATOR,
            OwnershipRole.NEEDS_INTERNAL_INPUT,
        ) and not self.suppress_draft
