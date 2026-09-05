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
Safety Rules Engine — Layer 1 pre-checks, VIP/No-Reply enforcement,
OOO loop prevention, and sensitive content lockdown.

V3 additions (Phase 5):
  • OOO Infinite Loop Shield (header + heuristic)
  • Sensitive Subpoena / Whistleblower Lockdown
  • False-Positive Phishing Shield
  • Multi-Topic Triage escalation

Loads configuration from:
  config/vip_rules.yaml    — VIP addresses, domains, no-reply patterns

Applied BEFORE LLM classification.
"""
import os
import re
import sys
from typing import Optional, List

try:
    import yaml
except ImportError:
    yaml = None

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.text_utils import detect_no_reply_sender, detect_vip_sender, has_critical_keyword

# Path resolution
_APP_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_DIR = os.path.join(_APP_DIR, '..', 'config')
_VIP_CONFIG = os.path.normpath(os.path.join(_CONFIG_DIR, 'vip_rules.yaml'))


def _load_yaml(path: str) -> dict:
    if yaml is None:
        print(f"[safety_rules] WARNING: PyYAML not installed. Cannot load {path}")
        return {}
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


_VIP_CONFIG_DATA: Optional[dict] = None


def _get_vip_config() -> dict:
    global _VIP_CONFIG_DATA
    if _VIP_CONFIG_DATA is None:
        _VIP_CONFIG_DATA = _load_yaml(_VIP_CONFIG)
    return _VIP_CONFIG_DATA


def run_pre_checks(sender: str, subject: str) -> dict:
    """
    Run all Layer 1 pre-checks on an incoming email.

    Returns a dict with:
      is_no_reply (bool)          — sender is automated / no-reply
      is_vip (bool)               — sender matches VIP rules
      has_critical_subject (bool) — subject contains a critical keyword
    """
    cfg = _get_vip_config()

    no_reply_patterns       = cfg.get('no_reply_patterns', [])
    vip_addresses           = cfg.get('vip_addresses', [])
    vip_domains             = cfg.get('vip_domains', [])
    critical_keywords       = cfg.get('critical_subject_keywords', [])

    is_no_reply      = detect_no_reply_sender(sender, no_reply_patterns)
    is_vip           = detect_vip_sender(sender, vip_addresses, vip_domains)
    critical_subject = has_critical_keyword(subject, critical_keywords)

    return {
        'is_no_reply':           is_no_reply,
        'is_vip':                is_vip,
        'has_critical_subject':  critical_subject,
    }


def enforce_vip_constraints(state: dict) -> dict:
    """
    Post-classification VIP enforcement.

    If is_vip=True, ensure:
      - gmail_actions does not contain remove_inbox, safe_archive, or move_to_trash.
      - apply_label @VIP is added.

    Returns updated gmail_actions list.
    """
    if not state.get('is_vip'):
        return {'gmail_actions': state.get('gmail_actions', [])}

    blocked = {'remove_inbox', 'safe_archive', 'move_to_trash'}
    safe_actions = [
        a for a in state.get('gmail_actions', [])
        if a.get('action') not in blocked
    ]

    # Ensure @VIP label is applied
    labels = [a.get('label') for a in safe_actions if a.get('action') == 'apply_label']
    if '@VIP' not in labels:
        safe_actions.insert(0, {'action': 'apply_label', 'label': '@VIP'})

    return {'gmail_actions': safe_actions}


# ═══════════════════════════════════════════════════════════════════════════════
# V3 Phase 5: OOO Infinite Loop Shield
# ═══════════════════════════════════════════════════════════════════════════════

def detect_ooo_auto_reply(auto_reply_headers: dict, body: str = "") -> bool:
    """
    Detect if an email is an Out-of-Office auto-reply.

    Uses two detection layers:
      Layer A: RFC 3834 header-based detection (deterministic, most reliable)
      Layer B: Body text heuristic patterns (fallback)

    Returns True if the email is detected as an OOO auto-reply.
    """
    if not auto_reply_headers:
        auto_reply_headers = {}

    # Layer A: Header-based detection
    auto_submitted = (auto_reply_headers.get("auto_submitted") or "").lower().strip()
    if auto_submitted in ("auto-replied", "auto-generated", "auto-notified"):
        return True

    x_auto_suppress = (auto_reply_headers.get("x_auto_response_suppress") or "").lower().strip()
    if x_auto_suppress and x_auto_suppress != "none":
        return True

    precedence = (auto_reply_headers.get("precedence") or "").lower().strip()
    if precedence in ("bulk", "junk"):
        return True

    x_autoreply = (auto_reply_headers.get("x_autoreply") or "").lower().strip()
    if x_autoreply in ("yes", "true", "1"):
        return True

    # Layer B: Body text heuristics
    if body:
        body_lower = body.lower()
        ooo_patterns = [
            r"i am out of (?:the )?office",
            r"i(?:'m| am) (?:currently )?(?:away|on vacation|on leave|on pto)",
            r"i will (?:be )?(?:out of office|away from|unavailable)",
            r"this is an? auto(?:matic|mated)?\s*(?:reply|response)",
            r"i (?:will|shall) (?:return|be back) (?:on|by)",
        ]
        for pattern in ooo_patterns:
            if re.search(pattern, body_lower):
                return True

    return False


def enforce_ooo_safety(state: dict) -> dict:
    """
    OOO Loop Prevention: If the sender is an OOO auto-responder,
    hard-block all draft creation to prevent infinite reply loops.

    Returns updated gmail_actions with create_draft_reply stripped.
    """
    auto_reply_headers = state.get("auto_reply_headers", {})
    body = state.get("body", "")

    if not detect_ooo_auto_reply(auto_reply_headers, body):
        return {"gmail_actions": state.get("gmail_actions", [])}

    # Strip all draft creation actions
    safe_actions = [
        a for a in state.get("gmail_actions", [])
        if a.get("action") != "create_draft_reply"
    ]

    # Add OOO label for visibility
    has_ooo_label = any(
        a.get("action") == "apply_label" and a.get("label") == "@OOO_AutoReply"
        for a in safe_actions
    )
    if not has_ooo_label:
        safe_actions.insert(0, {"action": "apply_label", "label": "@OOO_AutoReply"})

    return {"gmail_actions": safe_actions}


# ═══════════════════════════════════════════════════════════════════════════════
# V3 Phase 5: Sensitive Content Lockdown
# ═══════════════════════════════════════════════════════════════════════════════

# Patterns that indicate extremely sensitive content requiring human-only handling
_SENSITIVE_PATTERNS = [
    # Legal subpoenas and court orders
    r"(?:court\s+order|subpoena|legal\s+hold|litigation\s+hold|discovery\s+request)",
    # Whistleblower and ethics reports
    r"(?:whistleblower|ethics\s+hotline|anonymous\s+report|integrity\s+concern)",
    # HR investigations and terminations
    r"(?:termination\s+(?:notice|letter)|sexual\s+harassment|hostile\s+work\s+environment)",
    # Confidential M&A and board matters
    r"(?:material\s+non-public|insider\s+(?:information|trading)|board\s+(?:confidential|resolution))",
    # Government regulatory actions
    r"(?:cease\s+and\s+desist|enforcement\s+action|regulatory\s+investigation)",
]

_SENSITIVE_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in _SENSITIVE_PATTERNS]


def detect_sensitive_content(subject: str, body: str) -> Optional[str]:
    """
    Detect if an email contains sensitive legal, HR, or regulatory content
    that must NOT be auto-drafted.

    Returns the matched pattern description if sensitive, None otherwise.
    """
    text = f"{subject} {body}"
    for i, pattern in enumerate(_SENSITIVE_PATTERNS_COMPILED):
        if pattern.search(text):
            return _SENSITIVE_PATTERNS[i][:60]
    return None


def enforce_sensitive_lockdown(state: dict) -> dict:
    """
    Sensitive Content Lockdown: If the email contains legal/HR/regulatory
    sensitive content, block all draft creation and route to confidential review.

    Returns updated gmail_actions.
    """
    subject = state.get("subject", "")
    body = state.get("body", "")

    matched = detect_sensitive_content(subject, body)
    if not matched:
        return {"gmail_actions": state.get("gmail_actions", [])}

    # Strip all draft actions
    safe_actions = [
        a for a in state.get("gmail_actions", [])
        if a.get("action") != "create_draft_reply"
    ]

    # Add confidential review label
    has_label = any(
        a.get("action") == "apply_label" and a.get("label") == "@Confidential_Review"
        for a in safe_actions
    )
    if not has_label:
        safe_actions.insert(0, {"action": "apply_label", "label": "@Confidential_Review"})

    # Ensure it stays in inbox for manual handling
    safe_actions = [a for a in safe_actions if a.get("action") not in {"remove_inbox", "safe_archive", "move_to_trash"}]
    if not any(a.get("action") == "keep_inbox" for a in safe_actions):
        safe_actions.append({"action": "keep_inbox"})

    return {"gmail_actions": safe_actions}


# ═══════════════════════════════════════════════════════════════════════════════
# V3 Phase 5: False-Positive Phishing Shield
# ═══════════════════════════════════════════════════════════════════════════════

# Known legitimate infrastructure notification domains
_LEGITIMATE_INFRA_DOMAINS = [
    "amazonaws.com", "aws.amazon.com", "console.aws.amazon.com",
    "google.com", "cloud.google.com", "accounts.google.com",
    "datadoghq.com", "pagerduty.com", "opsgenie.com",
    "github.com", "gitlab.com", "bitbucket.org",
    "sentry.io", "newrelic.com", "splunk.com",
    "circleci.com", "travis-ci.com", "jenkins.io",
    "stripe.com", "twilio.com", "sendgrid.net",
]


def is_legitimate_infra_sender(sender: str) -> bool:
    """
    Check if a sender is from a known legitimate infrastructure/cloud domain.
    Prevents misclassification of real AWS/GCP/monitoring alerts as phishing.
    """
    if not sender:
        return False
    sender_lower = sender.lower()
    return any(domain in sender_lower for domain in _LEGITIMATE_INFRA_DOMAINS)
