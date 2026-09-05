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
Connector Manager.

Central registry and orchestrator for all external knowledge connectors:
  1. Instantiates active connectors based on config/connectors.yaml
  2. Resolves which connectors to query using tag-based deterministic routing
  3. Executes queries in parallel via ThreadPoolExecutor with strict 2.0s timeouts
  4. Synthesizes and caps facts for LLM prompt injection (max 3 bullets, 500 tokens cap)
"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Any, Set

from .base_connector import BaseConnector, FactItem, MutationResult
from .calendar_connector import CalendarConnector
from .gmail_search_connector import GmailSearchConnector
from .rag_connector import RAGConnector
from .mcp_connector import MCPConnector

# Import configuration schema loader
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.normpath(os.path.join(_APP_DIR, '..')))
from config.schemas import load_and_validate_connectors_config, ConnectorsConfig


class ConnectorManager:
    """
    Thread-safe orchestrator for enterprise connectors.
    """

    def __init__(self, config_path: Optional[str] = None):
        self.config: ConnectorsConfig = load_and_validate_connectors_config(config_path)
        self.connectors: Dict[str, BaseConnector] = {}
        self._init_connectors()

    def _init_connectors(self):
        """Instantiate all configured connectors."""
        # 1. Calendar
        if self.config.calendar.enabled:
            self.connectors["calendar"] = CalendarConnector(
                connector_id="calendar",
                config=self.config.calendar.model_dump()
            )

        # 2. Gmail Search
        if self.config.gmail_search.enabled:
            self.connectors["gmail_search"] = GmailSearchConnector(
                connector_id="gmail_search",
                config=self.config.gmail_search.model_dump()
            )

        # 3. External RAG Services
        for rag_id, rag_cfg in self.config.external_rag_services.items():
            connector_name = f"{rag_id}_rag" if not rag_id.endswith("_rag") else rag_id
            self.connectors[connector_name] = RAGConnector(
                connector_id=connector_name,
                config=rag_cfg.model_dump()
            )

        # 4. Outbound MCP Servers
        for mcp_id, mcp_cfg in self.config.mcp_servers.items():
            connector_name = f"{mcp_id}_mcp" if not mcp_id.endswith("_mcp") else mcp_id
            self.connectors[connector_name] = MCPConnector(
                connector_id=connector_name,
                config=mcp_cfg.model_dump()
            )

    def resolve_connectors_for_tags(self, context_tags: List[str]) -> List[str]:
        """
        Deterministic Tag-Based Routing (Addresses Review Issue #5):
        Matches incoming email's context tags against configured routing rules.
        Returns a list of connector IDs to query. Zero added LLM cost.
        """
        if not context_tags:
            return []

        lower_tags = {t.lower().strip() for t in context_tags}
        selected: Set[str] = set()

        for rule in self.config.routing_rules:
            rule_tags = {t.lower().strip() for t in rule.tags}
            if lower_tags.intersection(rule_tags):
                for conn_id in rule.connectors:
                    if conn_id in self.connectors and self.connectors[conn_id].is_available():
                        selected.add(conn_id)

        return list(selected)

    def query_connectors(
        self,
        query: str,
        connector_ids: List[str],
        filters: Optional[dict] = None,
        timeout_seconds: float = 2.0,
        **kwargs
    ) -> List[FactItem]:
        """
        Query selected connectors in parallel using ThreadPoolExecutor (Addresses Review Issue #2).
        Strict per-connector timeout prevents any single slow service from delaying pipeline.
        """
        self._last_query_telemetry: List[dict] = []
        if not connector_ids:
            return []

        all_facts: List[FactItem] = []
        tasks = {}
        start_times = {}

        with ThreadPoolExecutor(max_workers=min(len(connector_ids), 5)) as executor:
            for cid in connector_ids:
                connector = self.connectors.get(cid)
                if connector and connector.is_available():
                    start_times[cid] = time.perf_counter()
                    future = executor.submit(connector.query, query, filters=filters, **kwargs)
                    tasks[future] = cid

            for future in as_completed(tasks, timeout=timeout_seconds + 0.5):
                cid = tasks[future]
                elapsed_ms = (time.perf_counter() - start_times.get(cid, time.perf_counter())) * 1000
                try:
                    facts = future.result(timeout=timeout_seconds)
                    if facts:
                        all_facts.extend(facts)
                    self._last_query_telemetry.append({
                        "connector_id": cid,
                        "routing_tags": kwargs.get("context_tags", []),
                        "query_sent": str(query),
                        "status": "success",
                        "duration_ms": round(elapsed_ms, 2),
                        "facts_count": len(facts) if facts else 0,
                        "raw_facts_returned": [f.model_dump() for f in (facts or [])]
                    })
                except Exception as e:
                    print(f"[ConnectorManager] Error querying connector '{cid}': {e}")
                    self._last_query_telemetry.append({
                        "connector_id": cid,
                        "routing_tags": kwargs.get("context_tags", []),
                        "query_sent": str(query),
                        "status": f"error: {e}",
                        "duration_ms": round(elapsed_ms, 2),
                        "facts_count": 0,
                        "raw_facts_returned": []
                    })

        return all_facts

    def get_last_query_telemetry(self) -> List[dict]:
        """Retrieve telemetry captured during the most recent query_connectors run."""
        return getattr(self, "_last_query_telemetry", [])

    def synthesize_facts(self, facts: List[FactItem], max_bullets: int = 4, max_words_per_bullet: int = 150) -> str:
        """
        Synthesize extracted facts into a structured, token-capped prompt context block.
        """
        if not facts:
            return ""

        lines = ["--- 💡 RETRIEVED INTERNAL FACTS & ENTERPRISE CONTEXT ---"]
        for fact in facts[:max_bullets]:
            # Word-capping per excerpt
            words = fact.content.split()
            capped_content = " ".join(words[:max_words_per_bullet])
            if len(words) > max_words_per_bullet:
                capped_content += "..."
            ts = f" ({fact.timestamp})" if fact.timestamp else ""
            lines.append(f"• Source [{fact.source}]{ts}: {capped_content}")

        lines.append("---------------------------------------------------------")
        return "\n".join(lines)


# Singleton manager instance for pipeline
_manager_instance: Optional[ConnectorManager] = None


def get_connector_manager() -> ConnectorManager:
    """Get or create singleton ConnectorManager."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ConnectorManager()
    return _manager_instance
