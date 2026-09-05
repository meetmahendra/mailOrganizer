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
Generic Project Management Integration Service.

The email organiser pipeline ONLY calls this service — it never calls
Jira or any other PM tool APIs directly.

This service:
  1. Queues PM task requests in the DB (PMActionQueue table).
  2. Loads the configured adapter on demand.
  3. Executes approved tasks via the adapter.

PM actions require explicit user approval before execution.
The Daily Audit Digest surfaces pending tasks for approval.
"""
import os
import sys
import datetime
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_APP_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PM_CFG     = os.path.normpath(
    os.path.join(_APP_DIR, '..', 'config', 'integrations', 'pm_adapter.yaml')
)


def _load_pm_config() -> dict:
    if yaml is None or not os.path.exists(_PM_CFG):
        return {'enabled': False}
    with open(_PM_CFG, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def is_pm_enabled() -> bool:
    return _load_pm_config().get('enabled', False)


def _get_adapter():
    """
    Dynamically load the configured PM adapter.
    Returns an adapter instance or None if PM is disabled / misconfigured.
    """
    cfg = _load_pm_config()
    if not cfg.get('enabled', False):
        return None

    adapter_name = cfg.get('active_adapter', 'jira')

    try:
        if adapter_name == 'jira':
            from services.pm_adapters.jira_adapter import JiraAdapter
            return JiraAdapter()
        else:
            print(f"[pm_service] Unknown adapter: {adapter_name}")
            return None
    except Exception as e:
        print(f"[pm_service] Failed to load adapter '{adapter_name}': {e}")
        return None


def queue_pm_task(
    db,
    gmail_id:      str,
    subject:       str,
    sender:        str,
    summary:       str,
    description:   str = "",
    priority:      str = "Medium",
    project_key:   Optional[str] = None,
    assignee_email: Optional[str] = None,
) -> dict:
    """
    Queue a PM task for user approval.
    Persists the task to the PMActionQueue table in SQLite.
    Returns the queued task dict.
    """
    try:
        from models import PMActionQueue
        task = PMActionQueue(
            gmail_id       = gmail_id,
            email_subject  = subject,
            email_sender   = sender,
            summary        = summary,
            description    = description,
            priority       = priority,
            project_key    = project_key,
            assignee_email = assignee_email,
            status         = 'pending',
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return {'queued': True, 'task_id': task.id, 'summary': summary}
    except Exception as e:
        print(f"[pm_service] queue_pm_task error: {e}")
        return {'queued': False, 'error': str(e)}


def execute_approved_task(db, task_id: int) -> dict:
    """
    Execute a previously approved PM task via the active adapter.
    Updates the task status in the DB.
    """
    from models import PMActionQueue
    from services.pm_adapters.base_adapter import PMTask

    task = db.query(PMActionQueue).filter(PMActionQueue.id == task_id).first()
    if not task:
        return {'error': f'Task {task_id} not found'}
    if task.status != 'approved':
        return {'error': f'Task {task_id} is not approved (status: {task.status})'}

    adapter = _get_adapter()
    if not adapter:
        task.status = 'failed'
        task.result_json = {'error': 'PM adapter not configured or disabled'}
        db.commit()
        return {'error': 'PM adapter not configured'}

    pm_task = PMTask(
        summary        = task.summary,
        description    = task.description or '',
        priority       = task.priority or 'Medium',
        assignee_email = task.assignee_email,
        project_key    = task.project_key,
        email_gmail_id = task.gmail_id,
        email_subject  = task.email_subject,
        email_sender   = task.email_sender,
    )

    try:
        result = adapter.pm_create_task(pm_task)
        task.status      = 'executed'
        task.result_json = result
        task.executed_at = datetime.datetime.utcnow()
        db.commit()
        return {'executed': True, 'result': result}
    except Exception as e:
        task.status      = 'failed'
        task.result_json = {'error': str(e)}
        db.commit()
        return {'error': str(e)}


def approve_task(db, task_id: int) -> dict:
    """Mark a queued task as approved (ready for execution)."""
    from models import PMActionQueue
    task = db.query(PMActionQueue).filter(PMActionQueue.id == task_id).first()
    if not task:
        return {'error': f'Task {task_id} not found'}
    task.status = 'approved'
    db.commit()
    return {'approved': True, 'task_id': task_id}


def reject_task(db, task_id: int) -> dict:
    """Mark a queued task as rejected."""
    from models import PMActionQueue
    task = db.query(PMActionQueue).filter(PMActionQueue.id == task_id).first()
    if not task:
        return {'error': f'Task {task_id} not found'}
    task.status = 'rejected'
    db.commit()
    return {'rejected': True, 'task_id': task_id}