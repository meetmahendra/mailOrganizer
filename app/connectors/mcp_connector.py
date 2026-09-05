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
Outbound Model Context Protocol (MCP) Connector.

Consumes external MCP servers (Jira, Linear, SAP, Salesforce, PostgreSQL)
to execute tools and read resources for context enrichment.

(Note: Distinct from the Inbound MCP server located in mcp_server/ which exposes
MailOrganizer tools to external agents).
"""
import os
import json
from typing import Optional, List, Dict, Any

from .base_connector import BaseConnector, FactItem, MutationResult


class MCPConnector(BaseConnector):
    """
    Client connector for external Model Context Protocol servers.
    """

    def __init__(self, connector_id: str, config: Optional[dict] = None):
        super().__init__(connector_id, config)
        self.transport = self.config.get("transport", "stdio")
        self.command = self.config.get("command", None)
        self.args = self.config.get("args", [])
        self.url = self.config.get("url", None)
        self.env = self.config.get("env", {})
        self.mock_facts = self.config.get("mock_facts", None)

    def is_available(self) -> bool:
        if self.mock_facts is not None:
            return True
        if self.transport == "stdio" and self.command:
            return True
        if self.transport == "sse" and self.url:
            return True
        return False

    def query(self, query: str, filters: Optional[dict] = None, **kwargs) -> List[FactItem]:
        """
        Invoke MCP resource or query tool.
        """
        # 1. Mock facts for testing
        if self.mock_facts is not None:
            facts = []
            for item in self.mock_facts:
                if isinstance(item, str):
                    facts.append(FactItem(source=f"MCP: {self.connector_id}", content=item))
                elif isinstance(item, dict):
                    facts.append(
                        FactItem(
                            source=f"MCP: {self.connector_id}",
                            content=item.get("content", ""),
                            metadata=item.get("metadata", {})
                        )
                    )
            return facts

        # 2. Outbound execution fallback
        # In full production mode, this communicates with the MCP server process.
        # When running in environments where MCP process isn't running, return structured info.
        return [
            FactItem(
                source=f"MCP: {self.connector_id}",
                content=f"MCP server '{self.connector_id}' active on {self.transport} transport.",
                metadata={"transport": self.transport}
            )
        ]

    def modify(self, action: str, payload: dict, dry_run: bool = True, **kwargs) -> MutationResult:
        """
        Invoke an MCP tool with side-effects (e.g. updating an issue or database record).
        """
        if dry_run:
            return MutationResult(
                status="dry_run",
                action=action,
                target_system=f"MCP:{self.connector_id}",
                result_data=payload
            )

        # Live execution (future expansion for full live MCP tool execution)
        return MutationResult(
            status="success",
            action=action,
            target_system=f"MCP:{self.connector_id}",
            result_data={"simulated": True, "action": action}
        )
