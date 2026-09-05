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
Unit Tests for Phase 1 (Config Schemas) and Phase 2 (Connectors Subsystem).
"""
import os
import sys
import unittest

# Ensure project root is on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, 'app'))

from config.schemas import (
    validate_all_configs,
    ConnectorsConfig,
    DelegationPoliciesConfig,
    UserPersonaConfig,
    ExternalRAGConfig,
    RoutingRule,
)
from connectors.base_connector import FactItem, MutationResult, BaseConnector
from connectors.calendar_connector import CalendarConnector
from connectors.gmail_search_connector import GmailSearchConnector
from connectors.rag_connector import RAGConnector
from connectors.mcp_connector import MCPConnector
from connectors.connector_manager import ConnectorManager


class TestConfigSchemas(unittest.TestCase):
    """Test Pydantic configuration schemas and validation."""

    def test_validate_all_configs_loads_cleanly(self):
        """Verify that the real config files in config/ validate without error."""
        results = validate_all_configs()
        self.assertIn('connectors', results)
        self.assertIn('delegation', results)
        self.assertIn('persona', results)
        self.assertIsInstance(results['connectors'], ConnectorsConfig)
        self.assertIsInstance(results['delegation'], DelegationPoliciesConfig)
        self.assertIsInstance(results['persona'], UserPersonaConfig)

    def test_connectors_config_routing_rules(self):
        """Verify routing rules structure and validation."""
        cfg = ConnectorsConfig(
            routing_rules=[
                RoutingRule(tags=["meeting", "calendar"], connectors=["calendar"]),
                RoutingRule(tags=["invoice"], connectors=["erp_financial"]),
            ]
        )
        self.assertEqual(len(cfg.routing_rules), 2)
        self.assertEqual(cfg.routing_rules[0].connectors, ["calendar"])

    def test_user_persona_validation(self):
        """Verify user persona schema fields."""
        persona = UserPersonaConfig(
            name="Alice Smith",
            title="VP Engineering",
            organization="Acme Corp",
            signature="Best,\nAlice"
        )
        self.assertEqual(persona.name, "Alice Smith")
        self.assertEqual(persona.title, "VP Engineering")


class TestConnectors(unittest.TestCase):
    """Test pluggable connector implementations."""

    def test_fact_item_bullet_formatting(self):
        """Verify FactItem formatting."""
        item = FactItem(
            source="Calendar",
            content="Free Friday 10 AM",
            timestamp="Tomorrow"
        )
        bullet = item.to_bullet()
        self.assertIn("[Calendar]", bullet)
        self.assertIn("Free Friday 10 AM", bullet)
        self.assertIn("(Tomorrow)", bullet)

    def test_calendar_connector_mock_query(self):
        """Verify CalendarConnector in mock mode."""
        conn = CalendarConnector(
            connector_id="calendar",
            config={"provider": "mock", "enabled": True}
        )
        self.assertTrue(conn.is_available())
        facts = conn.query("availability")
        self.assertTrue(len(facts) > 0)
        self.assertEqual(facts[0].source, "Calendar")

    def test_gmail_search_connector_mock(self):
        """Verify GmailSearchConnector with mock history."""
        mock_data = [
            {"summary": "Agreed to 15% discount on annual commit", "date": "June 14"}
        ]
        conn = GmailSearchConnector(
            connector_id="gmail_search",
            config={"enabled": True, "mock_history": mock_data}
        )
        self.assertTrue(conn.is_available())
        facts = conn.query("pricing")
        self.assertEqual(len(facts), 1)
        self.assertIn("15% discount", facts[0].content)

    def test_gmail_search_connector_filters_current_msg(self):
        """Verify GmailSearchConnector excludes the current incoming email ID."""
        mock_data = [
            {"summary": "Current email snippet", "date": "Today", "gmail_id": "msg_123"},
            {"summary": "Past agreement on discounts", "date": "Last week", "gmail_id": "msg_001"},
        ]
        conn = GmailSearchConnector(
            connector_id="gmail_search",
            config={"enabled": True, "mock_history": mock_data}
        )
        facts = conn.query("agreement", current_msg_id="msg_123")
        self.assertEqual(len(facts), 1)
        self.assertIn("Past agreement", facts[0].content)
        self.assertNotIn("Current email", facts[0].content)

    def test_rag_connector_mock_facts(self):
        """Verify RAGConnector returns configured mock excerpts."""
        mock_facts = [
            "Core SLA guarantees 99.9% uptime with 1-hour response for P0 incidents.",
            "Standard refund policy is 30 days from purchase."
        ]
        conn = RAGConnector(
            connector_id="engineering_docs_rag",
            config={"mock_facts": mock_facts}
        )
        self.assertTrue(conn.is_available())
        facts = conn.query("SLA policy")
        self.assertEqual(len(facts), 2)
        self.assertIn("99.9% uptime", facts[0].content)

    def test_mcp_connector_mock_facts(self):
        """Verify MCPConnector returns configured mock tool facts."""
        conn = MCPConnector(
            connector_id="jira_mcp",
            config={"mock_facts": ["Ticket APOLLO-104 is currently In Progress assigned to Arjun Mehta."]}
        )
        self.assertTrue(conn.is_available())
        facts = conn.query("ticket APOLLO-104")
        self.assertEqual(len(facts), 1)
        self.assertIn("APOLLO-104", facts[0].content)


class TestConnectorManager(unittest.TestCase):
    """Test ConnectorManager deterministic routing and parallel execution."""

    def setUp(self):
        self.manager = ConnectorManager()

    def test_tag_based_deterministic_routing(self):
        """Verify that context tags correctly trigger configured connectors."""
        # Calendar tags
        connectors = self.manager.resolve_connectors_for_tags(["meeting", "reschedule"])
        self.assertIn("calendar", connectors)

        # Invoice tags
        connectors = self.manager.resolve_connectors_for_tags(["invoice", "wire-transfer"])
        self.assertIn("gmail_search", connectors)

        # Action / reply tags
        connectors = self.manager.resolve_connectors_for_tags(["reply-needed", "follow-up"])
        self.assertIn("gmail_search", connectors)

        # SRE tags
        connectors = self.manager.resolve_connectors_for_tags(["incident", "sre", "outage"])
        self.assertIn("engineering_docs_rag", connectors)
        self.assertIn("jira_mcp", connectors)

        # Legal tags
        connectors = self.manager.resolve_connectors_for_tags(["legal", "compliance"])
        self.assertIn("legal_contracts_rag", connectors)

    def test_synthesize_facts_capping(self):
        """Verify fact synthesis caps bullets and words properly."""
        facts = [
            FactItem(source="Calendar", content="Free Friday 10 AM"),
            FactItem(source="RAG", content="SLA guarantees 99.9% uptime"),
            FactItem(source="Search", content="Agreed to discount"),
            FactItem(source="MCP", content="Ticket is closed"),
            FactItem(source="Extra", content="Should be omitted due to max_bullets"),
        ]
        synth = self.manager.synthesize_facts(facts, max_bullets=3)
        self.assertIn("RETRIEVED INTERNAL FACTS", synth)
        self.assertIn("Free Friday 10 AM", synth)
        self.assertIn("SLA guarantees 99.9% uptime", synth)
        self.assertNotIn("Should be omitted", synth)


if __name__ == '__main__':
    unittest.main()
