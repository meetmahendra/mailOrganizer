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
Thread-safe CSV audit writer — V2.

Every email processed by the pipeline — whether in DRY_RUN or live mode —
is appended here for a full audit trail at d:\\mailOrganizer\\audit_log.csv.

V2 additions:
  - confidence_score
  - is_reply_necessary
  - reply_necessity_reason
  - is_no_reply
  - is_vip
"""
import csv
import os
import threading
from datetime import datetime, timezone

_lock = threading.Lock()

# Resolve path relative to the project root (two levels above this file)
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(_APP_DIR, '..', 'audit_log.csv')
CSV_PATH = os.path.normpath(CSV_PATH)

FIELDNAMES = [
    'timestamp',
    'entry_point',
    'dry_run',
    'gmail_id',
    'subject',
    'sender',
    'is_no_reply',
    'is_vip',
    'category',
    'urgency_score',
    'confidence_score',
    'reasoning',
    'is_reply_necessary',
    'reply_necessity_reason',
    'context_tags',
    'suggested_reply_preview',   # First 300 chars to keep file manageable
    'planned_actions',
    'actions_taken',
    'calendar_context',
]


def write_audit_row(state: dict) -> None:
    """Append one row to the CSV audit log. Thread-safe."""
    suggested = (state.get('enriched_draft_reply') or state.get('suggested_reply') or '')
    row = {
        'timestamp':               datetime.now(timezone.utc).isoformat(),
        'entry_point':             state.get('entry_point', 'DRY_RUN'),
        'dry_run':                 state.get('dry_run', True),
        'gmail_id':                state.get('gmail_id', ''),
        'subject':                 state.get('subject', ''),
        'sender':                  state.get('sender', ''),
        'is_no_reply':             state.get('is_no_reply', False),
        'is_vip':                  state.get('is_vip', False),
        'category':                state.get('category', ''),
        'urgency_score':           state.get('urgency_score', ''),
        'confidence_score':        state.get('confidence_score', ''),
        'reasoning':               (state.get('reasoning') or '')[:200],
        'is_reply_necessary':      state.get('is_reply_necessary', ''),
        'reply_necessity_reason':  (state.get('reply_necessity_reason') or '')[:200],
        'context_tags':            '; '.join(state.get('context_tags') or []),
        'suggested_reply_preview': suggested[:300],
        'planned_actions':         _format_actions(state.get('gmail_actions') or []),
        'actions_taken':           _format_actions(state.get('actions_taken') or []),
        'calendar_context':        (state.get('calendar_context') or '')[:200],
    }
    with _lock:
        try:
            file_exists = os.path.isfile(CSV_PATH)
            with open(CSV_PATH, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row)
        except PermissionError:
            print(f"[CSV Audit] Warning: '{CSV_PATH}' is locked by another process (e.g. Excel). Skipping CSV write.")
        except Exception as e:
            print(f"[CSV Audit] Warning: Could not write to audit_log.csv: {e}")


def _format_actions(actions: list) -> str:
    """Compact human-readable representation of action list."""
    parts = []
    for a in actions:
        label  = a.get('label', '')
        status = a.get('status', '')
        base   = a.get('action', '')
        parts.append(f"{base}({label})[{status}]" if label else f"{base}[{status}]")
    return ' | '.join(parts)
