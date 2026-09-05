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
Organization & Persona Model for Synthetic Test Data Generation.

Provides realistic enterprise actors, departmental topologies, signature templates,
RFC header generators, and legal confidentiality disclaimers.
"""
import os
import random
from typing import List, Dict, Any, Optional

try:
    import yaml
except ImportError:
    yaml = None

_APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONFIG_ORG_DIR = os.path.normpath(os.path.join(_APP_DIR, 'config', 'organization'))


def load_org_roster() -> List[Dict[str, Any]]:
    """Load employee roster from config/organization/roster.yaml."""
    if not yaml:
        return []
    path = os.path.join(_CONFIG_ORG_DIR, 'roster.yaml')
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
        return data.get('employees', [])


def load_external_stakeholders() -> Dict[str, Any]:
    """Load strategic clients and vendors from config/organization/external_stakeholders.yaml."""
    if not yaml:
        return {}
    path = os.path.join(_CONFIG_ORG_DIR, 'external_stakeholders.yaml')
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


CONFIDENTIALITY_DISCLAIMERS = [
    "\n\n---\nCONFIDENTIALITY NOTICE: This electronic mail transmission contains confidential and legally privileged information intended only for the use of the individual or entity named above. If you are not the intended recipient, please immediately delete and notify the sender.",
    "\n\n---\nThis email and any attachments are intended solely for the use of the individual or entity to whom they are addressed and may contain proprietary information of TechGlobal Solutions Inc.",
    "\n\n---\nPrivileged & Confidential | Attorney-Client Communication | Do Not Forward.",
    "\n\n---\nTechGlobal Cloud Solutions | 500 Howard Street, Suite 1400, San Francisco, CA 94105 | ISO 27001 & SOC 2 Type II Certified",
]


def generate_corporate_signature(name: str, title: str, department: str, email: str, phone: Optional[str] = None) -> str:
    """Generate a realistic corporate email signature."""
    p = phone or f"+1 (415) 555-0{random.randint(100, 999)}"
    disclaimer = random.choice(CONFIDENTIALITY_DISCLAIMERS)
    return f"\n\nBest regards,\n\n{name}\n{title} | {department}\nTechGlobal Cloud Solutions\nDirect: {p} | {email}{disclaimer}"


def generate_client_signature(name: str, title: str, company: str, email: str) -> str:
    """Generate an external client email signature."""
    disclaimer = CONFIDENTIALITY_DISCLAIMERS[0]
    return f"\n\nSincerely,\n\n{name}\n{title}\n{company}\nEmail: {email}{disclaimer}"
