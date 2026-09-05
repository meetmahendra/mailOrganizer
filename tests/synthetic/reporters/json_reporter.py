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
Machine-Readable JSON Report Exporter.
"""
import os
import json
from typing import List, Dict, Any
from tests.synthetic.schema import TestResult


def generate_json_report(stats: Dict[str, Any], results: List[TestResult], output_path: str) -> str:
    """Export complete test execution statistics and individual results to JSON."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    payload = {
        "evaluation_metrics": stats,
        "test_results": [r.model_dump() for r in results],
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return output_path
