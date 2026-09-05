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
Gmail Historical Search Connector.

Wraps app/services/gmail_service.py:execute_gmail_search() under the BaseConnector contract.
Searches past correspondence with the sender or topic keywords for prior agreements,
commitments, pricing discussions, or invoice references.
"""
from typing import Optional, List, Dict, Any

from .base_connector import BaseConnector, FactItem, MutationResult


class GmailSearchConnector(BaseConnector):
    """
    Queries past Gmail messages and threads to retrieve historical context.
    """

    def __init__(self, connector_id: str = "gmail_search", config: Optional[dict] = None):
        super().__init__(connector_id, config)
        self.max_past_threads = self.config.get("max_past_threads", 3)
        self.mock_history = self.config.get("mock_history", None)

    def is_available(self) -> bool:
        return self.config.get("enabled", True)

    def query(self, query: str, filters: Optional[dict] = None, **kwargs) -> List[FactItem]:
        """
        Search historical Gmail messages.
        kwargs may provide: creds (Credentials), sender (str), subject (str)
        """
        if not self.is_available():
            return []

        current_msg_id = kwargs.get("current_msg_id", "") or kwargs.get("gmail_id", "")

        # 1. Mock history for tests
        if self.mock_history is not None:
            facts = []
            for item in self.mock_history:
                if current_msg_id and item.get("gmail_id") == current_msg_id:
                    continue
                facts.append(
                    FactItem(
                        source="Gmail Search",
                        content=item.get("summary", ""),
                        timestamp=item.get("date", "Previous"),
                        metadata=item
                    )
                )
            return facts

        creds = kwargs.get("creds", None)
        sender = kwargs.get("sender", "")
        if not creds or not sender:
            return []

        try:
            from services.gmail_service import execute_gmail_search
            import re
            # Extract pure email address from sender header
            match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', sender)
            clean_email = match.group(0) if match else sender

            search_query = f"from:{clean_email}"
            subject_kw = kwargs.get("subject", "") or query or ""
            # Strip prefixes like Re:, Fwd: and non-alphanumeric chars
            clean_kw = re.sub(r'^(re|fwd|fw|external):\s*', '', subject_kw, flags=re.IGNORECASE).strip()
            clean_kw = re.sub(r'[^a-zA-Z0-9\s]', ' ', clean_kw)
            clean_kw = " ".join(clean_kw.split()[:5])  # Top 5 keywords
            if clean_kw:
                search_query += f" {clean_kw}"

            results = execute_gmail_search(creds, query=search_query, max_results=self.max_past_threads + 1)
            facts = []
            for msg in results:
                if current_msg_id and msg.get("gmail_id") == current_msg_id:
                    continue
                facts.append(
                    FactItem(
                        source="Gmail Search",
                        content=f"Past email with subject '{msg.get('subject')}': \"{msg.get('snippet', '')}\"",
                        timestamp=msg.get("date", ""),
                        metadata={"gmail_id": msg.get("gmail_id")}
                    )
                )
                if len(facts) >= self.max_past_threads:
                    break
            return facts

        except Exception as e:
            print(f"[GmailSearchConnector] Search error: {e}")
            return []

    def modify(self, action: str, payload: dict, dry_run: bool = True, **kwargs) -> MutationResult:
        """
        Mutations on mailbox (e.g. archiving or labeling).
        """
        return MutationResult(
            status="dry_run" if dry_run else "success",
            action=action,
            target_system="Gmail",
            result_data=payload
        )
