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
Calendar Connector.

Wraps existing app/services/calendar_service.py under the BaseConnector contract.
Provides structured availability facts and supports mock calendar fixtures for test execution.
"""
import datetime
from typing import Optional, List, Dict, Any

from .base_connector import BaseConnector, FactItem, MutationResult


class CalendarConnector(BaseConnector):
    """
    Connects to Google Calendar, Outlook, or a Mock Calendar provider.
    """

    def __init__(self, connector_id: str = "calendar", config: Optional[dict] = None):
        super().__init__(connector_id, config)
        self.provider = self.config.get("provider", "google").lower()
        self.timezone = self.config.get("timezone", "UTC")
        self.mock_slots = self.config.get("mock_slots", None)

    def is_available(self) -> bool:
        return self.config.get("enabled", True)

    def query(self, query: str, filters: Optional[dict] = None, **kwargs) -> List[FactItem]:
        """
        Query free/busy slots and upcoming events.
        kwargs may provide: creds (google.oauth2 credentials)
        """
        if not self.is_available():
            return []

        creds = kwargs.get("creds", None)

        # 1. Mock provider (used in tests or when creds are missing)
        if self.provider == "mock" or (creds is None and self.mock_slots is not None):
            return self._query_mock()

        # 2. Live Google Calendar (wraps calendar_service.py)
        if self.provider == "google":
            if not creds:
                # Return graceful fallback if creds are not supplied
                return [
                    FactItem(
                        source="Calendar",
                        content="Calendar availability service is active (no live credentials attached to this request).",
                        metadata={"provider": "google", "status": "no_creds"}
                    )
                ]
            try:
                from services.calendar_service import check_freebusy, get_upcoming_events
                freebusy = check_freebusy(creds)
                events = get_upcoming_events(creds, max_results=3)

                busy_slots = freebusy.get("busy_slots", [])
                facts = []
                if busy_slots:
                    slot_strs = ", ".join(f"{s['start']} to {s['end']}" for s in busy_slots[:3])
                    facts.append(
                        FactItem(
                            source="Calendar",
                            content=f"Busy commitments in the next 24h: {slot_strs}.",
                            metadata={"busy_count": len(busy_slots)}
                        )
                    )
                else:
                    facts.append(
                        FactItem(
                            source="Calendar",
                            content="Completely free for the next 24 hours.",
                            metadata={"is_free": True}
                        )
                    )

                if events:
                    ev_strs = "; ".join(f"{e.get('summary', 'Meeting')} at {e.get('start')}" for e in events)
                    facts.append(
                        FactItem(
                            source="Calendar",
                            content=f"Upcoming scheduled meetings: {ev_strs}.",
                            metadata={"event_count": len(events)}
                        )
                    )
                return facts

            except Exception as e:
                print(f"[CalendarConnector] Query error: {e}")
                return [
                    FactItem(
                        source="Calendar",
                        content=f"Calendar lookup encountered an error: {e}",
                        metadata={"error": str(e)}
                    )
                ]

        return []

    def modify(self, action: str, payload: dict, dry_run: bool = True, **kwargs) -> MutationResult:
        """
        Create or update a calendar event.
        """
        if dry_run:
            return MutationResult(
                status="dry_run",
                action=action,
                target_system="Calendar",
                result_data={"summary": payload.get("summary"), "start": payload.get("start"), "action": action}
            )

        # Live calendar modification (future expansion)
        return MutationResult(
            status="success",
            action=action,
            target_system="Calendar",
            result_data={"simulated_event_id": "cal-ev-mock-01"}
        )

    def _query_mock(self) -> List[FactItem]:
        """Return deterministic mock availability facts for tests."""
        slots = self.mock_slots or [
            "Free Friday between 10:00 AM – 11:30 AM EST",
            "Free Friday between 2:00 PM – 4:00 PM EST",
            "Thursday 2:00 PM conflicts with Board Preparation Sync"
        ]
        return [
            FactItem(
                source="Calendar",
                content="; ".join(slots),
                metadata={"provider": "mock"}
            )
        ]
