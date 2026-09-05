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
Pipeline MCP Tools.

Tools registered:
  get_pipeline_status  — current mode, aggregate stats, last run, category breakdown
  run_pipeline         — manually trigger the LangGraph pipeline for a batch of emails
                         (dry_run=True by default for safety)
"""
import json
import os


def _get_db():
    from database import SessionLocal
    return SessionLocal()


def _get_creds(db):
    from models import User
    from services.auth_service import credentials_from_json
    user = db.query(User).filter(User.id == 1).first()
    if not user or not user.credentials_json:
        raise ValueError(
            "User 1 is not authenticated. "
            "Start the FastAPI server and visit http://localhost:8000/auth/login first."
        )
    return credentials_from_json(user.credentials_json)


def register_pipeline_tools(mcp):
    """Register pipeline management tools onto the FastMCP instance."""

    @mcp.tool()
    def get_pipeline_status() -> str:
        """
        Get the current pipeline mode and aggregate processing statistics.

        Returns:
            JSON with mode (DRY_RUN / LIVE), total processed, last run timestamp,
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

    @mcp.tool()
    def run_pipeline(
        max_results: int  = 10,
        dry_run:     bool = True,
    ) -> str:
        """
        Manually trigger the LangGraph email pipeline for the authenticated user.

        Fetches up to max_results unread Gmail messages and processes each one
        through the full pipeline: pre_check → classify → plan → [calendar] → execute → log.

        SAFETY: dry_run defaults to True. Set dry_run=False ONLY when you want
        real Gmail mutations (labels, archive, trash, drafts) to happen.

        Args:
            max_results: How many unread emails to process (max 50, default 10).
            dry_run:     True = audit log only. False = live Gmail mutations ENABLED.

        Returns:
            JSON with mode, count processed, and per-email pipeline results.
        """
        db = _get_db()
        try:
            creds = _get_creds(db)
            from services.gmail_service import fetch_unread_emails
            from pipeline.graph import run_pipeline as _run_pipeline

            raw_emails = fetch_unread_emails(creds, max_results=max_results)
            results    = []
            for e in raw_emails:
                final_state = _run_pipeline(
                    email_data = e,
                    creds      = creds,
                    user_id    = 1,
                    dry_run    = dry_run,
                )
                results.append({
                    "gmail_id":      e["gmail_id"],
                    "subject":       e["subject"],
                    "category":      final_state.get("category"),
                    "urgency_score": final_state.get("urgency_score"),
                    "actions_taken": final_state.get("actions_taken"),
                })
            return json.dumps({
                "mode":      "DRY_RUN" if dry_run else "LIVE",
                "processed": len(results),
                "results":   results,
            }, default=str)
        except ValueError as e:
            return json.dumps({"error": str(e)})
        finally:
            db.close()
