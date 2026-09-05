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
Fixtures and Mock Context Injector for Live Benchmark Scenarios.

Allows deterministic injection of external RAG facts, calendar availability,
and historical threads during benchmark evaluation without requiring live external
network endpoints.
"""
import contextlib
from typing import Dict, Any, List
from unittest.mock import patch

from app.connectors.base_connector import FactItem
from app.connectors.connector_manager import ConnectorManager


class BenchmarkFixtureManager:
    """
    Manages runtime injection of connector fixtures for a specific benchmark test case.
    """

    @staticmethod
    def format_fixture_facts(fixture_data: Dict[str, Any]) -> List[FactItem]:
        """Convert fixture dictionary into FactItem objects for synthesis."""
        facts: List[FactItem] = []
        raw_facts = fixture_data.get("facts", [])
        for item in raw_facts:
            if isinstance(item, str):
                facts.append(FactItem(content=item, source="BenchmarkFixture"))
            elif isinstance(item, dict):
                facts.append(
                    FactItem(
                        content=item.get("content", ""),
                        source=item.get("source", "BenchmarkFixture"),
                        timestamp=item.get("timestamp"),
                    )
                )
        return facts


@contextlib.contextmanager
def apply_benchmark_fixtures(case, mode: str = "mock"):
    """
    Context manager that patches ConnectorManager.query_connectors to return
    scenario fixtures, and optionally mocks LLM calls when mode == 'mock'.
    """
    fixture_facts = BenchmarkFixtureManager.format_fixture_facts(case.connector_fixtures)

    def mock_query(self, query, connector_ids, **kwargs):
        return fixture_facts

    patches = [
        patch.object(ConnectorManager, "query_connectors", mock_query),
    ]

    if mode == "mock":
        from app.pipeline import nodes

        criteria = case.evaluation_criteria
        draft_reqs = criteria.draft_requirements

        def mock_classify(state):
            # Determine mock category from domain and criteria
            domain = case.domain
            if criteria.expected_responsibility == "OOO_SENDER":
                category = "Informational/Logs"
                urgency = 2
            elif domain == "cloud_sre":
                category = "System Alert"
                urgency = 9 if criteria.urgency_level == "HIGH" else 4
            elif domain == "security_adversarial":
                if criteria.inbox_placement == "SAFE_ARCHIVE":
                    category = "Spam/Trash"
                    urgency = 2
                else:
                    category = "Action Required (High)"
                    urgency = 9
            elif criteria.inbox_placement == "SAFE_ARCHIVE":
                category = "Promotions/Marketing" if "marketing" in domain else "Informational/Logs"
                urgency = 2
            elif "reschedule" in case.title.lower() or "calendar" in case.title.lower() or "meeting" in case.title.lower():
                category = "Calendar/Scheduling"
                urgency = 6
            elif criteria.urgency_level == "HIGH":
                category = "Action Required (High)"
                urgency = 9
            else:
                category = "Action Required (Med/Low)"
                urgency = 5

            tags = [domain, category.lower()]
            if "wire" in case.email.subject.lower():
                tags.append("wire-transfer")
            if "incident" in case.email.subject.lower() or "alert" in case.email.subject.lower():
                tags.extend(["incident", "sre"])
            if "gdpr" in case.email.subject.lower() or "subpoena" in case.email.subject.lower():
                tags.extend(["legal", "compliance"])
            if "reschedule" in case.email.subject.lower() or "interview" in case.email.subject.lower():
                tags.append("meeting")

            return {
                "category": category,
                "urgency_score": urgency,
                "confidence_score": 95,
                "reasoning": f"Benchmark scenario {case.id} classification",
                "suggested_reply": "",
                "context_tags": tags,
                "is_reply_necessary": draft_reqs.should_draft,
                "reply_necessity_reason": "Based on scenario evaluation requirements",
            }

        def mock_generate_draft(state):
            existing = state.get("enriched_draft_reply", "").strip()
            if existing:
                return {"enriched_draft_reply": existing}

            role = state.get("responsibility_role", "PRIMARY_ACTIONEE")
            if role in ("OBSERVER_ONLY", "TEAMMATE_HANDLING", "OOO_SENDER"):
                return {"enriched_draft_reply": ""}

            if not state.get("is_reply_necessary", False):
                return {"enriched_draft_reply": ""}

            # Build grounded draft satisfying must_mention keywords
            parts = [f"Hi, thank you for reaching out regarding {case.email.subject}."]
            if draft_reqs.must_mention:
                mentions = ", ".join(draft_reqs.must_mention)
                parts.append(f"Regarding {mentions}, we have reviewed the details.")
            
            if fixture_facts:
                fact_texts = " ".join(f.content for f in fixture_facts)
                parts.append(f"Context verified: {fact_texts}")

            cal = state.get("calendar_context", "")
            if cal:
                parts.append(f"Availability: {cal}")

            parts.append("Best regards,\nMarcus Vance | CTO\nTechGlobal Cloud Solutions")
            return {"enriched_draft_reply": "\n\n".join(parts)}

        patches.append(patch.object(nodes, "classify_email", mock_classify))
        patches.append(patch.object(nodes, "generate_enriched_draft", mock_generate_draft))

    for p in patches:
        p.start()

    try:
        yield
    finally:
        for p in reversed(patches):
            p.stop()
