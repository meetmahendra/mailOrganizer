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
Unit Tests for Organization Model, Persona Resolver, and Departmental Routing.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))

from services.org_context_service import (
    resolve_sender_persona,
    is_org_vip,
    get_department_labels,
    resolve_active_projects,
    build_org_context_for_prompt,
)


class TestOrgModel(unittest.TestCase):

    def test_internal_persona_resolution(self):
        """Verify employee lookup returns correct role, hierarchy, and department."""
        persona = resolve_sender_persona("arjun.mehta@yourcompany.com")
        self.assertIsNotNone(persona)
        self.assertEqual(persona["name"], "Arjun Mehta")
        self.assertEqual(persona["title"], "Principal Tech Lead — Core Payments")
        self.assertEqual(persona["department"], "Engineering")
        self.assertEqual(persona["hierarchy_level"], "LEAD_MANAGER")

    def test_strategic_client_persona_resolution(self):
        """Verify client contact lookup returns company name, tier, and VIP status."""
        persona = resolve_sender_persona("david.chen@yourclient.com")
        self.assertIsNotNone(persona)
        self.assertEqual(persona["company_name"], "Apex Global Financial")
        self.assertEqual(persona["tier"], "TIER_1_VIP")
        self.assertTrue(persona["is_vip"])

    def test_department_labels_resolution(self):
        """Verify department labels are resolved for routing."""
        labels = get_department_labels("sarah.jenkins@yourcompany.com")
        self.assertIn("Dept/SRE", labels)

    def test_active_project_matching(self):
        """Verify strategic project matching by name and code."""
        text = "Regarding our rollout for Project Apollo and the Stripe migration."
        projects = resolve_active_projects(text)
        self.assertTrue(len(projects) >= 1)
        self.assertEqual(projects[0]["code"], "PROJECT_APOLLO")

    def test_org_context_prompt_formatting(self):
        """Verify prompt enrichment block includes all pertinent details."""
        block = build_org_context_for_prompt(
            "marcus.vance@yourcompany.com",
            "Project Apollo Review",
            "Please check the payments latency."
        )
        self.assertIn("Chief Technology Officer", block)
        self.assertIn("Project Apollo", block)
        self.assertIn("VIP Priority Status: YES", block)


if __name__ == "__main__":
    unittest.main()
