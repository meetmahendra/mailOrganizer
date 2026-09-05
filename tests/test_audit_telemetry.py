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
Tests for deep observability telemetry schemas and pipeline tracing.
"""
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "app"))

from pipeline.audit_schema import (
    AuditRecord,
    LLMCommunication,
    ConnectorCommunication,
    PipelineNodeTrace,
)


class TestAuditTelemetry(unittest.TestCase):

    def test_audit_record_validation(self):
        rec = AuditRecord(
            entry_point="LIVE_BENCHMARK",
            dry_run=True,
            timestamp="2026-09-04T02:00:00Z",
            execution_time_seconds=1.45,
            gmail_id="msg_999",
            thread_id="th_999",
            sender="boss@corp.com",
            to_recipients=["me@corp.com"],
            subject="Urgent: Production cluster review",
            body="Marcus, please confirm architecture approval.",
            category="Action Required (High)",
            urgency_score=9,
            confidence_score=98,
            reasoning="Critical executive request",
            context_tags=["approval", "architecture"],
            is_reply_necessary=True,
            reply_necessity_reason="Direct question from VP",
            responsibility_role="PRIMARY_ACTIONEE",
            ownership_reason="Directly addressed by name",
            retrieved_facts="• Topology review SLA: 48 hours",
            enriched_draft_reply="I have reviewed the topology and grant my CTO approval.",
            llm_communications=[
                LLMCommunication(
                    step="classification",
                    model="gemini-3.6-flash",
                    temperature=0.1,
                    system_prompt="System instructions...",
                    human_prompt="Subject: Urgent: Production cluster review",
                    raw_response='{"category": "Action Required (High)"}',
                    duration_ms=450.2,
                    status="success",
                ),
                LLMCommunication(
                    step="draft_generation",
                    model="gemini-3.6-flash",
                    temperature=0.3,
                    system_prompt="Drafting instructions...",
                    human_prompt="Draft reply...",
                    raw_response="I have reviewed the topology and grant my CTO approval.",
                    duration_ms=620.0,
                    status="success",
                ),
            ],
            connector_communications=[
                ConnectorCommunication(
                    connector_id="gmail_search",
                    routing_tags=["architecture"],
                    query_sent="Production cluster review",
                    status="success",
                    duration_ms=35.0,
                    facts_count=1,
                    raw_facts_returned=[{"content": "Prior agreement"}],
                )
            ],
            pipeline_trace=[
                PipelineNodeTrace(node="pre_check", duration_ms=2.1),
                PipelineNodeTrace(node="classify", duration_ms=450.2),
                PipelineNodeTrace(node="ownership_gate", duration_ms=1.5, routing_decision="enrich_context", routing_reason="Role requires drafting"),
                PipelineNodeTrace(node="enrich_context", duration_ms=35.0),
                PipelineNodeTrace(node="generate_draft", duration_ms=620.0),
                PipelineNodeTrace(node="plan_actions", duration_ms=3.0),
                PipelineNodeTrace(node="execute", duration_ms=1.0),
                PipelineNodeTrace(node="log_result", duration_ms=5.0),
            ],
        )

        self.assertEqual(rec.entry_point, "LIVE_BENCHMARK")
        self.assertEqual(len(rec.llm_communications), 2)
        self.assertEqual(rec.llm_communications[0].step, "classification")
        self.assertEqual(rec.llm_communications[1].step, "draft_generation")
        self.assertEqual(len(rec.connector_communications), 1)
        self.assertEqual(rec.connector_communications[0].connector_id, "gmail_search")
        self.assertEqual(len(rec.pipeline_trace), 8)
        self.assertEqual(rec.pipeline_trace[2].routing_decision, "enrich_context")


if __name__ == "__main__":
    unittest.main()
