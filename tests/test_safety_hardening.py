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
Unit tests for Phase 5 Safety Hardening.

Tests OOO loop prevention, sensitive content lockdown, and false-positive
phishing shield independently.
"""
import os
import sys
import unittest

# Ensure app/ is on the path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app'))

from pipeline.safety_rules import (
    detect_ooo_auto_reply,
    enforce_ooo_safety,
    detect_sensitive_content,
    enforce_sensitive_lockdown,
    is_legitimate_infra_sender,
)


class TestOOOLoopPrevention(unittest.TestCase):
    """Test OOO auto-reply detection and loop prevention."""

    def test_auto_submitted_header_detected(self):
        """Auto-Submitted: auto-replied is detected."""
        self.assertTrue(detect_ooo_auto_reply({"auto_submitted": "auto-replied"}))

    def test_auto_submitted_auto_generated(self):
        """Auto-Submitted: auto-generated is detected."""
        self.assertTrue(detect_ooo_auto_reply({"auto_submitted": "auto-generated"}))

    def test_x_auto_response_suppress_oof(self):
        """X-Auto-Response-Suppress: OOF is detected."""
        self.assertTrue(detect_ooo_auto_reply({"x_auto_response_suppress": "OOF"}))

    def test_x_autoreply_yes(self):
        """X-Autoreply: yes is detected."""
        self.assertTrue(detect_ooo_auto_reply({"x_autoreply": "yes"}))

    def test_precedence_bulk(self):
        """Precedence: bulk is detected."""
        self.assertTrue(detect_ooo_auto_reply({"precedence": "bulk"}))

    def test_normal_precedence_not_detected(self):
        """Precedence: normal is not detected."""
        self.assertFalse(detect_ooo_auto_reply({"precedence": "normal"}))

    def test_body_out_of_office(self):
        """Body 'I am out of the office' is detected."""
        self.assertTrue(detect_ooo_auto_reply(
            {}, "Hi, I am out of the office until next Monday."
        ))

    def test_body_on_vacation(self):
        """Body 'I'm currently on vacation' is detected."""
        self.assertTrue(detect_ooo_auto_reply(
            {}, "Thanks for your email. I'm currently on vacation."
        ))

    def test_body_automatic_reply(self):
        """Body 'This is an automatic reply' is detected."""
        self.assertTrue(detect_ooo_auto_reply(
            {}, "This is an automatic reply to let you know I'm away."
        ))

    def test_normal_body_not_detected(self):
        """Normal email body is not detected as OOO."""
        self.assertFalse(detect_ooo_auto_reply(
            {}, "Hi Marcus, can we discuss the Q4 roadmap?"
        ))

    def test_empty_inputs_not_detected(self):
        """Empty headers and body returns False."""
        self.assertFalse(detect_ooo_auto_reply({}, ""))

    def test_enforce_ooo_strips_draft(self):
        """enforce_ooo_safety strips create_draft_reply and adds @OOO_AutoReply label."""
        state = {
            "auto_reply_headers": {"auto_submitted": "auto-replied"},
            "body": "",
            "gmail_actions": [
                {"action": "apply_label", "label": "@Action"},
                {"action": "create_draft_reply"},
                {"action": "keep_inbox"},
            ],
        }
        result = enforce_ooo_safety(state)
        actions = result["gmail_actions"]

        # Draft should be stripped
        action_types = [a["action"] for a in actions]
        self.assertNotIn("create_draft_reply", action_types)

        # OOO label should be present
        labels = [a.get("label") for a in actions if a.get("action") == "apply_label"]
        self.assertIn("@OOO_AutoReply", labels)

    def test_enforce_ooo_no_change_for_normal(self):
        """enforce_ooo_safety does not modify actions for normal emails."""
        state = {
            "auto_reply_headers": {},
            "body": "Normal email",
            "gmail_actions": [
                {"action": "create_draft_reply"},
                {"action": "apply_label", "label": "@Action"},
            ],
        }
        result = enforce_ooo_safety(state)
        action_types = [a["action"] for a in result["gmail_actions"]]
        self.assertIn("create_draft_reply", action_types)


class TestSensitiveContentLockdown(unittest.TestCase):
    """Test sensitive content detection and lockdown."""

    def test_subpoena_detected(self):
        """Subject/body with 'subpoena' is detected."""
        result = detect_sensitive_content("Legal Notice", "You are hereby served a subpoena for records.")
        self.assertIsNotNone(result)

    def test_court_order_detected(self):
        """Subject/body with 'court order' is detected."""
        result = detect_sensitive_content("Urgent Court Order", "Pursuant to this court order...")
        self.assertIsNotNone(result)

    def test_whistleblower_detected(self):
        """Subject/body with 'whistleblower' is detected."""
        result = detect_sensitive_content("Confidential", "This is a whistleblower report regarding...")
        self.assertIsNotNone(result)

    def test_litigation_hold_detected(self):
        """Subject/body with 'litigation hold' is detected."""
        result = detect_sensitive_content("Notice", "Please preserve all documents per this litigation hold.")
        self.assertIsNotNone(result)

    def test_sexual_harassment_detected(self):
        """HR sensitive content detected."""
        result = detect_sensitive_content("HR Complaint", "Report regarding sexual harassment incident.")
        self.assertIsNotNone(result)

    def test_cease_and_desist_detected(self):
        """Regulatory cease and desist detected."""
        result = detect_sensitive_content("Legal", "We are issuing a cease and desist notice.")
        self.assertIsNotNone(result)

    def test_normal_legal_not_detected(self):
        """Normal legal discussion is not flagged."""
        result = detect_sensitive_content("Contract Review", "Please review the attached NDA.")
        self.assertIsNone(result)

    def test_normal_email_not_detected(self):
        """Normal business email is not flagged."""
        result = detect_sensitive_content("Q4 Planning", "Let's discuss the roadmap for next quarter.")
        self.assertIsNone(result)

    def test_enforce_sensitive_strips_draft(self):
        """enforce_sensitive_lockdown strips drafts and adds @Confidential_Review."""
        state = {
            "subject": "Subpoena Notice",
            "body": "You are served with a subpoena for document production.",
            "gmail_actions": [
                {"action": "create_draft_reply"},
                {"action": "apply_label", "label": "@Action"},
                {"action": "remove_inbox"},
            ],
        }
        result = enforce_sensitive_lockdown(state)
        actions = result["gmail_actions"]

        action_types = [a["action"] for a in actions]
        self.assertNotIn("create_draft_reply", action_types)
        self.assertNotIn("remove_inbox", action_types)

        labels = [a.get("label") for a in actions if a.get("action") == "apply_label"]
        self.assertIn("@Confidential_Review", labels)

        self.assertIn("keep_inbox", action_types)

    def test_enforce_sensitive_no_change_for_normal(self):
        """enforce_sensitive_lockdown does not modify normal emails."""
        state = {
            "subject": "Team Sync",
            "body": "Let's meet at 3pm.",
            "gmail_actions": [
                {"action": "create_draft_reply"},
            ],
        }
        result = enforce_sensitive_lockdown(state)
        action_types = [a["action"] for a in result["gmail_actions"]]
        self.assertIn("create_draft_reply", action_types)


class TestPhishingShield(unittest.TestCase):
    """Test false-positive phishing shield for infrastructure senders."""

    def test_aws_sender_legitimate(self):
        """AWS notification sender is recognized as legitimate."""
        self.assertTrue(is_legitimate_infra_sender("no-reply@amazonaws.com"))

    def test_gcp_sender_legitimate(self):
        """GCP notification sender is recognized as legitimate."""
        self.assertTrue(is_legitimate_infra_sender("alerts@cloud.google.com"))

    def test_datadog_sender_legitimate(self):
        """Datadog alert sender is recognized as legitimate."""
        self.assertTrue(is_legitimate_infra_sender("alert@datadoghq.com"))

    def test_pagerduty_sender_legitimate(self):
        """PagerDuty sender is recognized as legitimate."""
        self.assertTrue(is_legitimate_infra_sender("notifications@pagerduty.com"))

    def test_github_sender_legitimate(self):
        """GitHub notification is recognized as legitimate."""
        self.assertTrue(is_legitimate_infra_sender("noreply@github.com"))

    def test_unknown_domain_not_legitimate(self):
        """Unknown domain is not recognized as legitimate."""
        self.assertFalse(is_legitimate_infra_sender("phisher@evil-domain.com"))

    def test_empty_sender_not_legitimate(self):
        """Empty sender is not recognized as legitimate."""
        self.assertFalse(is_legitimate_infra_sender(""))


if __name__ == '__main__':
    unittest.main()
