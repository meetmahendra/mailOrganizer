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
MCP Resources — read-only data endpoints the orchestrator can reference.

Resources registered:
  gmail://pipeline-status   — current mode, stats, last run
  gmail://recent-emails     — last 10 processed emails with classification
"""
import json
import os


def _get_db():
    from database import SessionLocal
    return SessionLocal()


def register_resources(mcp):
    """Register MCP resources onto the FastMCP instance."""

    @mcp.resource("gmail://pipeline-status")
    def pipeline_status_resource() -> str:
        """
        Current pipeline mode and aggregate processing statistics.

        Returns a JSON snapshot of the pipeline state including mode,
        total emails processed, dry-run vs live counts, last run time,
        and a breakdown of emails by category.
        """
        db = _get_db()
        try:
            from models import EmailProcessingLog
            from sqlalchemy import func

            dry_run       = os.getenv("DRY_RUN", "true").strip().lower() != "false"
            total         = db.query(EmailProcessingLog).count()
            dry_run_count = db.query(EmailProcessingLog).filter(EmailProcessingLog.dry_run == True).count()
            live_count    = db.query(EmailProcessingLog).filter(EmailProcessingLog.dry_run == False).count()

            last_entry = (
                db.query(EmailProcessingLog)
                  .order_by(EmailProcessingLog.processed_at.desc())
                  .first()
            )
            category_counts = (
                db.query(EmailProcessingLog.category, func.count().label("count"))
                  .group_by(EmailProcessingLog.category)
                  .all()
            )
            return json.dumps({
                "mode":             "DRY_RUN" if dry_run else "LIVE",
                "dry_run":          dry_run,
                "total_processed":  total,
                "dry_run_runs":     dry_run_count,
                "live_runs":        live_count,
                "last_run_at":      last_entry.processed_at.isoformat() if last_entry and last_entry.processed_at else None,
                "category_breakdown": {row.category: row.count for row in category_counts},
            }, default=str)
        finally:
            db.close()

    @mcp.resource("gmail://recent-emails")
    def recent_emails_resource() -> str:
        """
        The 10 most recently processed emails with their pipeline classifications.

        Useful as context for the orchestrator to understand what the pipeline
        has seen recently before deciding what tools to call.
        """
        db = _get_db()
        try:
            from models import Email, EmailTag
            rows = (
                db.query(Email, EmailTag)
                  .join(EmailTag, Email.id == EmailTag.email_id, isouter=True)
                  .order_by(Email.received_at.desc())
                  .limit(10)
                  .all()
            )
            return json.dumps([
                {
                    "id":            email.id,
                    "gmail_id":      email.gmail_id,
                    "subject":       email.subject,
                    "sender":        email.sender,
                    "received_at":   email.received_at.isoformat() if email.received_at else None,
                    "category":      tag.category       if tag else None,
                    "urgency_score": tag.urgency_score  if tag else None,
                    "context_tags":  tag.context_tags   if tag else [],
                }
                for email, tag in rows
            ], default=str)
        finally:
            db.close()
