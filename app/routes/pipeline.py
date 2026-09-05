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
Pipeline management routes.

GET  /pipeline/status  — current mode, stats, last run
POST /pipeline/run     — manually trigger a pipeline batch for a user
"""
import os
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import User, EmailProcessingLog
from services.auth_service import credentials_from_json
from services.gmail_service import fetch_unread_emails
from pipeline.graph import run_pipeline

router = APIRouter()


def _dry_run_flag() -> bool:
    return os.getenv("DRY_RUN", "true").strip().lower() != "false"


@router.get("/status")
def pipeline_status(db: Session = Depends(get_db)):
    """Show current pipeline mode and aggregate processing statistics."""
    dry_run = _dry_run_flag()

    total_processed = db.query(EmailProcessingLog).count()
    dry_run_count   = db.query(EmailProcessingLog).filter(EmailProcessingLog.dry_run == True).count()
    live_count      = db.query(EmailProcessingLog).filter(EmailProcessingLog.dry_run == False).count()

    last_entry = (
        db.query(EmailProcessingLog)
          .order_by(EmailProcessingLog.processed_at.desc())
          .first()
    )

    # Category breakdown
    from sqlalchemy import func
    category_counts = (
        db.query(EmailProcessingLog.category, func.count().label("count"))
          .group_by(EmailProcessingLog.category)
          .all()
    )

    return {
        "mode":             "DRY_RUN" if dry_run else "LIVE",
        "dry_run":          dry_run,
        "audit_log_path":   os.path.normpath(os.path.join(
                                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                                "audit_log.csv"
                            )),
        "total_processed":  total_processed,
        "dry_run_runs":     dry_run_count,
        "live_runs":        live_count,
        "last_run_at":      last_entry.processed_at if last_entry else None,
        "category_breakdown": {row.category: row.count for row in category_counts},
    }


@router.post("/run")
def run_pipeline_manually(
    user_id:     int = Query(default=1),
    max_results: int = Query(default=10, le=50),
    db: Session = Depends(get_db),
):
    """
    Manually trigger the LangGraph pipeline for a user.
    Fetches up to max_results unread emails and processes them.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.credentials_json:
        raise HTTPException(
            status_code=401,
            detail="User not found or not authenticated. Visit /auth/login first.",
        )

    creds   = credentials_from_json(user.credentials_json)
    dry_run = _dry_run_flag()

    raw_emails = fetch_unread_emails(creds, max_results=max_results)
    results    = []

    source_tag = "DRY_RUN" if dry_run else "API_BATCH"
    for e in raw_emails:
        final_state = run_pipeline(
            email_data  = e,
            creds       = creds,
            user_id     = user_id,
            dry_run     = dry_run,
            entry_point = source_tag,
        )
        results.append({
            "gmail_id":      e['gmail_id'],
            "subject":       e['subject'],
            "category":      final_state.get("category"),
            "urgency_score": final_state.get("urgency_score"),
            "actions_taken": final_state.get("actions_taken"),
        })

    from pipeline.audit_manager import AUDIT_DIR
    return {
        "mode":             "DRY_RUN" if dry_run else "LIVE",
        "processed":        len(results),
        "audit_logs_dir":   AUDIT_DIR,
        "results":          results,
    }
