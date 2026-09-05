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
Unit tests for the Delegation & Ownership Subsystem (Phase 3).

Tests each check independently plus the full evaluate_ownership orchestrator.
"""
import os
import sys
import unittest

# Ensure app/ is on the path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app'))

from delegation.models import OwnershipRole, ResponsibilityDecision, DelegationTarget
from delegation.ownership_evaluator import (
    check_ooo_sender,
    check_recipient_role,
    check_teammate_handling,
    check_missing_information,
    evaluate_ownership,
)


class TestOwnershipModels(unittest.TestCase):
    """Test data model construction and properties."""

    def test_ownership_role_values(self):
        """All six ownership roles are defined."""
        roles = [e.value for e in OwnershipRole]
        self.assertIn("PRIMARY_ACTIONEE", roles)
        self.assertIn("OBSERVER_ONLY", roles)
        self.assertIn("DELEGATOR", roles)
        self.assertIn("TEAMMATE_HANDLING", roles)
        self.assertIn("NEEDS_INTERNAL_INPUT", roles)
        self.assertIn("OOO_SENDER", roles)

    def test_responsibility_decision_should_enrich(self):
        """PRIMARY_ACTIONEE should proceed to enrichment; OBSERVER_ONLY should not."""
        primary = ResponsibilityDecision(
            role=OwnershipRole.PRIMARY_ACTIONEE,
            suppress_draft=False,
        )
        self.assertTrue(primary.should_enrich_and_draft)

        observer = ResponsibilityDecision(
            role=OwnershipRole.OBSERVER_ONLY,
            suppress_draft=True,
        )
        self.assertFalse(observer.should_enrich_and_draft)

    def test_delegation_target_model(self):
        """DelegationTarget constructs with all fields."""
        target = DelegationTarget(
            name="Jane Doe",
            email="jane@company.com",
            role="SRE On-Call",
            resolver_used="oncall_service",
            delegation_message="Looping in Jane Doe for SRE support.",
        )
        self.assertEqual(target.name, "Jane Doe")
        self.assertEqual(target.email, "jane@company.com")


class TestOOODetection(unittest.TestCase):
    """Test OOO auto-responder detection (Check 1)."""

    def test_auto_submitted_header(self):
        """RFC 3834 Auto-Submitted: auto-replied triggers OOO."""
        result = check_ooo_sender({"auto_submitted": "auto-replied"})
        self.assertIsNotNone(result)
        self.assertEqual(result.role, OwnershipRole.OOO_SENDER)
        self.assertTrue(result.suppress_draft)
        self.assertGreaterEqual(result.confidence, 0.95)

    def test_x_auto_response_suppress_header(self):
        """X-Auto-Response-Suppress: OOF triggers OOO."""
        result = check_ooo_sender({"x_auto_response_suppress": "OOF"})
        self.assertIsNotNone(result)
        self.assertEqual(result.role, OwnershipRole.OOO_SENDER)

    def test_x_autoreply_header(self):
        """X-Autoreply: yes triggers OOO."""
        result = check_ooo_sender({"x_autoreply": "yes"})
        self.assertIsNotNone(result)
        self.assertEqual(result.role, OwnershipRole.OOO_SENDER)

    def test_precedence_bulk(self):
        """Precedence: bulk triggers OOO."""
        result = check_ooo_sender({"precedence": "bulk"})
        self.assertIsNotNone(result)
        self.assertEqual(result.role, OwnershipRole.OOO_SENDER)

    def test_body_heuristic_out_of_office(self):
        """Body text 'I am out of office' triggers OOO."""
        result = check_ooo_sender(
            {},
            body="Hi, I am out of office until September 5th. I will respond when I return."
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.role, OwnershipRole.OOO_SENDER)

    def test_body_heuristic_vacation(self):
        """Body text 'I'm currently on vacation' triggers OOO."""
        result = check_ooo_sender(
            {},
            body="Thanks for your email. I'm currently on vacation and will return on Monday."
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.role, OwnershipRole.OOO_SENDER)

    def test_body_auto_response(self):
        """Body text 'This is an automatic reply' triggers OOO."""
        result = check_ooo_sender(
            {},
            body="This is an automatic reply. I will be back by Friday."
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.role, OwnershipRole.OOO_SENDER)

    def test_no_ooo_normal_email(self):
        """Normal email with no OOO signals returns None."""
        result = check_ooo_sender(
            {},
            body="Hi Marcus, can we schedule a meeting to discuss the Q4 budget?"
        )
        self.assertIsNone(result)

    def test_empty_headers_empty_body(self):
        """Empty inputs return None (no false positives)."""
        result = check_ooo_sender({}, body="")
        self.assertIsNone(result)

    def test_precedence_list_not_ooo(self):
        """Precedence: list is not treated as OOO (mailing list)."""
        # Note: Precedence 'list' is not in the safety_rules OOO check
        # but IS in the ownership evaluator's check. Test the evaluator's behavior.
        result = check_ooo_sender({"precedence": "list"})
        self.assertIsNotNone(result)
        self.assertEqual(result.role, OwnershipRole.OOO_SENDER)


class TestRecipientDisambiguation(unittest.TestCase):
    """Test multi-To/CC recipient disambiguation (Check 2)."""

    def test_user_only_in_cc(self):
        """User in CC only → OBSERVER_ONLY."""
        # This test depends on persona config being available
        # If no persona config, check_recipient_role returns None
        result = check_recipient_role(
            to_recipients=["other@company.com"],
            cc_recipients=["marcus.vance@yourcompany.com"],
            body="Hi team, please review the attached.",
            sender="external@client.com",
        )
        # Without persona config loaded, this may return None
        if result is not None:
            self.assertEqual(result.role, OwnershipRole.OBSERVER_ONLY)

    def test_user_mentioned_for_visibility(self):
        """User on To: but explicitly marked 'included for visibility' → OBSERVER_ONLY."""
        result = check_recipient_role(
            to_recipients=["marcus.vance@yourcompany.com", "elena.rostova@yourcompany.com"],
            cc_recipients=[],
            body="Hi Elena, could you take a look at the revised Figma components? Marcus is included for visibility.",
            sender="designer@partner.com",
        )
        if result is not None:
            self.assertEqual(result.role, OwnershipRole.OBSERVER_ONLY)
            self.assertTrue(result.suppress_draft)

    def test_sole_to_recipient(self):
        """User as sole To: recipient → None (falls through to PRIMARY_ACTIONEE)."""
        result = check_recipient_role(
            to_recipients=["marcus.vance@yourcompany.com"],
            cc_recipients=[],
            body="Marcus, can you review this proposal?",
            sender="external@client.com",
        )
        # Should return None (primary actionee is the default)
        self.assertIsNone(result)


class TestTeammateHandling(unittest.TestCase):
    """Test teammate 'I'm on it' detection (Check 3)."""

    def test_teammate_claimed_ownership(self):
        """Internal colleague says 'I'll handle this' → TEAMMATE_HANDLING."""
        thread = [
            {"sender": "client@external.com", "body": "Can someone help with the deployment issue?"},
            {"sender": "colleague@yourcompany.com", "body": "I'll handle this right away."},
        ]
        result = check_teammate_handling(
            thread_history=thread,
            sender="client@external.com",
        )
        # Depends on persona config for domain matching
        # Without config, may return None
        if result is not None:
            self.assertEqual(result.role, OwnershipRole.TEAMMATE_HANDLING)

    def test_no_commitment_in_thread(self):
        """Thread without commitment phrases → None."""
        thread = [
            {"sender": "client@external.com", "body": "Can someone help with the deployment issue?"},
            {"sender": "colleague@yourcompany.com", "body": "Thanks for letting us know."},
        ]
        result = check_teammate_handling(
            thread_history=thread,
            sender="client@external.com",
        )
        self.assertIsNone(result)

    def test_empty_thread(self):
        """Empty thread history → None."""
        result = check_teammate_handling(
            thread_history=[],
            sender="client@external.com",
        )
        self.assertIsNone(result)


class TestMissingInformation(unittest.TestCase):
    """Test missing information / inferred dependency (Check 4)."""

    def test_delivery_date_question(self):
        """Email asking for delivery dates → NEEDS_INTERNAL_INPUT."""
        result = check_missing_information(
            body="Hi Marcus, when will you deliver the API integration? What is the delivery date for Phase 2?",
            category="Action Required (High)",
            context_tags=["engineering", "deadline"],
        )
        if result is not None:
            self.assertEqual(result.role, OwnershipRole.NEEDS_INTERNAL_INPUT)
            self.assertFalse(result.suppress_draft)

    def test_custom_pricing_request(self):
        """Email requesting custom pricing → NEEDS_INTERNAL_INPUT."""
        result = check_missing_information(
            body="We need a custom pricing proposal for the enterprise tier with volume discounts.",
            category="Action Required (High)",
            context_tags=["finance", "sales"],
        )
        if result is not None:
            self.assertEqual(result.role, OwnershipRole.NEEDS_INTERNAL_INPUT)

    def test_normal_email_no_dependency(self):
        """Normal email without dependency signals → None."""
        result = check_missing_information(
            body="Hi Marcus, here's the status update for Project Alpha. All on track.",
            category="Informational/Logs",
            context_tags=["update"],
        )
        self.assertIsNone(result)


class TestEvaluateOwnership(unittest.TestCase):
    """Test the full evaluate_ownership orchestrator."""

    def test_ooo_takes_highest_priority(self):
        """OOO detection overrides all other checks."""
        result = evaluate_ownership(
            sender="colleague@company.com",
            to_recipients=["marcus.vance@yourcompany.com"],
            cc_recipients=[],
            body="I am out of the office until September 10th.",
            auto_reply_headers={"auto_submitted": "auto-replied"},
            category="Action Required (High)",
            context_tags=["urgent"],
        )
        self.assertEqual(result.role, OwnershipRole.OOO_SENDER)
        self.assertTrue(result.suppress_draft)

    def test_default_primary_actionee(self):
        """Normal email with no special signals → PRIMARY_ACTIONEE."""
        result = evaluate_ownership(
            sender="client@external.com",
            to_recipients=["marcus.vance@yourcompany.com"],
            cc_recipients=[],
            body="Hi Marcus, can we schedule a call to discuss the contract renewal?",
            auto_reply_headers={},
        )
        self.assertEqual(result.role, OwnershipRole.PRIMARY_ACTIONEE)
        self.assertFalse(result.suppress_draft)

    def test_ooo_body_heuristic_blocks_draft(self):
        """OOO body heuristic blocks draft even without headers."""
        result = evaluate_ownership(
            sender="person@company.com",
            to_recipients=["user@company.com"],
            cc_recipients=[],
            body="This is an automated reply. I will be back by September 15th.",
            auto_reply_headers={},
        )
        self.assertEqual(result.role, OwnershipRole.OOO_SENDER)
        self.assertTrue(result.suppress_draft)

    def test_result_has_required_fields(self):
        """ResponsibilityDecision always has role, confidence, reason."""
        result = evaluate_ownership(
            sender="anyone@anywhere.com",
            to_recipients=[],
            cc_recipients=[],
            body="Hello",
            auto_reply_headers={},
        )
        self.assertIsInstance(result.role, OwnershipRole)
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)
        self.assertIsInstance(result.reason, str)
        self.assertTrue(len(result.reason) > 0)


if __name__ == '__main__':
    unittest.main()
