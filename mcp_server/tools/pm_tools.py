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
Project Management MCP Tools.

Tools registered:
  list_pending_pm_tasks  — list PM tasks awaiting user approval
  approve_pm_task        — approve a task (does NOT execute yet)
  reject_pm_task         — reject a pending task
  execute_pm_task        — execute an approved task via the configured adapter
"""
import json


def _get_db():
    from database import SessionLocal
    return SessionLocal()


def register_pm_tools(mcp):
    """Register PM task queue management tools onto the FastMCP instance."""

    @mcp.tool()
    def list_pending_pm_tasks(hours: int = 24) -> str:
        """
        List all pending project management tasks awaiting user approval.

        The pipeline queues PM tasks when it detects that an email requires
        action in Jira or another PM tool. Tasks sit in 'pending' state
        until you approve or reject them here.

        Args:
            hours: Time window in hours — only tasks created in this period
                   are returned (default 24).

        Returns:
            JSON array of pending PM tasks with their details.
        """
        import datetime
        db = _get_db()
        try:
            from models import PMActionQueue
            since = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
            tasks = db.query(PMActionQueue).filter(
                PMActionQueue.status == "pending",
                PMActionQueue.created_at >= since,
            ).order_by(PMActionQueue.created_at.desc()).all()

            return json.dumps([
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
            ], default=str)
        finally:
            db.close()

    @mcp.tool()
    def approve_pm_task(task_id: int) -> str:
        """
        Approve a pending PM task, marking it ready for execution.

        After approving, call execute_pm_task to actually create the ticket
        in Jira (or the configured PM adapter).

        Args:
            task_id: The integer ID of the PM task (from list_pending_pm_tasks).

        Returns:
            JSON confirming approval status.
        """
        db = _get_db()
        try:
            from services import pm_service
            result = pm_service.approve_task(db, task_id)
            return json.dumps(result, default=str)
        finally:
            db.close()

    @mcp.tool()
    def reject_pm_task(task_id: int) -> str:
        """
        Reject a pending PM task.

        The task will be marked as rejected and will not appear in future
        pending task lists.

        Args:
            task_id: The integer ID of the PM task (from list_pending_pm_tasks).

        Returns:
            JSON confirming rejection status.
        """
        db = _get_db()
        try:
            from services import pm_service
            result = pm_service.reject_task(db, task_id)
            return json.dumps(result, default=str)
        finally:
            db.close()

    @mcp.tool()
    def execute_pm_task(task_id: int) -> str:
        """
        Execute a previously approved PM task via the configured adapter (e.g. Jira).

        IMPORTANT: The task must be in 'approved' status first. Call approve_pm_task
        before calling this tool.

        Args:
            task_id: The integer ID of the approved PM task.

        Returns:
            JSON with execution result from the PM adapter (e.g. created Jira ticket URL).
        """
        db = _get_db()
        try:
            from services import pm_service
            result = pm_service.execute_approved_task(db, task_id)
            return json.dumps(result, default=str)
        finally:
            db.close()
