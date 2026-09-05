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
Base Connector Interface.

Uniform abstraction for all external enterprise systems.
Every connector supports two-way interaction:
  - query(query, filters): Read / Semantic Retrieval
  - modify(action, payload): Write / Updates (if supported by system)
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class FactItem(BaseModel):
    """Represents a single retrieved fact from an external system."""
    source: str = Field(description="Identifier of the source, e.g. 'External RAG: engineering_docs'")
    content: str = Field(description="The crisp fact statement or excerpt")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Arbitrary source metadata")
    timestamp: Optional[str] = Field(default=None, description="Optional timestamp or date of the fact")

    def to_bullet(self) -> str:
        """Format as a clean bullet point for prompt context."""
        ts = f" ({self.timestamp})" if self.timestamp else ""
        return f"• [{self.source}]{ts}: {self.content}"


class MutationResult(BaseModel):
    """Represents the outcome of a write/modify operation on an external system."""
    status: str = Field(description="Status: 'success', 'dry_run', or 'failed'")
    action: str = Field(description="Action name executed, e.g. 'update_ticket'")
    target_system: str = Field(description="Target system name, e.g. 'jira_mcp'")
    result_data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Response payload from the system")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class BaseConnector(ABC):
    """
    Abstract Base Connector.
    Implementations must be thread-safe for parallel execution.
    """

    def __init__(self, connector_id: str, config: Optional[dict] = None):
        self.connector_id = connector_id
        self.config = config or {}

    @abstractmethod
    def query(self, query: str, filters: Optional[dict] = None, **kwargs) -> List[FactItem]:
        """
        Query the external system for relevant facts.
        Must handle its own timeouts and exceptions without crashing.
        """
        pass

    @abstractmethod
    def modify(self, action: str, payload: dict, dry_run: bool = True, **kwargs) -> MutationResult:
        """
        Execute a write/update operation on the external system.
        Must respect dry_run: return status='dry_run' without modifying live systems.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the connector is configured and reachable."""
        pass
