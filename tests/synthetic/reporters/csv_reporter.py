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
Enterprise QA CSV Report Exporter.
Outputs structured CSV matching QA test spreadsheet deliverables.
"""
import os
import csv
from typing import List, Dict, Any
from tests.synthetic.schema import TestResult


def generate_csv_report(stats: Dict[str, Any], results: List[TestResult], output_path: str) -> str:
    """Generate structured CSV containing all individual test execution traces."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Test_ID",
            "Suite",
            "Domain",
            "Title",
            "Status",
            "Expected_Category",
            "Predicted_Category",
            "Category_Match",
            "Expected_Urgency_Range",
            "Predicted_Urgency",
            "Urgency_Match",
            "Expected_Reply_Necessary",
            "Predicted_Reply_Necessary",
            "Is_VIP",
            "Is_No_Reply",
            "Actions_Match",
            "Duration_MS",
            "Sender",
            "Subject",
            "Reasoning",
        ])

        for r in results:
            writer.writerow([
                r.test_id,
                r.suite,
                r.domain,
                r.title,
                "PASSED" if r.passed else "FAILED",
                r.expected.category,
                r.predicted_category,
                r.category_match,
                f"{r.expected.urgency_score_range[0]}-{r.expected.urgency_score_range[1]}",
                r.predicted_urgency,
                r.urgency_match,
                r.expected.is_reply_necessary,
                r.predicted_reply_necessary,
                r.expected.is_vip,
                r.expected.is_no_reply,
                r.actions_match,
                f"{r.duration_ms:.1f}",
                r.email_sender,
                r.email_subject,
                r.reasoning.replace("\n", " ") if r.reasoning else "",
            ])
    return output_path
