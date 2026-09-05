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
Tests for AuditManager 100-email auto-partitioning and master index generation.
"""
import os
import sys
import json
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "app"))

from pipeline.audit_manager import AuditManager, JSON_DIR, HTML_DIR, AUDIT_DIR, AUDIT_CSV


class TestAuditManager(unittest.TestCase):

    def test_audit_manager_partitioning_at_100(self):
        manager = AuditManager.get_instance()

        # Generate 105 test records across different sources
        sources = ["DRY_RUN", "LIVE_BENCHMARK", "API_BATCH"]
        for i in range(105):
            source = sources[i % len(sources)]
            dummy_state = {
                "entry_point": source,
                "dry_run": True,
                "gmail_id": f"test_msg_{i+1:04d}",
                "thread_id": f"thread_{i+1:04d}",
                "sender": f"sender_{i}@example.com",
                "to_recipients": ["me@company.com"],
                "cc_recipients": [],
                "subject": f"Automated Test Subject {i+1}",
                "body": f"This is test body for message {i+1}",
                "category": "Informational/Logs",
                "urgency_score": 2,
                "confidence_score": 95,
                "reasoning": "Automated partition test reasoning",
                "context_tags": ["test", "partition"],
                "is_reply_necessary": False,
                "reply_necessity_reason": "Automated test",
                "responsibility_role": "PRIMARY_ACTIONEE",
                "ownership_reason": "Direct addressee",
                "retrieved_facts": "• Test fact 1\n• Test fact 2",
                "calendar_context": "No conflicts",
                "gmail_actions": [{"action": "mark_as_read"}],
                "actions_taken": [{"action": "mark_as_read", "status": "DRY_RUN"}],
                "enriched_draft_reply": f"Hi, thanks for reaching out regarding message {i+1}.",
                "llm_communications": [
                    {
                        "step": "classification",
                        "model": "gemini-3.6-flash",
                        "temperature": 0.1,
                        "system_prompt": "You are a test classifier system prompt.",
                        "human_prompt": f"Subject: Automated Test Subject {i+1}",
                        "raw_response": '{"category": "Informational/Logs", "urgency": 2}',
                        "duration_ms": 120.5,
                        "status": "success",
                    }
                ],
                "connector_communications": [
                    {
                        "connector_id": "gmail_search",
                        "routing_tags": ["test"],
                        "query_sent": f"Automated Test Subject {i+1}",
                        "status": "success",
                        "duration_ms": 45.2,
                        "facts_count": 1,
                        "raw_facts_returned": [{"source": "Gmail Search", "content": "Previous thread"}],
                    }
                ],
                "pipeline_trace": [
                    {"node": "pre_check", "duration_ms": 1.2},
                    {"node": "classify", "duration_ms": 120.5},
                    {"node": "log_result", "duration_ms": 2.1},
                ],
            }
            manager.record_email(dummy_state)

        # Verify part_0001.json exists and has at least 100 records
        part1_json = os.path.join(JSON_DIR, "audit_report_part_0001.json")
        self.assertTrue(os.path.exists(part1_json), "part_0001.json must exist")
        with open(part1_json, "r", encoding="utf-8") as f:
            data1 = json.load(f)
            self.assertEqual(len(data1), 100, f"Expected 100 records in part 1, got {len(data1)}")

        # Verify part_0002.json exists and has at least 5 records
        part2_json = os.path.join(JSON_DIR, "audit_report_part_0002.json")
        self.assertTrue(os.path.exists(part2_json), "part_0002.json must exist")
        with open(part2_json, "r", encoding="utf-8") as f:
            data2 = json.load(f)
            self.assertGreaterEqual(len(data2), 5, f"Expected >= 5 records in part 2, got {len(data2)}")

        # Verify HTML parts exist
        self.assertTrue(os.path.exists(os.path.join(HTML_DIR, "audit_report_part_0001.html")))
        self.assertTrue(os.path.exists(os.path.join(HTML_DIR, "audit_report_part_0002.html")))

        # Verify master index.html exists and is populated
        index_html = os.path.join(AUDIT_DIR, "index.html")
        self.assertTrue(os.path.exists(index_html))
        with open(index_html, "r", encoding="utf-8") as f:
            index_content = f.read()
            self.assertIn("Part 0001", index_content)
            self.assertIn("Part 0002", index_content)

        # Verify audit_log.csv has records
        self.assertTrue(os.path.exists(AUDIT_CSV))


if __name__ == "__main__":
    unittest.main()
