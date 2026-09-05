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
Pluggable External Knowledge & System Connectors.

Provides uniform BaseConnector abstraction (Query + Modify) across:
  - CalendarConnector (Google / Outlook / Mock)
  - GmailSearchConnector (Historical Mailbox Search)
  - RAGConnector (External Pre-existing RAG Services)
  - MCPConnector (Outbound Model Context Protocol Servers)
  - ConnectorManager (Tag-based deterministic parallel dispatcher)
"""
from .base_connector import BaseConnector, FactItem, MutationResult
from .calendar_connector import CalendarConnector
from .gmail_search_connector import GmailSearchConnector
from .rag_connector import RAGConnector
from .mcp_connector import MCPConnector
from .connector_manager import ConnectorManager

__all__ = [
    "BaseConnector",
    "FactItem",
    "MutationResult",
    "CalendarConnector",
    "GmailSearchConnector",
    "RAGConnector",
    "MCPConnector",
    "ConnectorManager",
]
