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
Daily Audit Digest API routes.

GET  /digest/                     — get the digest for the last N hours
POST /digest/rescue/{gmail_id}    — rescue an email back to Inbox
POST /digest/trash                — mark email(s) for deletion (bulk or single)
POST /digest/trash/promotions     — bulk-delete all Promotions emails from a period
GET  /digest/pm/pending           — list pending PM tasks
POST /digest/pm/{task_id}/approve — approve a PM task for execution
POST /digest/pm/{task_id}/reject  — reject a PM task
POST /digest/pm/{task_id}/execute — execute an approved PM task
"""
import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models import User, EmailProcessingLog, PMActionQueue
from services.auth_service import credentials_from_json
from services.digest_service import get_digest
from services import pm_service

router = APIRouter()


# ── Digest endpoints ──────────────────────────────────────────────────────────

@router.get("/")
def get_daily_digest(
    hours:   int = Query(default=24, description="Time window in hours"),
    user_id: int = Query(default=1),
    db: Session = Depends(get_db),
):
    """
    Get the daily audit digest: all archived/muted emails and pending PM tasks
    from the past N hours. Review this to catch any misclassified emails.
    """
    return get_digest(db, hours=hours, user_id=user_id)


@router.post("/rescue/{gmail_id}")
def rescue_email(
    gmail_id: str,
    user_id:  int = Query(default=1),
    db: Session = Depends(get_db),
):
    """
    Rescue a muted/archived email back to the Inbox.
    Moves the email back to INBOX by restoring the INBOX label.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.credentials_json:
        raise HTTPException(status_code=401, detail="User not authenticated")

    creds = credentials_from_json(user.credentials_json)

    try:
        from googleapiclient.discovery import build
        service = build('gmail', 'v1', credentials=creds)
        service.users().messages().modify(
            userId='me', id=gmail_id,
            body={'addLabelIds': ['INBOX']}
        ).execute()
        return {"rescued": True, "gmail_id": gmail_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class TrashRequest(BaseModel):
    gmail_ids: List[str]
    confirm: bool = False   # Must be True to proceed


@router.post("/trash")
def trash_emails(
    request: TrashRequest,
    user_id: int = Query(default=1),
    db: Session = Depends(get_db),
):
    """
    Move selected emails to Trash. Requires confirm=true.
    This is the ONLY way the system permanently removes emails from view.
    """
    if not request.confirm:
        return {
            "trashed":  False,
            "message":  "Set confirm=true to proceed with deletion.",
            "count":    len(request.gmail_ids),
        }

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.credentials_json:
        raise HTTPException(status_code=401, detail="User not authenticated")

    creds = credentials_from_json(user.credentials_json)
    results = []
    for gmail_id in request.gmail_ids:
        try:
            from services.gmail_service import move_to_trash
            move_to_trash(creds, gmail_id)
            results.append({"gmail_id": gmail_id, "status": "trashed"})
        except Exception as e:
            results.append({"gmail_id": gmail_id, "status": f"error: {e}"})

    return {"trashed": True, "results": results}


@router.post("/trash/promotions")
def bulk_trash_promotions(
    hours:   int  = Query(default=24),
    confirm: bool = Query(default=False),
    user_id: int  = Query(default=1),
    db: Session = Depends(get_db),
):
    """
    Bulk delete all Promotions/Marketing emails processed in the last N hours.
    Requires confirm=true. Shows a preview first if confirm=false.
    """
    since = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)

    if not confirm:
        logs = db.query(EmailProcessingLog).filter(
            EmailProcessingLog.category == 'Promotions/Marketing',
            EmailProcessingLog.processed_at >= since,
        ).all()
        return {
            "confirm_required": True,
            "count":            len(logs),
            "message":          f"Add confirm=true to delete {len(logs)} promotions emails.",
            "emails":           [{"gmail_id": l.gmail_id, "subject": l.subject} for l in logs],
        }

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.credentials_json:
        raise HTTPException(status_code=401, detail="User not authenticated")

    logs  = db.query(EmailProcessingLog).filter(
        EmailProcessingLog.category == 'Promotions/Marketing',
        EmailProcessingLog.processed_at >= since,
    ).all()

    creds   = credentials_from_json(user.credentials_json)
    results = []
    for log in logs:
        try:
            from services.gmail_service import move_to_trash
            move_to_trash(creds, log.gmail_id)
            results.append({"gmail_id": log.gmail_id, "subject": log.subject, "status": "trashed"})
        except Exception as e:
            results.append({"gmail_id": log.gmail_id, "subject": log.subject, "status": f"error: {e}"})

    return {"bulk_trashed": True, "count": len(results), "results": results}


# ── PM Task endpoints ─────────────────────────────────────────────────────────

@router.get("/pm/pending")
def list_pending_pm_tasks(
    hours:   int = Query(default=24),
    db: Session = Depends(get_db),
):
    """List all pending PM tasks awaiting user approval."""
    since = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
    tasks = db.query(PMActionQueue).filter(
        PMActionQueue.status == 'pending',
        PMActionQueue.created_at >= since,
    ).order_by(PMActionQueue.created_at.desc()).all()

    return [{
        'id':            t.id,
        'gmail_id':      t.gmail_id,
        'email_subject': t.email_subject,
        'email_sender':  t.email_sender,
        'summary':       t.summary,
        'description':   t.description,
        'priority':      t.priority,
        'project_key':   t.project_key,
        'assignee_email': t.assignee_email,
        'created_at':    t.created_at.isoformat() if t.created_at else None,
    } for t in tasks]


@router.post("/pm/{task_id}/approve")
def approve_pm_task(task_id: int, db: Session = Depends(get_db)):
    """Approve a pending PM task. Does NOT execute it yet — call /execute next."""
    result = pm_service.approve_task(db, task_id)
    if 'error' in result:
        raise HTTPException(status_code=404, detail=result['error'])
    return result


@router.post("/pm/{task_id}/reject")
def reject_pm_task(task_id: int, db: Session = Depends(get_db)):
    """Reject a pending PM task."""
    result = pm_service.reject_task(db, task_id)
    if 'error' in result:
        raise HTTPException(status_code=404, detail=result['error'])
    return result


@router.post("/pm/{task_id}/execute")
def execute_pm_task(task_id: int, db: Session = Depends(get_db)):
    """
    Execute an approved PM task via the configured adapter.
    The task must be in 'approved' status (call /approve first).
    """
    result = pm_service.execute_approved_task(db, task_id)
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    return result
