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
Email MCP Tools — Phase 1 (read) + Phase 2 (ingest + search).

Tools registered:
  list_emails          — list stored emails with pipeline tags
  get_email            — full email detail + classification
  get_processing_log   — paginated pipeline execution log
  search_emails        — natural-language → Gmail search via AI
  ingest_emails        — fetch unread Gmail + run LangGraph pipeline
                         (dry_run=True by default for safety)
"""
import json
import datetime
import os
import sys

from typing import Optional


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _get_db():
    """Create and return a new DB session (caller must close it)."""
    from database import SessionLocal
    return SessionLocal()


def _get_creds(db):
    """
    Fetch Google OAuth credentials for user_id=1.
    Raises ValueError if user is not authenticated.
    """
    from models import User
    from services.auth_service import credentials_from_json
    user = db.query(User).filter(User.id == 1).first()
    if not user or not user.credentials_json:
        raise ValueError(
            "User 1 is not authenticated. "
            "Start the FastAPI server and visit http://localhost:8000/auth/login first."
        )
    return credentials_from_json(user.credentials_json)


# ── Tool registration ──────────────────────────────────────────────────────────

def register_email_tools(mcp):
    """Register all email-related MCP tools onto the FastMCP instance."""

    @mcp.tool()
    def list_emails(
        urgency:  Optional[str] = None,
        category: Optional[str] = None,
        limit:    int           = 20,
    ) -> str:
        """
        List stored emails with their latest pipeline classification tags.

        Args:
            urgency:  Filter by urgency rating (e.g. 'High', 'Critical').
            category: Filter by category string (partial match).
            limit:    Maximum number of results to return (default 20).

        Returns:
            JSON array of email records with classification metadata.
        """
        db = _get_db()
        try:
            from models import Email, EmailTag
            query = (
                db.query(Email, EmailTag)
                  .join(EmailTag, Email.id == EmailTag.email_id, isouter=True)
            )
            if urgency:
                query = query.filter(EmailTag.urgency_rating.ilike(urgency))
            if category:
                query = query.filter(EmailTag.category.ilike(f"%{category}%"))

            rows = query.order_by(Email.received_at.desc()).limit(limit).all()
            result = [
                {
                    "id":             email.id,
                    "gmail_id":       email.gmail_id,
                    "subject":        email.subject,
                    "sender":         email.sender,
                    "snippet":        email.snippet,
                    "received_at":    email.received_at.isoformat() if email.received_at else None,
                    "category":       tag.category       if tag else None,
                    "urgency_score":  tag.urgency_score  if tag else None,
                    "context_tags":   tag.context_tags   if tag else [],
                }
                for email, tag in rows
            ]
            return json.dumps({"count": len(result), "emails": result}, default=str)
        finally:
            db.close()

    @mcp.tool()
    def get_email(email_id: int) -> str:
        """
        Get full email detail including body and latest pipeline classification.

        Args:
            email_id: The integer DB id of the email (from list_emails).

        Returns:
            JSON object with full email body, classification, and last pipeline run info.
        """
        db = _get_db()
        try:
            from models import Email, EmailTag, EmailProcessingLog
            result = (
                db.query(Email, EmailTag)
                  .join(EmailTag, Email.id == EmailTag.email_id, isouter=True)
                  .filter(Email.id == email_id)
                  .first()
            )
            if not result:
                return json.dumps({"error": f"Email {email_id} not found."})

            email, tag = result
            log_entry = (
                db.query(EmailProcessingLog)
                  .filter(EmailProcessingLog.gmail_id == email.gmail_id)
                  .order_by(EmailProcessingLog.processed_at.desc())
                  .first()
            )
            return json.dumps({
                "id":          email.id,
                "gmail_id":    email.gmail_id,
                "subject":     email.subject,
                "sender":      email.sender,
                "snippet":     email.snippet,
                "body":        email.body,
                "received_at": email.received_at.isoformat() if email.received_at else None,
                "classification": {
                    "category":        tag.category        if tag else None,
                    "urgency_score":   tag.urgency_score   if tag else None,
                    "context_tags":    tag.context_tags    if tag else [],
                    "suggested_reply": tag.suggested_reply if tag else None,
                } if tag else None,
                "latest_pipeline_run": {
                    "actions_taken":    log_entry.actions_taken,
                    "dry_run":          log_entry.dry_run,
                    "pipeline_version": log_entry.pipeline_version,
                    "processed_at":     log_entry.processed_at.isoformat() if log_entry.processed_at else None,
                } if log_entry else None,
            }, default=str)
        finally:
            db.close()

    @mcp.tool()
    def get_processing_log(
        limit:    int           = 50,
        dry_run:  Optional[bool] = None,
        category: Optional[str] = None,
    ) -> str:
        """
        Get the paginated pipeline execution log — one entry per email processed.

        Args:
            limit:    Max rows to return (default 50).
            dry_run:  If True, return only dry-run entries. If False, live-run only.
                      Omit to return all.
            category: Filter by email category (partial match).

        Returns:
            JSON array of pipeline log entries.
        """
        db = _get_db()
        try:
            from models import EmailProcessingLog
            query = db.query(EmailProcessingLog)
            if dry_run is not None:
                query = query.filter(EmailProcessingLog.dry_run == dry_run)
            if category:
                query = query.filter(EmailProcessingLog.category.ilike(f"%{category}%"))

            rows = query.order_by(EmailProcessingLog.processed_at.desc()).limit(limit).all()
            return json.dumps([
                {
                    "id":               r.id,
                    "gmail_id":         r.gmail_id,
                    "subject":          r.subject,
                    "sender":           r.sender,
                    "category":         r.category,
                    "urgency_score":    r.urgency_score,
                    "actions_taken":    r.actions_taken,
                    "dry_run":          r.dry_run,
                    "pipeline_version": r.pipeline_version,
                    "processed_at":     r.processed_at.isoformat() if r.processed_at else None,
                }
                for r in rows
            ], default=str)
        finally:
            db.close()

    @mcp.tool()
    def search_emails(
        query:       str,
        max_results: int = 20,
    ) -> str:
        """
        Search Gmail using natural language. The AI translates the query into a
        Gmail search operator string, then executes it against the Gmail API.

        Args:
            query:       Natural language search (e.g. "invoices from last week").
            max_results: Maximum number of results to return (default 20).

        Returns:
            JSON with the original query, the translated Gmail search string,
            and the list of matching emails.
        """
        db = _get_db()
        try:
            creds = _get_creds(db)
            from services.ai_service import translate_query_to_gmail
            from services.gmail_service import execute_gmail_search
            gmail_query = translate_query_to_gmail(query)
            results     = execute_gmail_search(creds, gmail_query, max_results=max_results)
            return json.dumps({
                "original_query": query,
                "gmail_query":    gmail_query,
                "result_count":   len(results),
                "results":        results,
            }, default=str)
        except ValueError as e:
            return json.dumps({"error": str(e)})
        finally:
            db.close()

    @mcp.tool()
    def ingest_emails(
        max_results: int  = 20,
        dry_run:     bool = True,
    ) -> str:
        """
        Fetch unread Gmail messages and run each through the LangGraph pipeline.

        The pipeline classifies, prioritises, drafts replies, handles calendar
        scheduling, and optionally creates PM tasks — depending on email content.

        SAFETY: dry_run defaults to True. Set dry_run=False ONLY when you want
        real Gmail mutations (labels, archive, trash, drafts) to happen.

        Args:
            max_results: How many unread emails to fetch (max 100, default 20).
            dry_run:     True = log actions to audit CSV only (Gmail untouched).
                         False = live Gmail mutations ENABLED.

        Returns:
            JSON with mode, count processed, and per-email pipeline results.
        """
        db = _get_db()
        try:
            creds = _get_creds(db)
            from services.gmail_service import fetch_unread_emails
            from pipeline.graph import run_pipeline
            from models import Email

            raw_emails = fetch_unread_emails(creds, max_results=max_results)
            results    = []

            for e in raw_emails:
                # Persist to local DB (idempotent)
                existing = db.query(Email).filter(Email.gmail_id == e["gmail_id"]).first()
                if not existing:
                    new_email = Email(
                        user_id   = 1,
                        gmail_id  = e["gmail_id"],
                        thread_id = e.get("thread_id"),
                        subject   = e["subject"],
                        sender    = e["sender"],
                        snippet   = e["snippet"],
                        body      = e["body"],
                        received_at = datetime.datetime.utcnow(),
                    )
                    db.add(new_email)
                    db.commit()
                    db.refresh(new_email)

                final_state = run_pipeline(
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
                "emails":    results,
            }, default=str)
        except ValueError as e:
            return json.dumps({"error": str(e)})
        finally:
            db.close()
