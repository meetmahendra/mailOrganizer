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
Daily Audit Digest Service.

Queries the database for all emails processed in a given time window
and compiles a structured digest for user review.

The digest includes:
  - All emails archived/muted (with rescue option)
  - Promotions emails (with bulk-delete option)
  - Low-confidence emails routed to @Review_Needed
  - Pending PM tasks awaiting approval
  - System alerts / quota errors
"""
import datetime
from typing import Optional


def get_digest(
    db,
    hours: int = 24,
    user_id: Optional[int] = None,
) -> dict:
    """
    Build the audit digest for the past `hours` hours.

    Returns a structured dict suitable for API response or email rendering.
    """
    from models import EmailProcessingLog, PMActionQueue

    since = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)

    # ---- Processed emails -----------------------------------------------
    query = db.query(EmailProcessingLog).filter(
        EmailProcessingLog.processed_at >= since
    )
    if user_id is not None:
        query = query.filter(EmailProcessingLog.user_id == user_id)

    logs = query.order_by(EmailProcessingLog.processed_at.desc()).all()

    archived      = []
    promotions    = []
    needs_review  = []
    system_alerts = []
    all_processed = []

    for log in logs:
        entry = {
            'gmail_id':         log.gmail_id,
            'subject':          log.subject,
            'sender':           log.sender,
            'category':         log.category,
            'urgency_score':    log.urgency_score,
            'actions_taken':    log.actions_taken,
            'processed_at':     log.processed_at.isoformat() if log.processed_at else None,
            'is_reply_necessary': log.is_reply_necessary,
            'reply_necessity_reason': log.reply_necessity_reason,
            'confidence_score': log.confidence_score,
        }
        all_processed.append(entry)

        category = log.category or ''
        actions  = log.actions_taken or []
        was_archived = any(
            a.get('action') in ('remove_inbox', 'safe_archive') for a in actions
        )

        if category == 'Promotions/Marketing':
            promotions.append(entry)
        elif category == 'Needs Review':
            needs_review.append(entry)
        elif category == 'System Alert':
            system_alerts.append(entry)
        elif was_archived:
            archived.append(entry)

    # ---- Pending PM tasks -----------------------------------------------
    pm_tasks = db.query(PMActionQueue).filter(
        PMActionQueue.created_at >= since,
        PMActionQueue.status == 'pending',
    ).all()

    pending_pm = [{
        'id':            t.id,
        'gmail_id':      t.gmail_id,
        'email_subject': t.email_subject,
        'email_sender':  t.email_sender,
        'summary':       t.summary,
        'priority':      t.priority,
        'project_key':   t.project_key,
        'assignee_email': t.assignee_email,
        'created_at':    t.created_at.isoformat() if t.created_at else None,
    } for t in pm_tasks]

    return {
        'generated_at':  datetime.datetime.utcnow().isoformat(),
        'period_hours':  hours,
        'summary': {
            'total_processed':     len(all_processed),
            'total_archived':      len(archived),
            'total_promotions':    len(promotions),
            'total_needs_review':  len(needs_review),
            'total_system_alerts': len(system_alerts),
            'pending_pm_tasks':    len(pending_pm),
        },
        'archived_emails':   archived,
        'promotions_emails': promotions,
        'needs_review':      needs_review,
        'system_alerts':     system_alerts,
        'pending_pm_tasks':  pending_pm,
    }