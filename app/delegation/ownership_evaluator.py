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
Ownership Evaluator — Core Decision Engine.

Determines who is responsible for an incoming email by evaluating
multiple signals in priority order:

  1. OOO Auto-Responder Detection (hard block — highest priority)
  2. Multi-To / CC Recipient Disambiguation
  3. Teammate "I'm on it" Thread Tracking
  4. Dynamic Capability-Based Delegation (via registered app resolvers)
  5. Missing Information / Inferred Dependency Detection

Each check is self-contained and testable independently.
"""
import os
import re
import sys
from typing import Optional, List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from delegation.models import (
    OwnershipRole,
    ResponsibilityDecision,
    DelegationTarget,
)

try:
    from config.schemas import load_and_validate_delegation_config, load_and_validate_user_persona_config
except ImportError:
    load_and_validate_delegation_config = None
    load_and_validate_user_persona_config = None


# ── Cached config ─────────────────────────────────────────────────────────────

_delegation_config = None
_persona_config = None


def _get_delegation_config():
    global _delegation_config
    if _delegation_config is None and load_and_validate_delegation_config:
        _delegation_config = load_and_validate_delegation_config()
    return _delegation_config


def _get_persona_config():
    global _persona_config
    if _persona_config is None and load_and_validate_user_persona_config:
        _persona_config = load_and_validate_user_persona_config()
    return _persona_config


def _clean_email(addr: str) -> str:
    """Extract bare email from 'Name <user@domain.com>' format."""
    match = re.search(r'[\w\.\-\+]+@[\w\.\-]+\.\w+', addr)
    return match.group(0).lower() if match else addr.strip().lower()


def _get_user_email() -> str:
    """Get the configured user's email from persona config."""
    persona = _get_persona_config()
    if persona:
        sig = persona.signature or ""
        match = re.search(r'[\w\.\-\+]+@[\w\.\-]+\.\w+', sig)
        if match:
            return match.group(0).lower()
    return ""


def _get_user_name() -> str:
    """Get the configured user's name from persona config."""
    persona = _get_persona_config()
    return persona.name if persona else ""


# ═══════════════════════════════════════════════════════════════════════════════
# CHECK 1: OOO Auto-Responder Detection
# ═══════════════════════════════════════════════════════════════════════════════

def check_ooo_sender(auto_reply_headers: dict, body: str = "") -> Optional[ResponsibilityDecision]:
    """
    Detect if the sender is an Out-of-Office auto-responder.

    Priority 1 (highest) — if detected, hard-blocks all draft generation.

    Detection layers:
      Layer A: RFC 3834 headers (deterministic, reliable)
      Layer B: Body text heuristics (fallback for missing headers)
    """
    if not auto_reply_headers:
        auto_reply_headers = {}

    # Layer A: Header-based detection (most reliable)
    auto_submitted = (auto_reply_headers.get("auto_submitted") or "").lower().strip()
    if auto_submitted in ("auto-replied", "auto-generated", "auto-notified"):
        return ResponsibilityDecision(
            role=OwnershipRole.OOO_SENDER,
            confidence=0.99,
            reason=f"Auto-Submitted header detected: '{auto_submitted}'",
            suppress_draft=True,
        )

    x_auto_suppress = (auto_reply_headers.get("x_auto_response_suppress") or "").lower().strip()
    if x_auto_suppress and x_auto_suppress != "none":
        return ResponsibilityDecision(
            role=OwnershipRole.OOO_SENDER,
            confidence=0.95,
            reason=f"X-Auto-Response-Suppress header: '{x_auto_suppress}'",
            suppress_draft=True,
        )

    precedence = (auto_reply_headers.get("precedence") or "").lower().strip()
    if precedence in ("bulk", "junk", "list"):
        return ResponsibilityDecision(
            role=OwnershipRole.OOO_SENDER,
            confidence=0.85,
            reason=f"Precedence header: '{precedence}' (bulk/auto message)",
            suppress_draft=True,
        )

    x_autoreply = (auto_reply_headers.get("x_autoreply") or "").lower().strip()
    if x_autoreply in ("yes", "true", "1"):
        return ResponsibilityDecision(
            role=OwnershipRole.OOO_SENDER,
            confidence=0.95,
            reason="X-Autoreply header indicates auto-response",
            suppress_draft=True,
        )

    # Layer B: Body text heuristics
    if body:
        body_lower = body.lower()
        ooo_patterns = [
            r"i am out of (?:the )?office",
            r"i(?:'m| am) (?:currently )?(?:away|on vacation|on leave|on pto)",
            r"i will (?:be )?(?:out of office|away from|unavailable)",
            r"this is an? auto(?:matic|mated)?\s*(?:reply|response)",
            r"i (?:will|shall) (?:return|be back) (?:on|by)",
            r"(?:away|out) (?:from|until) .{3,30}(?:monday|tuesday|wednesday|thursday|friday|january|february|march|april|may|june|july|august|september|october|november|december|\d{1,2}/\d{1,2})",
        ]
        for pattern in ooo_patterns:
            if re.search(pattern, body_lower):
                return ResponsibilityDecision(
                    role=OwnershipRole.OOO_SENDER,
                    confidence=0.75,
                    reason=f"Body text matches OOO pattern: '{pattern}'",
                    suppress_draft=True,
                )

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# CHECK 2: Multi-To / CC Recipient Disambiguation
# ═══════════════════════════════════════════════════════════════════════════════

def check_recipient_role(
    to_recipients: List[str],
    cc_recipients: List[str],
    body: str,
    sender: str,
) -> Optional[ResponsibilityDecision]:
    """
    Determine if the user is the primary addressee, an observer, or a broadcast recipient.

    Rules (applied in order):
      1. User is ONLY in CC and not in To → OBSERVER_ONLY
      2. User is one of many To: recipients and body names someone else → OBSERVER_ONLY
      3. To: count exceeds broadcast_threshold and user not called out → OBSERVER_ONLY
      4. User is sole To: recipient → PRIMARY_ACTIONEE
    """
    config = _get_delegation_config()
    user_email = _get_user_email()
    user_name = _get_user_name()

    if not user_email:
        return None  # Can't evaluate without knowing who the user is

    clean_to = [_clean_email(r) for r in to_recipients]
    clean_cc = [_clean_email(r) for r in cc_recipients]

    user_in_to = user_email in clean_to
    user_in_cc = user_email in clean_cc

    # Rule 1: User only in CC → observer
    if user_in_cc and not user_in_to:
        return ResponsibilityDecision(
            role=OwnershipRole.OBSERVER_ONLY,
            confidence=0.95,
            reason=f"User ({user_email}) is in CC only, not addressed in To:",
            suppress_draft=True,
        )

    if not user_in_to:
        # Check if user is addressed by name in body (e.g. email arrived via alias/distribution list)
        user_named = False
        body_lower = body.lower() if body else ""
        if user_name and len(user_name) > 2:
            first_name = user_name.split()[0].lower()
            if first_name in body_lower:
                user_named = True
        if not user_named:
            # User is neither directly in To: nor named in body (received via alias/distribution list)
            return ResponsibilityDecision(
                role=OwnershipRole.OBSERVER_ONLY,
                confidence=0.85,
                reason=f"User ({user_email}) is not directly addressed in To: (received via alias/distribution list)",
                suppress_draft=True,
            )
        return None

    broadcast_threshold = 4
    if config:
        broadcast_threshold = config.multi_recipient_to.broadcast_threshold

    # Rule 2 & 3: Multiple recipients in To:
    if len(clean_to) > 1:
        # Check if someone else is specifically named in the body
        other_recipients = [r for r in clean_to if r != user_email]
        body_lower = body.lower() if body else ""

        # Check if user is called out specifically
        someone_else_named = False
        user_named = False
        first_name = user_name.split()[0].lower() if user_name else ""

        # Check if user is mentioned merely as an observer / FYI (e.g. "Marcus is included for visibility")
        is_user_observer_mention = False
        if first_name and len(first_name) > 2:
            observer_phrases = [
                rf"\b{first_name}\b\s+is\s+(?:included\s+|copied\s+|cc'?d\s+)?(?:for\s+visibility|for\s+info|for\s+awareness|as\s+fyi|fyi)",
                rf"(?:cc'?ing|copying|looping\s+in)\s+\b{first_name}\b\s+(?:for\s+visibility|for\s+info|for\s+awareness)",
                rf"(?:fyi|for\s+visibility|for\s+awareness)[,\s:]+\b{first_name}\b",
            ]
            is_user_observer_mention = any(re.search(p, body_lower) for p in observer_phrases)

        if is_user_observer_mention:
            return ResponsibilityDecision(
                role=OwnershipRole.OBSERVER_ONLY,
                confidence=0.90,
                reason=f"User ({user_name}) is explicitly noted as included for visibility/FYI only in body",
                suppress_draft=True,
            )

        if first_name and len(first_name) > 2 and not is_user_observer_mention:
            if first_name in body_lower:
                user_named = True

        # We can't resolve other names without roster access, but we check
        # for direct email mentions or name tokens in the body
        for other in other_recipients:
            local_part = other.split("@")[0].replace(".", " ").replace("_", " ").lower()
            name_parts = [p for p in local_part.split() if len(p) > 2]
            for part in name_parts:
                if part in body_lower:
                    someone_else_named = True
                    break

        # If another recipient is named and user is not → observer
        if someone_else_named and not user_named:
            return ResponsibilityDecision(
                role=OwnershipRole.OBSERVER_ONLY,
                confidence=0.80,
                reason="Another To: recipient is specifically named in the email body",
                suppress_draft=True,
            )

        # Rule 3: Broadcast threshold
        if len(clean_to) >= broadcast_threshold and not user_named:
            return ResponsibilityDecision(
                role=OwnershipRole.OBSERVER_ONLY,
                confidence=0.75,
                reason=f"Broadcast email: {len(clean_to)} recipients in To: (threshold: {broadcast_threshold}), user not specifically addressed",
                suppress_draft=True,
            )

    # User is sole To: or is specifically named → primary actionee
    return None  # Fall through to default PRIMARY_ACTIONEE


# ═══════════════════════════════════════════════════════════════════════════════
# CHECK 3: Teammate "I'm on it" Detection
# ═══════════════════════════════════════════════════════════════════════════════

def check_teammate_handling(
    thread_history: List[dict],
    sender: str,
) -> Optional[ResponsibilityDecision]:
    """
    Detect if an internal colleague has already claimed ownership of this thread.

    Scans thread turns for commitment phrases from internal senders
    (e.g. "I'm looking into this", "I'll handle this", "Working on it now").
    """
    config = _get_delegation_config()
    if config and not config.teammate_handling.suppress_draft_if_internal_reply:
        return None

    if not thread_history:
        return None

    user_email = _get_user_email()
    sender_email = _clean_email(sender)

    commitment_patterns = [
        r"i(?:'m| am| will be) (?:looking into|handling|taking care of|working on)",
        r"i(?:'ll| will) (?:handle|take care of|look into|follow up|investigate)",
        r"(?:on it|handling (?:this |it )?now|working on (?:this |it )?now)",
        r"i(?:'ve| have) (?:already |just )?(?:started|begun|looked into|picked (?:this |it )?up)",
        r"let me (?:handle|take care of|look into|check on) (?:this|it)",
        r"i(?:'ll| will) (?:get back|respond|reply|revert) (?:to|on|about)",
    ]

    for turn in thread_history:
        turn_sender = _clean_email(turn.get("sender", ""))
        turn_body = (turn.get("body") or turn.get("snippet") or "").lower()

        # Skip the original external sender and the user themselves
        if turn_sender == sender_email or turn_sender == user_email:
            continue

        # Only count internal colleagues (same domain as user)
        if user_email and "@" in user_email:
            user_domain = user_email.split("@")[1]
            if "@" not in turn_sender or turn_sender.split("@")[1] != user_domain:
                continue

        # Check for commitment language
        for pattern in commitment_patterns:
            if re.search(pattern, turn_body):
                return ResponsibilityDecision(
                    role=OwnershipRole.TEAMMATE_HANDLING,
                    confidence=0.85,
                    reason=f"Internal colleague {turn_sender} committed to handling this in the thread",
                    suppress_draft=True,
                )

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# CHECK 4: Missing Information / Inferred Dependency
# ═══════════════════════════════════════════════════════════════════════════════

def check_missing_information(
    body: str,
    category: str,
    context_tags: List[str],
) -> Optional[ResponsibilityDecision]:
    """
    Detect when the email asks for information that requires internal consultation
    before a substantive reply can be drafted.

    Signals:
      - Body asks for delivery dates, custom pricing, capacity planning
      - Email references internal systems the user would need to check
      - Tags include indicators of cross-team dependency
    """
    if not body:
        return None

    config = _get_delegation_config()
    holding_reply = None
    if config:
        holding_reply = config.missing_information.default_holding_reply

    body_lower = body.lower()

    # Patterns that indicate the sender needs info the user can't answer alone
    dependency_patterns = [
        r"(?:what is|when (?:will|can)|could you (?:confirm|check|verify)) .*(?:delivery date|timeline|eta|deadline|ship date)",
        r"(?:need|require|request) .*(?:custom (?:pricing|quote)|bespoke|tailored|special) .*(?:proposal|pricing|rate|offer)",
        r"(?:can you|could you|please) .*(?:check with|ask|confirm with|consult) .*(?:engineering|finance|legal|team|operations|product)",
        r"(?:what is|do you have) .*(?:capacity|availability|bandwidth) .*(?:for|to handle|to take on)",
        r"(?:need|require) .*(?:approval|sign-off|authorization) .*(?:from|by) .*(?:manager|director|vp|cfo|cto|ceo)",
    ]

    for pattern in dependency_patterns:
        if re.search(pattern, body_lower):
            return ResponsibilityDecision(
                role=OwnershipRole.NEEDS_INTERNAL_INPUT,
                confidence=0.70,
                reason=f"Email requests information requiring internal consultation (pattern: {pattern[:50]})",
                suppress_draft=False,
                holding_reply=holding_reply,
            )

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN EVALUATOR — Public API
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate_ownership(
    sender: str,
    to_recipients: List[str],
    cc_recipients: List[str],
    body: str,
    auto_reply_headers: dict,
    category: str = "",
    context_tags: List[str] = None,
    thread_history: List[dict] = None,
) -> ResponsibilityDecision:
    """
    Main entry point — evaluate email ownership through all checks in priority order.

    Returns a ResponsibilityDecision that the pipeline uses to decide whether to
    generate a draft, delegate, or suppress.

    Check order (first match wins):
      1. OOO detection (hard block)
      2. Multi-To/CC disambiguation
      3. Teammate claim detection
      4. Missing information dependency
      5. Default: PRIMARY_ACTIONEE
    """
    context_tags = context_tags or []
    thread_history = thread_history or []

    # Check 1: OOO auto-responder (highest priority)
    ooo = check_ooo_sender(auto_reply_headers, body)
    if ooo:
        return ooo

    # Check 2: Recipient disambiguation
    recipient = check_recipient_role(to_recipients, cc_recipients, body, sender)
    if recipient:
        return recipient

    # Check 3: Teammate already handling
    teammate = check_teammate_handling(thread_history, sender)
    if teammate:
        return teammate

    # Check 4: Missing information
    missing = check_missing_information(body, category, context_tags)
    if missing:
        return missing

    # Default: User is the primary actionee
    return ResponsibilityDecision(
        role=OwnershipRole.PRIMARY_ACTIONEE,
        confidence=1.0,
        reason="User is the primary or sole addressee with no overriding delegation signals",
        suppress_draft=False,
    )
