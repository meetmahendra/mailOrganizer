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
Unit Tests for Draft History Enrichment and Cross-Thread Search Routing.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))

from pipeline.nodes import enrich_context, generate_enriched_draft
from pipeline.state import EmailState


class TestDraftEnrichment(unittest.TestCase):

    def test_enrich_context_forces_gmail_search_when_reply_necessary(self):
        """Verify that enrich_context queries gmail_search when is_reply_necessary is True."""
        state: EmailState = {
            "gmail_id": "msg_incoming_999",
            "thread_id": "thread_888",
            "subject": "Regarding your proposal",
            "sender": "partner@acme.com",
            "body": "Could you provide details on the discount discussed earlier?",
            "snippet": "",
            "message_id_header": "",
            "to_recipients": ["me@company.com"],
            "cc_recipients": [],
            "auto_reply_headers": {},
            "thread_history": [],
            "is_no_reply": False,
            "is_vip": False,
            "has_critical_subject": False,
            "category": "Action Required (Med/Low)",
            "urgency_score": 6,
            "confidence_score": 90,
            "reasoning": "Reply requested",
            "suggested_reply": "",
            # Deliberately use tags that don't include financial or explicit search tags
            "context_tags": ["general-inquiry", "unrelated-tag"],
            "is_reply_necessary": True,
            "reply_necessity_reason": "Partner asked for proposal discount details",
            "gmail_actions": [],
            "pending_pm_tasks": [],
            "calendar_context": "",
            "responsibility_role": "PRIMARY_ACTIONEE",
            "delegation_target": None,
            "ownership_reason": "",
            "retrieved_facts": "",
            "enriched_draft_reply": "",
            "pending_mutations": [],
            "dry_run": True,
            "creds": None,
            "user_id": 1,
            "actions_taken": [],
            "error": None,
        }

        with patch("connectors.connector_manager.get_connector_manager") as mock_mgr_get:
            mock_mgr = MagicMock()
            mock_search_conn = MagicMock()
            mock_search_conn.is_available.return_value = True
            mock_mgr.connectors = {"gmail_search": mock_search_conn}
            mock_mgr.resolve_connectors_for_tags.return_value = []
            mock_mgr.query_connectors.return_value = []
            mock_mgr.synthesize_facts.return_value = "--- 💡 RETRIEVED INTERNAL FACTS ---\n• Source [Gmail Search]: Past 15% discount"
            mock_mgr_get.return_value = mock_mgr

            result = enrich_context(state)

            # Check that query_connectors was called and included gmail_search
            mock_mgr.query_connectors.assert_called_once()
            called_kwargs = mock_mgr.query_connectors.call_args.kwargs
            self.assertIn("gmail_search", called_kwargs.get("connector_ids", []))
            self.assertEqual(called_kwargs.get("current_msg_id"), "msg_incoming_999")
            self.assertEqual(result.get("retrieved_facts"), "--- 💡 RETRIEVED INTERNAL FACTS ---\n• Source [Gmail Search]: Past 15% discount")

    def test_generate_enriched_draft_includes_thread_history(self):
        """Verify that generate_enriched_draft formats in-thread history into the LLM prompt."""
        state: EmailState = {
            "gmail_id": "msg_incoming_999",
            "thread_id": "thread_888",
            "subject": "Re: Project Launch Date",
            "sender": "sarah@acme.com",
            "body": "Sounds good, what time works best for you?",
            "snippet": "",
            "message_id_header": "",
            "to_recipients": ["me@company.com"],
            "cc_recipients": [],
            "auto_reply_headers": {},
            "thread_history": [
                {"turn": 1, "date": "2026-09-02", "sender": "sarah@acme.com", "snippet": "Can we launch next Monday?"},
                {"turn": 2, "date": "2026-09-03", "sender": "me@company.com", "snippet": "Monday looks good, let's schedule a prep sync."},
            ],
            "is_no_reply": False,
            "is_vip": False,
            "has_critical_subject": False,
            "category": "Calendar/Scheduling",
            "urgency_score": 7,
            "confidence_score": 95,
            "reasoning": "Scheduling sync",
            "suggested_reply": "",
            "context_tags": ["schedule-meeting"],
            "is_reply_necessary": True,
            "reply_necessity_reason": "Time request",
            "gmail_actions": [],
            "pending_pm_tasks": [],
            "calendar_context": "Thursday 2 PM is open",
            "responsibility_role": "PRIMARY_ACTIONEE",
            "delegation_target": None,
            "ownership_reason": "",
            "retrieved_facts": "• Source [Gmail Search]: Prior sync scheduled for 30 mins",
            "enriched_draft_reply": "",
            "pending_mutations": [],
            "dry_run": True,
            "creds": None,
            "user_id": 1,
            "actions_taken": [],
            "error": None,
        }

        with patch("os.getenv", return_value="fake_gemini_key"), \
             patch("pipeline.nodes._build_llm") as mock_build_llm, \
             patch("pipeline.nodes.ChatPromptTemplate") as mock_prompt_template:

            mock_llm = MagicMock()
            mock_chain = MagicMock()
            mock_llm_response = MagicMock()
            mock_llm_response.content = "Let's meet Thursday at 2 PM for the prep sync."
            mock_chain.invoke.return_value = mock_llm_response
            mock_prompt_template.from_messages.return_value.__or__.return_value = mock_chain
            mock_build_llm.return_value = mock_llm

            result = generate_enriched_draft(state)

            self.assertIn("enriched_draft_reply", result)
            invoked_payload = mock_chain.invoke.call_args[0][0]
            system_text = invoked_payload.get("system_text", "")
            self.assertIn("--- 📜 CONVERSATION THREAD (PRIOR TURNS) ---", system_text)
            self.assertIn("Turn 1 (2026-09-02) from sarah@acme.com", system_text)
            self.assertIn("Can we launch next Monday?", system_text)
            self.assertIn("Turn 2 (2026-09-03) from me@company.com", system_text)
            self.assertIn("• Source [Gmail Search]: Prior sync scheduled for 30 mins", system_text)
            self.assertIn("--- CALENDAR AVAILABILITY ---", system_text)


if __name__ == "__main__":
    unittest.main()
