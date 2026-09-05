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
Email routes — V1.

Changes from V0:
  • POST /emails/ingest now runs every email through the LangGraph pipeline.
  • GET  /emails/       returns EmailProcessingLog rows (pipeline output).
  • GET  /emails/{id}   returns full email + latest pipeline log entry.
  • GET  /emails/log    paginated view of the EmailProcessingLog table.
"""
import os
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import User, Email, EmailTag, EmailProcessingLog
from services.auth_service import credentials_from_json
from services.gmail_service import fetch_unread_emails
from pipeline.graph import run_pipeline

router = APIRouter()


def _dry_run_flag() -> bool:
    return os.getenv("DRY_RUN", "true").strip().lower() != "false"


def _get_creds(user_id: int, db: Session):
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.credentials_json:
        raise HTTPException(
            status_code=401,
            detail="User not found or not authenticated. Visit /auth/login first.",
        )
    return credentials_from_json(user.credentials_json)


# ── POST /emails/ingest ───────────────────────────────────────────────────────

@router.post("/ingest")
def ingest_emails(
    user_id:     int = Query(default=1),
    max_results: int = Query(default=20, le=100),
    db: Session = Depends(get_db),
):
    """
    Fetch unread Gmail messages and run each through the LangGraph pipeline.
    DRY_RUN=true  → actions logged to CSV, nothing written to Gmail.
    DRY_RUN=false → real Gmail mutations (labels, archive, drafts, trash).
    """
    creds   = _get_creds(user_id, db)
    dry_run = _dry_run_flag()

    raw_emails = fetch_unread_emails(creds, max_results=max_results)
    results    = []

    for e in raw_emails:
        # Persist email to local DB (skip if already stored)
        existing = db.query(Email).filter(Email.gmail_id == e['gmail_id']).first()
        if not existing:
            new_email = Email(
                user_id   = user_id,
                gmail_id  = e['gmail_id'],
                thread_id = e.get('thread_id'),
                subject   = e['subject'],
                sender    = e['sender'],
                snippet   = e['snippet'],
                body      = e['body'],
                received_at = datetime.datetime.utcnow(),
            )
            db.add(new_email)
            db.commit()
            db.refresh(new_email)

        # Run pipeline (classify → plan → [calendar] → execute → log)
        final_state = run_pipeline(
            email_data = e,
            creds      = creds,
            user_id    = user_id,
            dry_run    = dry_run,
        )

        results.append({
            "gmail_id":      e['gmail_id'],
            "subject":       e['subject'],
            "category":      final_state.get("category"),
            "urgency_score": final_state.get("urgency_score"),
            "actions_taken": final_state.get("actions_taken"),
            "dry_run":       dry_run,
        })

    return {
        "mode":       "DRY_RUN" if dry_run else "LIVE",
        "processed":  len(results),
        "emails":     results,
    }


# ── GET /emails/ ──────────────────────────────────────────────────────────────

@router.get("/")
def list_emails(
    urgency:  Optional[str] = None,
    category: Optional[str] = None,
    limit:    int           = 20,
    db: Session = Depends(get_db),
):
    """List stored emails with their latest V1 pipeline tags."""
    query = (
        db.query(Email, EmailTag)
          .join(EmailTag, Email.id == EmailTag.email_id, isouter=True)
    )
    if urgency:
        query = query.filter(EmailTag.urgency_rating.ilike(urgency))
    if category:
        query = query.filter(EmailTag.category.ilike(f"%{category}%"))

    rows = query.order_by(Email.received_at.desc()).limit(limit).all()
    return [
        {
            "id":          email.id,
            "gmail_id":    email.gmail_id,
            "subject":     email.subject,
            "sender":      email.sender,
            "snippet":     email.snippet,
            "received_at": email.received_at,
            "category":    tag.category       if tag else None,
            "urgency_score": tag.urgency_score if tag else None,
            "context_tags": tag.context_tags  if tag else [],
        }
        for email, tag in rows
    ]


# ── GET /emails/log ───────────────────────────────────────────────────────────

@router.get("/log")
def get_processing_log(
    limit:    int  = 50,
    dry_run:  Optional[bool] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Paginated view of the EmailProcessingLog — one row per pipeline execution."""
    query = db.query(EmailProcessingLog)
    if dry_run is not None:
        query = query.filter(EmailProcessingLog.dry_run == dry_run)
    if category:
        query = query.filter(EmailProcessingLog.category.ilike(f"%{category}%"))

    rows = query.order_by(EmailProcessingLog.processed_at.desc()).limit(limit).all()
    return [
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
            "processed_at":     r.processed_at,
        }
        for r in rows
    ]


# ── GET /emails/{email_id} ────────────────────────────────────────────────────

@router.get("/{email_id}")
def get_email(email_id: int, db: Session = Depends(get_db)):
    """Full email detail including body and latest pipeline classification."""
    result = (
        db.query(Email, EmailTag)
          .join(EmailTag, Email.id == EmailTag.email_id, isouter=True)
          .filter(Email.id == email_id)
          .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail="Email not found.")

    email, tag = result

    # Fetch most recent pipeline log entry for this gmail_id
    log_entry = (
        db.query(EmailProcessingLog)
          .filter(EmailProcessingLog.gmail_id == email.gmail_id)
          .order_by(EmailProcessingLog.processed_at.desc())
          .first()
    )

    return {
        "id":          email.id,
        "gmail_id":    email.gmail_id,
        "subject":     email.subject,
        "sender":      email.sender,
        "snippet":     email.snippet,
        "body":        email.body,
        "received_at": email.received_at,
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
            "processed_at":     log_entry.processed_at,
        } if log_entry else None,
    }
