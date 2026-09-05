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

from datetime import datetime, timedelta, timezone
from typing import Optional, List
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials


def check_freebusy(
    creds: Credentials,
    time_min: Optional[datetime] = None,
    time_max: Optional[datetime] = None,
) -> dict:
    """
    Check the user's free/busy status for a given window.
    Defaults to the next 24 hours if no range is given.
    Returns a dict with 'is_free' bool and 'busy_slots' list.
    """
    try:
        service = build('calendar', 'v3', credentials=creds)

        now = datetime.now(timezone.utc)
        time_min = time_min or now
        time_max = time_max or (now + timedelta(hours=24))

        body = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "items": [{"id": "primary"}],
        }

        result = service.freebusy().query(body=body).execute()
        busy = result.get('calendars', {}).get('primary', {}).get('busy', [])

        return {
            "is_free": len(busy) == 0,
            "busy_slots": busy,
            "window_start": time_min.isoformat(),
            "window_end": time_max.isoformat(),
        }
    except HttpError as e:
        print(f"Calendar API error: {e}")
        return {"is_free": None, "busy_slots": [], "error": str(e)}


def get_upcoming_events(creds: Credentials, max_results: int = 5) -> List[dict]:
    """Fetch the next N upcoming events from the user's primary calendar."""
    try:
        service = build('calendar', 'v3', credentials=creds)
        now = datetime.now(timezone.utc).isoformat()

        events_result = service.events().list(
            calendarId='primary',
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime',
        ).execute()

        events = events_result.get('items', [])
        return [
            {
                'id': e.get('id'),
                'summary': e.get('summary', 'No title'),
                'start': e.get('start', {}).get('dateTime', e.get('start', {}).get('date')),
                'end': e.get('end', {}).get('dateTime', e.get('end', {}).get('date')),
                'attendees': [a.get('email') for a in e.get('attendees', [])],
            }
            for e in events
        ]
    except HttpError as e:
        print(f"Calendar events error: {e}")
        return []


def handle_scheduling_action(creds: Credentials, suggested_action: str) -> dict:
    """
    Inspect a 'suggested_action' from the AI tagger.
    If it involves scheduling, fetch free/busy and upcoming events.
    """
    scheduling_keywords = ['schedule', 'meeting', 'reschedule', 'calendar', 'appointment', 'call']
    action_lower = suggested_action.lower()

    if any(kw in action_lower for kw in scheduling_keywords):
        freebusy = check_freebusy(creds)
        events = get_upcoming_events(creds)
        return {
            "calendar_check_triggered": True,
            "freebusy": freebusy,
            "upcoming_events": events,
        }
    return {"calendar_check_triggered": False}
