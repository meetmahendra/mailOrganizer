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
Gmail Organizer — MCP Server (SSE Transport — no external mcp package required).

Implements the Model Context Protocol 2024-11-05 specification directly using
FastAPI + Starlette SSE, so no internet/PyPI access is needed.

Protocol flow:
  1. Client connects to GET /sse  → receives SSE stream
  2. Server immediately sends:    event: endpoint
                                  data: /messages?session_id=<uuid>
  3. Client sends JSON-RPC 2.0 requests to POST /messages?session_id=<uuid>
  4. Server replies via the SSE stream with JSON-RPC responses

Endpoints:
  GET  /sse               — SSE event stream (MCP transport)
  POST /messages          — JSON-RPC message inbox
  GET  /health            — health check

Run:
    cd d:\\mailOrganizer
    python -m mcp_server.server

Then point your MCP client at:  http://localhost:8001/sse
"""
import os
import sys
import json
import uuid
import asyncio
import datetime
from typing import Any, Dict, Optional, List

# ── Path bootstrap ─────────────────────────────────────────────────────────────
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP_DIR  = os.path.join(_ROOT_DIR, "app")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT_DIR, ".env"))

# ── DB init ────────────────────────────────────────────────────────────────────
from database import engine, Base
Base.metadata.create_all(bind=engine)

# ── FastAPI app ────────────────────────────────────────────────────────────────
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware

app = FastAPI(title="Gmail Organizer MCP Server", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Session registry: session_id → asyncio.Queue ──────────────────────────────
_sessions: Dict[str, asyncio.Queue] = {}


# ══════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ══════════════════════════════════════════════════════════════════════════════

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
            "Visit http://localhost:8000/auth/login first."
        )
    return credentials_from_json(user.credentials_json)


# ══════════════════════════════════════════════════════════════════════════════
# TOOL & RESOURCE REGISTRIES
# ══════════════════════════════════════════════════════════════════════════════

# name -> {"name", "description", "inputSchema", "handler"}
TOOLS: Dict[str, dict] = {}

# uri  -> {"uri", "name", "description", "mimeType", "handler"}
RESOURCES: Dict[str, dict] = {}


def register_tool(name: str, description: str, input_schema: dict):
    """Decorator factory — registers a sync tool handler by name."""
    def decorator(fn):
        TOOLS[name] = {
            "name":        name,
            "description": description,
            "inputSchema": input_schema,
            "handler":     fn,
        }
        return fn
    return decorator


def register_resource(uri: str, name: str, description: str, mime_type: str = "application/json"):
    """Decorator factory — registers a sync resource reader by URI."""
    def decorator(fn):
        RESOURCES[uri] = {
            "uri":         uri,
            "name":        name,
            "description": description,
            "mimeType":    mime_type,
            "handler":     fn,
        }
        return fn
    return decorator


# ══════════════════════════════════════════════════════════════════════════════
# EMAIL TOOLS
# ══════════════════════════════════════════════════════════════════════════════

@register_tool(
    name="list_emails",
    description=(
        "List stored emails with their latest pipeline classification tags. "
        "Optionally filter by urgency or category. Returns up to `limit` emails "
        "ordered by most recently received."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "urgency":  {"type": "string",  "description": "Filter by urgency (e.g. High, Critical, Low, Medium)."},
            "category": {"type": "string",  "description": "Partial category match (e.g. Promotions, Work)."},
            "limit":    {"type": "integer", "description": "Max results (default 20).", "default": 20},
        },
    },
)
def list_emails(urgency=None, category=None, limit=20):
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
        rows = query.order_by(Email.received_at.desc()).limit(int(limit)).all()
        result = [
            {
                "id":            email.id,
                "gmail_id":      email.gmail_id,
                "subject":       email.subject,
                "sender":        email.sender,
                "snippet":       email.snippet,
                "received_at":   email.received_at.isoformat() if email.received_at else None,
                "category":      tag.category       if tag else None,
                "urgency_score": tag.urgency_score  if tag else None,
                "context_tags":  tag.context_tags   if tag else [],
            }
            for email, tag in rows
        ]
        return {"count": len(result), "emails": result}
    finally:
        db.close()


@register_tool(
    name="get_email",
    description=(
        "Get full email detail including body and the latest pipeline classification "
        "and most recent pipeline run info for a given email."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "email_id": {"type": "integer", "description": "The integer DB id (from list_emails)."},
        },
        "required": ["email_id"],
    },
)
def get_email(email_id):
    db = _get_db()
    try:
        from models import Email, EmailTag, EmailProcessingLog
        result = (
            db.query(Email, EmailTag)
              .join(EmailTag, Email.id == EmailTag.email_id, isouter=True)
              .filter(Email.id == int(email_id))
              .first()
        )
        if not result:
            return {"error": f"Email {email_id} not found."}
        email, tag = result
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
        }
    finally:
        db.close()


@register_tool(
    name="get_processing_log",
    description="Get the paginated pipeline execution log — one entry per email processed by the pipeline.",
    input_schema={
        "type": "object",
        "properties": {
            "limit":    {"type": "integer", "description": "Max rows (default 50).", "default": 50},
            "dry_run":  {"type": "boolean", "description": "Filter by dry_run mode. Omit for all."},
            "category": {"type": "string",  "description": "Partial category filter."},
        },
    },
)
def get_processing_log(limit=50, dry_run=None, category=None):
    db = _get_db()
    try:
        from models import EmailProcessingLog
        query = db.query(EmailProcessingLog)
        if dry_run is not None:
            query = query.filter(EmailProcessingLog.dry_run == dry_run)
        if category:
            query = query.filter(EmailProcessingLog.category.ilike(f"%{category}%"))
        rows = query.order_by(EmailProcessingLog.processed_at.desc()).limit(int(limit)).all()
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
                "processed_at":     r.processed_at.isoformat() if r.processed_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()


@register_tool(
    name="search_emails",
    description=(
        "Search Gmail using natural language. The AI translates the natural language "
        "query into a Gmail search operator string and executes it against the Gmail API."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query":       {"type": "string",  "description": "Natural language search (e.g. 'invoices from last week')."},
            "max_results": {"type": "integer", "description": "Max results (default 20).", "default": 20},
        },
        "required": ["query"],
    },
)
def search_emails(query, max_results=20):
    db = _get_db()
    try:
        creds = _get_creds(db)
        from services.ai_service import translate_query_to_gmail
        from services.gmail_service import execute_gmail_search
        gmail_query = translate_query_to_gmail(query)
        results = execute_gmail_search(creds, gmail_query, max_results=int(max_results))
        return {
            "original_query": query,
            "gmail_query":    gmail_query,
            "result_count":   len(results),
            "results":        results,
        }
    except ValueError as e:
        return {"error": str(e)}
    finally:
        db.close()


@register_tool(
    name="ingest_emails",
    description=(
        "Fetch unread Gmail messages and run each through the full LangGraph pipeline "
        "(pre_check → classify → plan_actions → [calendar] → execute → log). "
        "SAFETY: dry_run defaults to True — no Gmail mutations occur unless dry_run=False."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "max_results": {"type": "integer", "description": "How many unread emails to fetch (max 100, default 20).", "default": 20},
            "dry_run":     {"type": "boolean", "description": "True=audit log only (safe). False=live Gmail mutations ENABLED.", "default": True},
        },
    },
)
def ingest_emails(max_results=20, dry_run=True):
    db = _get_db()
    try:
        creds = _get_creds(db)
        from services.gmail_service import fetch_unread_emails
        from pipeline.graph import run_pipeline
        from models import Email

        raw_emails = fetch_unread_emails(creds, max_results=int(max_results))
        results = []
        for e in raw_emails:
            existing = db.query(Email).filter(Email.gmail_id == e["gmail_id"]).first()
            if not existing:
                new_email = Email(
                    user_id=1,
                    gmail_id=e["gmail_id"],
                    thread_id=e.get("thread_id"),
                    subject=e["subject"],
                    sender=e["sender"],
                    snippet=e["snippet"],
                    body=e["body"],
                    received_at=datetime.datetime.utcnow(),
                )
                db.add(new_email)
                db.commit()
                db.refresh(new_email)

            final_state = run_pipeline(
                email_data=e,
                creds=creds,
                user_id=1,
                dry_run=bool(dry_run),
            )
            results.append({
                "gmail_id":      e["gmail_id"],
                "subject":       e["subject"],
                "category":      final_state.get("category"),
                "urgency_score": final_state.get("urgency_score"),
                "actions_taken": final_state.get("actions_taken"),
            })
        return {
            "mode":      "DRY_RUN" if dry_run else "LIVE",
            "processed": len(results),
            "emails":    results,
        }
    except ValueError as e:
        return {"error": str(e)}
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE TOOLS
# ══════════════════════════════════════════════════════════════════════════════

@register_tool(
    name="get_pipeline_status",
    description=(
        "Get the current pipeline mode (DRY_RUN / LIVE), aggregate processing statistics, "
        "last run timestamp, and a breakdown of emails by category."
    ),
    input_schema={"type": "object", "properties": {}},
)
def get_pipeline_status():
    db = _get_db()
    try:
        from models import EmailProcessingLog
        from sqlalchemy import func
        dry_run  = os.getenv("DRY_RUN", "true").strip().lower() != "false"
        total    = db.query(EmailProcessingLog).count()
        dr_cnt   = db.query(EmailProcessingLog).filter(EmailProcessingLog.dry_run == True).count()
        live_cnt = db.query(EmailProcessingLog).filter(EmailProcessingLog.dry_run == False).count()
        last     = db.query(EmailProcessingLog).order_by(EmailProcessingLog.processed_at.desc()).first()
        cats     = (
            db.query(EmailProcessingLog.category, func.count().label("count"))
              .group_by(EmailProcessingLog.category).all()
        )
        return {
            "mode":             "DRY_RUN" if dry_run else "LIVE",
            "dry_run":          dry_run,
            "total_processed":  total,
            "dry_run_runs":     dr_cnt,
            "live_runs":        live_cnt,
            "last_run_at":      last.processed_at.isoformat() if last and last.processed_at else None,
            "category_breakdown": {r.category: r.count for r in cats},
        }
    finally:
        db.close()


@register_tool(
    name="run_pipeline",
    description=(
        "Manually trigger the LangGraph email pipeline for a batch of unread emails. "
        "Processes each through: pre_check → classify → plan → [calendar] → execute → log. "
        "SAFETY: dry_run defaults to True."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "max_results": {"type": "integer", "description": "Emails to process (max 50, default 10).", "default": 10},
            "dry_run":     {"type": "boolean", "description": "True=audit log only. False=live Gmail mutations ENABLED.", "default": True},
        },
    },
)
def run_pipeline_tool(max_results=10, dry_run=True):
    db = _get_db()
    try:
        creds = _get_creds(db)
        from services.gmail_service import fetch_unread_emails
        from pipeline.graph import run_pipeline
        raw_emails = fetch_unread_emails(creds, max_results=int(max_results))
        results = []
        for e in raw_emails:
            fs = run_pipeline(email_data=e, creds=creds, user_id=1, dry_run=bool(dry_run))
            results.append({
                "gmail_id":      e["gmail_id"],
                "subject":       e["subject"],
                "category":      fs.get("category"),
                "urgency_score": fs.get("urgency_score"),
                "actions_taken": fs.get("actions_taken"),
            })
        return {"mode": "DRY_RUN" if dry_run else "LIVE", "processed": len(results), "results": results}
    except ValueError as e:
        return {"error": str(e)}
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# DIGEST TOOLS
# ══════════════════════════════════════════════════════════════════════════════

@register_tool(
    name="get_digest",
    description=(
        "Get the daily audit digest: archived emails, promotions, needs-review emails, "
        "system alerts, and pending PM tasks from the past N hours. "
        "Use this to review what the pipeline did and catch misclassified emails."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "hours": {"type": "integer", "description": "Time window in hours (default 24).", "default": 24},
        },
    },
)
def get_digest(hours=24):
    db = _get_db()
    try:
        from services.digest_service import get_digest as _gd
        return _gd(db, hours=int(hours), user_id=1)
    finally:
        db.close()


@register_tool(
    name="rescue_email",
    description=(
        "Rescue a muted or archived email back to the Gmail Inbox. "
        "Use this when the pipeline incorrectly archived an email you need."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "gmail_id": {"type": "string", "description": "Gmail message ID (from get_digest or list_emails)."},
        },
        "required": ["gmail_id"],
    },
)
def rescue_email(gmail_id):
    db = _get_db()
    try:
        creds = _get_creds(db)
        from googleapiclient.discovery import build
        svc = build("gmail", "v1", credentials=creds)
        svc.users().messages().modify(
            userId="me", id=gmail_id, body={"addLabelIds": ["INBOX"]}
        ).execute()
        return {"rescued": True, "gmail_id": gmail_id}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Gmail API error: {e}"}
    finally:
        db.close()


@register_tool(
    name="trash_emails",
    description=(
        "Move selected emails to Trash. "
        "SAFETY: dry_run defaults to True (preview only). "
        "Set dry_run=False AND confirm=True to actually delete."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "gmail_ids": {
                "type":        "array",
                "items":       {"type": "string"},
                "description": "List of Gmail message IDs to trash.",
            },
            "confirm": {"type": "boolean", "description": "Must be True to proceed with deletion.", "default": False},
            "dry_run": {"type": "boolean", "description": "True=preview only (safe). False=real deletion.", "default": True},
        },
        "required": ["gmail_ids"],
    },
)
def trash_emails(gmail_ids, confirm=False, dry_run=True):
    if dry_run:
        return {
            "dry_run": True,
            "message": "DRY RUN: No emails deleted. Pass dry_run=False and confirm=True to delete.",
            "would_trash": gmail_ids,
            "count": len(gmail_ids),
        }
    if not confirm:
        return {
            "trashed": False,
            "message": "Set confirm=True and dry_run=False to proceed with deletion.",
            "count": len(gmail_ids),
        }
    db = _get_db()
    try:
        creds = _get_creds(db)
        from services.gmail_service import move_to_trash
        results = []
        for gid in gmail_ids:
            try:
                move_to_trash(creds, gid)
                results.append({"gmail_id": gid, "status": "trashed"})
            except Exception as e:
                results.append({"gmail_id": gid, "status": f"error: {e}"})
        return {"trashed": True, "results": results}
    except ValueError as e:
        return {"error": str(e)}
    finally:
        db.close()


@register_tool(
    name="bulk_trash_promotions",
    description=(
        "Bulk-delete all Promotions/Marketing emails processed in the last N hours. "
        "SAFETY: dry_run defaults to True. Always call first without confirm to see a preview."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "hours":   {"type": "integer", "description": "Time window in hours (default 24).", "default": 24},
            "confirm": {"type": "boolean", "description": "Must be True to execute deletion.", "default": False},
            "dry_run": {"type": "boolean", "description": "True=preview only. False=real deletion.", "default": True},
        },
    },
)
def bulk_trash_promotions(hours=24, confirm=False, dry_run=True):
    db = _get_db()
    try:
        from models import EmailProcessingLog
        since = datetime.datetime.utcnow() - datetime.timedelta(hours=int(hours))
        logs  = db.query(EmailProcessingLog).filter(
            EmailProcessingLog.category == "Promotions/Marketing",
            EmailProcessingLog.processed_at >= since,
        ).all()
        preview = [{"gmail_id": l.gmail_id, "subject": l.subject} for l in logs]

        if dry_run:
            return {
                "dry_run": True,
                "message": f"DRY RUN: {len(logs)} promotions emails would be trashed. Pass dry_run=False and confirm=True to execute.",
                "emails":  preview,
                "count":   len(preview),
            }
        if not confirm:
            return {
                "confirm_required": True,
                "count":            len(logs),
                "message":          f"Add confirm=True and dry_run=False to delete {len(logs)} emails.",
                "emails":           preview,
            }
        creds = _get_creds(db)
        from services.gmail_service import move_to_trash
        results = []
        for log in logs:
            try:
                move_to_trash(creds, log.gmail_id)
                results.append({"gmail_id": log.gmail_id, "subject": log.subject, "status": "trashed"})
            except Exception as e:
                results.append({"gmail_id": log.gmail_id, "subject": log.subject, "status": f"error: {e}"})
        return {"bulk_trashed": True, "count": len(results), "results": results}
    except ValueError as e:
        return {"error": str(e)}
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# PM TOOLS
# ══════════════════════════════════════════════════════════════════════════════

@register_tool(
    name="list_pending_pm_tasks",
    description=(
        "List all pending project management tasks awaiting user approval. "
        "The pipeline queues tasks when emails require Jira action."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "hours": {"type": "integer", "description": "Time window in hours (default 24).", "default": 24},
        },
    },
)
def list_pending_pm_tasks(hours=24):
    db = _get_db()
    try:
        from models import PMActionQueue
        since = datetime.datetime.utcnow() - datetime.timedelta(hours=int(hours))
        tasks = db.query(PMActionQueue).filter(
            PMActionQueue.status == "pending",
            PMActionQueue.created_at >= since,
        ).order_by(PMActionQueue.created_at.desc()).all()
        return [
            {
                "id":             t.id,
                "gmail_id":       t.gmail_id,
                "email_subject":  t.email_subject,
                "email_sender":   t.email_sender,
                "summary":        t.summary,
                "description":    t.description,
                "priority":       t.priority,
                "project_key":    t.project_key,
                "assignee_email": t.assignee_email,
                "created_at":     t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks
        ]
    finally:
        db.close()


@register_tool(
    name="approve_pm_task",
    description="Approve a pending PM task (marks it ready for execution). Call execute_pm_task next.",
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "integer", "description": "PM task ID from list_pending_pm_tasks."},
        },
        "required": ["task_id"],
    },
)
def approve_pm_task(task_id):
    db = _get_db()
    try:
        from services import pm_service
        return pm_service.approve_task(db, int(task_id))
    finally:
        db.close()


@register_tool(
    name="reject_pm_task",
    description="Reject a pending PM task. It will be marked rejected and excluded from future pending lists.",
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "integer", "description": "PM task ID from list_pending_pm_tasks."},
        },
        "required": ["task_id"],
    },
)
def reject_pm_task(task_id):
    db = _get_db()
    try:
        from services import pm_service
        return pm_service.reject_task(db, int(task_id))
    finally:
        db.close()


@register_tool(
    name="execute_pm_task",
    description=(
        "Execute an approved PM task via the configured adapter (e.g. Jira). "
        "IMPORTANT: The task must be in approved status — call approve_pm_task first."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "integer", "description": "Approved PM task ID."},
        },
        "required": ["task_id"],
    },
)
def execute_pm_task(task_id):
    db = _get_db()
    try:
        from services import pm_service
        return pm_service.execute_approved_task(db, int(task_id))
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# MCP RESOURCES
# ══════════════════════════════════════════════════════════════════════════════

@register_resource(
    uri="gmail://pipeline-status",
    name="Pipeline Status",
    description="Current pipeline mode and aggregate processing statistics.",
)
def _pipeline_status_resource():
    return get_pipeline_status()


@register_resource(
    uri="gmail://recent-emails",
    name="Recent Emails",
    description="The 10 most recently processed emails with pipeline classifications.",
)
def _recent_emails_resource():
    return list_emails(limit=10)


# ══════════════════════════════════════════════════════════════════════════════
# MCP JSON-RPC 2.0 PROTOCOL HANDLER
# ══════════════════════════════════════════════════════════════════════════════

SERVER_INFO      = {"name": "gmail-organizer", "version": "1.0.0"}
PROTOCOL_VERSION = "2024-11-05"


def _ok(request_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _err(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _handle_rpc(msg: dict) -> Optional[dict]:
    """Dispatch a JSON-RPC 2.0 message and return the response dict (or None for notifications)."""
    method = msg.get("method", "")
    rid    = msg.get("id")
    params = msg.get("params") or {}

    # ── Lifecycle ────────────────────────────────────────────────────────────
    if method == "initialize":
        return _ok(rid, {
            "protocolVersion": PROTOCOL_VERSION,
            "serverInfo":      SERVER_INFO,
            "capabilities": {
                "tools":     {"listChanged": False},
                "resources": {"listChanged": False, "subscribe": False},
                "prompts":   {"listChanged": False},
            },
        })

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None  # notifications — no response

    if method == "ping":
        return _ok(rid, {})

    # ── Tools ────────────────────────────────────────────────────────────────
    if method == "tools/list":
        return _ok(rid, {
            "tools": [
                {"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]}
                for t in TOOLS.values()
            ]
        })

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        tool      = TOOLS.get(tool_name)
        if not tool:
            return _err(rid, -32601, f"Tool not found: {tool_name}")
        try:
            result   = tool["handler"](**arguments)
            is_error = isinstance(result, dict) and "error" in result
            return _ok(rid, {
                "content": [{"type": "text", "text": json.dumps(result, default=str, indent=2)}],
                "isError": is_error,
            })
        except Exception as e:
            return _ok(rid, {
                "content": [{"type": "text", "text": f"Tool execution error: {e}"}],
                "isError": True,
            })

    # ── Resources ────────────────────────────────────────────────────────────
    if method == "resources/list":
        return _ok(rid, {
            "resources": [
                {"uri": r["uri"], "name": r["name"], "description": r["description"], "mimeType": r["mimeType"]}
                for r in RESOURCES.values()
            ]
        })

    if method == "resources/read":
        uri      = params.get("uri")
        resource = RESOURCES.get(uri)
        if not resource:
            return _err(rid, -32602, f"Resource not found: {uri}")
        try:
            data = resource["handler"]()
            return _ok(rid, {
                "contents": [{
                    "uri":      uri,
                    "mimeType": resource["mimeType"],
                    "text":     json.dumps(data, default=str, indent=2),
                }]
            })
        except Exception as e:
            return _err(rid, -32603, str(e))

    # ── Prompts ───────────────────────────────────────────────────────────────
    if method == "prompts/list":
        return _ok(rid, {"prompts": []})

    # ── Unknown ───────────────────────────────────────────────────────────────
    return _err(rid, -32601, f"Method not found: {method}")


# ══════════════════════════════════════════════════════════════════════════════
# FastAPI ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    """Health check — confirms server is running and lists registered tools."""
    return {
        "status":    "ok",
        "server":    "Gmail Organizer MCP",
        "transport": "SSE",
        "protocol":  PROTOCOL_VERSION,
        "tools":     len(TOOLS),
        "resources": len(RESOURCES),
        "tool_names": list(TOOLS.keys()),
        "sse_endpoint": "/sse",
        "message_endpoint": "/messages?session_id=<session_id>",
    }


@app.get("/sse")
async def sse_endpoint(request: Request):
    """
    MCP SSE transport endpoint (GET).

    Client connects here and receives a persistent event stream.
    The first event is 'endpoint' which tells the client where to POST messages.
    Subsequent events are JSON-RPC responses to tool calls.
    """
    session_id          = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _sessions[session_id] = queue

    messages_url = f"/messages?session_id={session_id}"

    async def event_generator():
        # Immediately send the endpoint event
        yield f"event: endpoint\ndata: {messages_url}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    payload = json.dumps(data, default=str)
                    yield f"event: message\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"  # keep connection alive
        finally:
            _sessions.pop(session_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "Connection":                  "keep-alive",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.post("/messages")
async def messages_endpoint(request: Request, session_id: str):
    """
    MCP JSON-RPC message inbox (POST).

    Client POSTs JSON-RPC 2.0 requests here.
    Responses are pushed back via the SSE stream (not in this HTTP response).
    Returns HTTP 202 Accepted immediately.
    """
    queue = _sessions.get(session_id)
    if queue is None:
        return Response(
            content=json.dumps({"error": "Session not found. Connect to /sse first."}),
            status_code=404,
            media_type="application/json",
        )

    try:
        body = await request.json()
    except Exception:
        return Response(
            content=json.dumps({"error": "Invalid JSON body."}),
            status_code=400,
            media_type="application/json",
        )

    # Handle both single message and batch array
    messages = body if isinstance(body, list) else [body]
    for msg in messages:
        resp = _handle_rpc(msg)
        if resp is not None:
            await queue.put(resp)

    return Response(status_code=202)


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8001"))
    print(f"\n{'='*62}")
    print(f"  Gmail Organizer MCP Server  (native SSE, no mcp package)")
    print(f"  SSE endpoint  : http://{host}:{port}/sse")
    print(f"  Health check  : http://{host}:{port}/health")
    print(f"  Tools         : {len(TOOLS)}  |  Resources: {len(RESOURCES)}")
    print(f"{'='*62}\n")
    uvicorn.run("mcp_server.server:app", host=host, port=port, reload=False)
