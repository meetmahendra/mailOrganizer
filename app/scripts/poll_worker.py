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
Background polling worker — V1.

Continuously polls all authenticated users' Gmail inboxes and runs every
unread email through the LangGraph pipeline.

DRY_RUN is read from the .env file, so the same flag that controls the
FastAPI server controls this worker automatically.

Usage (from d:\\mailOrganizer):
    python -m app.scripts.poll_worker
"""
import sys
import os
import time
import datetime

# Resolve app/ directory and project root so all imports work
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_DIR    = os.path.dirname(_SCRIPT_DIR)
_ROOT_DIR   = os.path.dirname(_APP_DIR)

sys.path.insert(0, _APP_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT_DIR, '.env'))

from database import SessionLocal, engine, Base
from models import User
from services.auth_service import credentials_from_json
from services.gmail_service import fetch_unread_emails
from pipeline.graph import run_pipeline

# Ensure all tables exist
Base.metadata.create_all(bind=engine)

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))


def _dry_run_flag() -> bool:
    return os.getenv("DRY_RUN", "true").strip().lower() != "false"


def process_user(user: User, db, dry_run: bool) -> None:
    if not user.credentials_json:
        print(f"  [SKIP] {user.email} - no credentials stored.")
        return

    try:
        creds      = credentials_from_json(user.credentials_json)
        raw_emails = fetch_unread_emails(creds, max_results=20)
        print(f"  [{user.email}] {len(raw_emails)} unread email(s) found.")

        for e in raw_emails:
            final_state = run_pipeline(
                email_data = e,
                creds      = creds,
                user_id    = user.id,
                dry_run    = dry_run,
            )
            category = final_state.get("category", "?")
            score    = final_state.get("urgency_score", "?")
            actions  = [a.get("action") for a in final_state.get("actions_taken", [])]
            mode_tag = "[DRY]" if dry_run else "[LIVE]"
            print(
                f"    {mode_tag} [{score}/10] {e['subject'][:50]!r} "
                f"-> {category} | {actions}"
            )
    except Exception as e:
        print(f"  [ERROR] {user.email}: {e}")


def poll_loop() -> None:
    dry_run  = _dry_run_flag()
    mode_str = "DRY_RUN (CSV only)" if dry_run else "[!] LIVE (Gmail mutations active)"

    print("=" * 60)
    print("  Email Organizer - Background Polling Worker V1")
    print(f"  Mode: {mode_str}")
    print(f"  Interval: every {POLL_INTERVAL}s  |  Ctrl+C to stop")
    print("=" * 60)

    while True:
        # Re-read DRY_RUN on every cycle so you can change it without restarting
        dry_run = _dry_run_flag()

        print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] Polling... (mode={'DRY_RUN' if dry_run else 'LIVE'})")
        db = SessionLocal()
        try:
            users = db.query(User).all()
            if not users:
                print("  No authenticated users. Visit /auth/login to authenticate.")
            for user in users:
                process_user(user, db, dry_run)
        finally:
            db.close()

        print(f"  Done. Sleeping {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    poll_loop()
