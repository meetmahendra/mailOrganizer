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
Curated Industry Benchmark Test Suites.
Provides loaders for all 11 enterprise domain dataset files.
"""
import os
import json
from typing import List, Dict, Any

_DATASETS_DIR = os.path.dirname(os.path.abspath(__file__))

SUITE_FILES = {
    "fintech_banking": "fintech_banking_suite.json",
    "cloud_devops_sre": "cloud_devops_sre_suite.json",
    "executive_board": "executive_board_suite.json",
    "legal_compliance": "legal_compliance_suite.json",
    "enterprise_sales_cs": "enterprise_sales_cs_suite.json",
    "engineering_product": "engineering_product_suite.json",
    "hr_people_ops": "hr_people_ops_suite.json",
    "security_adversarial": "security_adversarial_suite.json",
    "finance_procurement": "finance_procurement_suite.json",
    "promotions_marketing": "promotions_marketing_suite.json",
    "chained_thread_history": "chained_thread_history_suite.json",
}


def load_suite(suite_name: str) -> List[Dict[str, Any]]:
    """Load a specific curated benchmark suite by name."""
    filename = SUITE_FILES.get(suite_name)
    if not filename:
        # Check if filename passed directly
        filename = f"{suite_name}.json" if not suite_name.endswith(".json") else suite_name
    path = os.path.join(_DATASETS_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_all_curated_suites() -> List[Dict[str, Any]]:
    """Load all 11 curated benchmark suites into a consolidated list."""
    all_cases = []
    for suite_name in SUITE_FILES:
        cases = load_suite(suite_name)
        all_cases.extend(cases)
    return all_cases
