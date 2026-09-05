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
Unit Tests for Deterministic Rules Engine and VIP/No-Reply Safety Safeguards.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))

from pipeline.safety_rules import run_pre_checks, enforce_vip_constraints
from pipeline.rules_engine import get_actions_for_category
from services.org_context_service import is_org_vip, get_department_labels


class TestRulesAndSafety(unittest.TestCase):

    def test_vip_address_detection(self):
        """Verify VIP email detection matches exact address and roster."""
        checks = run_pre_checks("boss@yourcompany.com", "Project Status")
        self.assertTrue(checks["is_vip"])
        
        # Test C-Suite roster VIP
        self.assertTrue(is_org_vip("victoria.sterling@yourcompany.com"))
        self.assertTrue(is_org_vip("marcus.vance@yourcompany.com"))

    def test_vip_domain_detection(self):
        """Verify VIP domain detection matches customer domains."""
        checks = run_pre_checks("david.chen@yourclient.com", "Urgent API Question")
        self.assertTrue(checks["is_vip"])

    def test_vip_action_constraint_enforcement(self):
        """Verify VIP emails NEVER get archived or trashed, and always receive @VIP label."""
        state = {
            "is_vip": True,
            "gmail_actions": [
                {"action": "remove_inbox"},
                {"action": "safe_archive", "label": "_LLM/Promotions"},
                {"action": "mark_as_read"},
            ]
        }
        res = enforce_vip_constraints(state)
        actions = res["gmail_actions"]
        
        # Must not contain remove_inbox or safe_archive
        action_names = [a.get("action") for a in actions]
        self.assertNotIn("remove_inbox", action_names)
        self.assertNotIn("safe_archive", action_names)
        
        # Must contain @VIP label
        labels = [a.get("label") for a in actions if a.get("action") == "apply_label"]
        self.assertIn("@VIP", labels)

    def test_no_reply_suppresses_draft(self):
        """Verify automated no-reply senders suppress draft reply creation."""
        checks = run_pre_checks("no-reply@mailer.amazon.com", "Your Order Has Shipped")
        self.assertTrue(checks["is_no_reply"])

        state = {
            "is_no_reply": True,
            "is_reply_necessary": False,
        }
        actions = get_actions_for_category("Action Required (High)", state)
        action_names = [a.get("action") for a in actions]
        self.assertNotIn("create_draft_reply", action_names)

    def test_critical_keyword_detection(self):
        """Verify critical subject keywords are flagged in Layer 1 pre-checks."""
        checks = run_pre_checks("eng@yourcompany.com", "[P0 INCIDENT] Production Database Down")
        self.assertTrue(checks["has_critical_subject"])


if __name__ == "__main__":
    unittest.main()
