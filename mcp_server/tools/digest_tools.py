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
Digest MCP Tools.

Tools registered:
  get_digest               — daily audit digest for a time window
  rescue_email             — move a muted/archived email back to Inbox
  trash_emails             — move selected emails to Trash (confirm required)
  bulk_trash_promotions    — bulk-delete all Promotions emails in a period
"""
import json
import datetime
from typing import List


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


def register_digest_tools(mcp):
    """Register digest/review tools onto the FastMCP instance."""

    @mcp.tool()
    def get_digest(hours: int = 24) -> str:
        """
        Get the daily audit digest: all processed emails and pending PM tasks
        from the past N hours. Use this to review what the pipeline did and
        catch any misclassified emails.

        Args:
            hours: Time window in hours (default 24 = last 24 hours).

        Returns:
            JSON with summary counts, archived emails, promotions, needs-review
            emails, system alerts, and pending PM tasks.
        """
        db = _get_db()
        try:
            from services.digest_service import get_digest as _get_digest
            result = _get_digest(db, hours=hours, user_id=1)
            return json.dumps(result, default=str)
        finally:
            db.close()

    @mcp.tool()
    def rescue_email(gmail_id: str) -> str:
        """
        Rescue a muted or archived email back to the Gmail Inbox.

        Use this when the pipeline incorrectly archived an email you need.
        Restores the INBOX label on the message.

        Args:
            gmail_id: The Gmail message ID (from get_digest or list_emails).

        Returns:
            JSON confirming rescue status.
        """
        db = _get_db()
        try:
            creds = _get_creds(db)
            from googleapiclient.discovery import build
            service = build("gmail", "v1", credentials=creds)
            service.users().messages().modify(
                userId="me",
                id=gmail_id,
                body={"addLabelIds": ["INBOX"]},
            ).execute()
            return json.dumps({"rescued": True, "gmail_id": gmail_id})
        except ValueError as e:
            return json.dumps({"error": str(e)})
        except Exception as e:
            return json.dumps({"error": f"Gmail API error: {e}"})
        finally:
            db.close()

    @mcp.tool()
    def trash_emails(
        gmail_ids: List[str],
        confirm:   bool = False,
        dry_run:   bool = True,
    ) -> str:
        """
        Move selected emails to Trash.

        SAFETY: Set confirm=True to proceed. dry_run defaults to True — when
        dry_run=True, this tool returns a preview of what would be trashed
        without actually deleting anything.

        Args:
            gmail_ids: List of Gmail message IDs to trash.
            confirm:   Must be True to actually execute deletion.
            dry_run:   True = preview only (no real deletion). False = real deletion.

        Returns:
            JSON with preview (if dry_run or !confirm) or results of deletion.
        """
        if dry_run:
            return json.dumps({
                "dry_run":  True,
                "message":  "DRY RUN: No emails were trashed. Pass dry_run=False and confirm=True to delete.",
                "would_trash": gmail_ids,
                "count":    len(gmail_ids),
            })

        if not confirm:
            return json.dumps({
                "trashed": False,
                "message": "Set confirm=True (and dry_run=False) to proceed with deletion.",
                "count":   len(gmail_ids),
            })

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
            return json.dumps({"trashed": True, "results": results}, default=str)
        except ValueError as e:
            return json.dumps({"error": str(e)})
        finally:
            db.close()

    @mcp.tool()
    def bulk_trash_promotions(
        hours:   int  = 24,
        confirm: bool = False,
        dry_run: bool = True,
    ) -> str:
        """
        Bulk-delete all Promotions/Marketing emails processed in the last N hours.

        SAFETY: dry_run defaults to True (preview only). Set dry_run=False and
        confirm=True to execute real deletion. Always call first without confirm
        to preview the list of emails that would be deleted.

        Args:
            hours:   Time window in hours (default 24).
            confirm: Must be True to execute deletion.
            dry_run: True = preview only. False = real Gmail deletion.

        Returns:
            JSON with preview list or deletion results.
        """
        db = _get_db()
        try:
            from models import EmailProcessingLog
            since = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
            logs = db.query(EmailProcessingLog).filter(
                EmailProcessingLog.category == "Promotions/Marketing",
                EmailProcessingLog.processed_at >= since,
            ).all()
            preview = [{"gmail_id": l.gmail_id, "subject": l.subject} for l in logs]

            if dry_run:
                return json.dumps({
                    "dry_run":         True,
                    "message":         f"DRY RUN: {len(logs)} promotions emails would be trashed. Pass dry_run=False and confirm=True to execute.",
                    "emails":          preview,
                    "count":           len(preview),
                })

            if not confirm:
                return json.dumps({
                    "confirm_required": True,
                    "count":            len(logs),
                    "message":          f"Add confirm=True and dry_run=False to delete {len(logs)} promotions emails.",
                    "emails":           preview,
                })

            creds = _get_creds(db)
            from services.gmail_service import move_to_trash
            results = []
            for log in logs:
                try:
                    move_to_trash(creds, log.gmail_id)
                    results.append({"gmail_id": log.gmail_id, "subject": log.subject, "status": "trashed"})
                except Exception as e:
                    results.append({"gmail_id": log.gmail_id, "subject": log.subject, "status": f"error: {e}"})

            return json.dumps({"bulk_trashed": True, "count": len(results), "results": results}, default=str)
        except ValueError as e:
            return json.dumps({"error": str(e)})
        finally:
            db.close()
