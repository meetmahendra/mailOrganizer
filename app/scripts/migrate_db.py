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
Lightweight SQLite migration helper - V0 -> V1.

Adds the three new columns to email_tags (if they don't exist) and
creates the email_processing_log table (if it doesn't exist).

Run ONCE after upgrading from V0:
    cd d:\\mailOrganizer
    python -m app.scripts.migrate_db

Safe to run multiple times - it skips columns/tables that already exist.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env'))

from database import engine, Base
from models import EmailTag, EmailProcessingLog  # noqa: ensure models are imported
import sqlalchemy as sa


def column_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def migrate():
    print("Running V0 -> V1 migration...")
    with engine.connect() as conn:
        # email_tags: add new V1 columns
        for col_name, col_type in [
            ("category",        "VARCHAR"),
            ("urgency_score",   "INTEGER"),
            ("suggested_reply", "TEXT"),
        ]:
            if not column_exists(conn, "email_tags", col_name):
                conn.execute(sa.text(f"ALTER TABLE email_tags ADD COLUMN {col_name} {col_type}"))
                print(f"  [+] Added email_tags.{col_name}")
            else:
                print(f"  [ok] email_tags.{col_name} already exists - skipped")

        # emails: add thread_id / user_id if missing
        for col_name, col_type in [
            ("thread_id", "VARCHAR"),
            ("user_id",   "INTEGER"),
        ]:
            if not column_exists(conn, "emails", col_name):
                conn.execute(sa.text(f"ALTER TABLE emails ADD COLUMN {col_name} {col_type}"))
                print(f"  [+] Added emails.{col_name}")
            else:
                print(f"  [ok] emails.{col_name} already exists - skipped")

        conn.commit()

    # Create new tables (safe if they already exist)
    Base.metadata.create_all(bind=engine)
    print("  [ok] email_processing_log table ensured")
    print("\nMigration complete.")


if __name__ == "__main__":
    migrate()
