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
External RAG Connector.

Connects to pre-existing enterprise RAG services (Vertex AI Search, LangChain RAG,
LlamaIndex, or custom internal FastAPI endpoints).
Supports semantic querying and optional feedback/modify endpoints.
"""
from typing import Optional, List, Dict, Any
import requests

from .base_connector import BaseConnector, FactItem, MutationResult


class RAGConnector(BaseConnector):
    """
    HTTP REST Client for external RAG services.
    """

    def __init__(self, connector_id: str, config: Optional[dict] = None):
        super().__init__(connector_id, config)
        self.endpoint = self.config.get("endpoint", "")
        self.modify_endpoint = self.config.get("modify_endpoint", None)
        self.auth_header = self.config.get("auth_header", None)
        self.timeout = float(self.config.get("timeout_seconds", 2.0))
        self.description = self.config.get("description", "")
        self.mock_facts = self.config.get("mock_facts", None)

    def is_available(self) -> bool:
        return bool(self.endpoint or self.mock_facts is not None)

    def query(self, query: str, filters: Optional[dict] = None, **kwargs) -> List[FactItem]:
        """
        Send semantic query to the external RAG service.
        """
        # 1. Mock facts for test execution
        if self.mock_facts is not None:
            facts = []
            for item in self.mock_facts:
                if isinstance(item, str):
                    facts.append(FactItem(source=f"External RAG: {self.connector_id}", content=item))
                elif isinstance(item, dict):
                    facts.append(
                        FactItem(
                            source=f"External RAG: {self.connector_id}",
                            content=item.get("content", ""),
                            metadata=item.get("metadata", {})
                        )
                    )
            return facts

        if not self.endpoint:
            return []

        headers = {"Content-Type": "application/json"}
        if self.auth_header:
            headers["Authorization"] = self.auth_header

        payload = {
            "query": query,
            "top_k": 3,
            "filters": filters or {},
        }

        try:
            resp = requests.post(self.endpoint, json=payload, headers=headers, timeout=self.timeout)
            if resp.status_code != 200:
                print(f"[RAGConnector:{self.connector_id}] HTTP error {resp.status_code}: {resp.text[:100]}")
                return []

            data = resp.json()
            # Support standard formats: list of strings or list of {content, metadata}
            results = data.get("results") or data.get("chunks") or data.get("documents") or []
            facts = []
            for res in results[:3]:
                if isinstance(res, str):
                    facts.append(FactItem(source=f"External RAG: {self.connector_id}", content=res.strip()))
                elif isinstance(res, dict):
                    facts.append(
                        FactItem(
                            source=f"External RAG: {self.connector_id}",
                            content=res.get("text") or res.get("content") or res.get("snippet", ""),
                            metadata=res.get("metadata", {})
                        )
                    )
            return facts

        except requests.exceptions.Timeout:
            print(f"[RAGConnector:{self.connector_id}] Query timed out after {self.timeout}s.")
            return []
        except Exception as e:
            print(f"[RAGConnector:{self.connector_id}] Query failed: {e}")
            return []

    def modify(self, action: str, payload: dict, dry_run: bool = True, **kwargs) -> MutationResult:
        """
        Post document update, feedback, or annotation back to the RAG service.
        """
        if dry_run:
            return MutationResult(
                status="dry_run",
                action=action,
                target_system=f"RAG:{self.connector_id}",
                result_data=payload
            )

        if not self.modify_endpoint:
            return MutationResult(
                status="failed",
                action=action,
                target_system=f"RAG:{self.connector_id}",
                error="Modify endpoint not configured for this RAG service."
            )

        headers = {"Content-Type": "application/json"}
        if self.auth_header:
            headers["Authorization"] = self.auth_header

        try:
            resp = requests.post(self.modify_endpoint, json=payload, headers=headers, timeout=self.timeout)
            return MutationResult(
                status="success" if resp.status_code in (200, 201, 204) else "failed",
                action=action,
                target_system=f"RAG:{self.connector_id}",
                result_data=resp.json() if resp.status_code == 200 else {"status_code": resp.status_code},
                error=resp.text if resp.status_code not in (200, 201, 204) else None
            )
        except Exception as e:
            return MutationResult(
                status="failed",
                action=action,
                target_system=f"RAG:{self.connector_id}",
                error=str(e)
            )
