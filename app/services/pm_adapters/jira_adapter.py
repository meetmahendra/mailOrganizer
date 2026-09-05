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
Jira PM Adapter.

Maps generic PM actions (from BasePMAdapter) to Jira REST API calls.
Configuration loaded from: config/integrations/jira/connection.yaml

This adapter is a SEPARATE deployable component — the email organiser
queues PM tasks and the adapter executes them upon user approval.
"""
import os
import re
from typing import Optional

from services.pm_adapters.base_adapter import BasePMAdapter, PMTask

try:
    import yaml
except ImportError:
    yaml = None

try:
    import requests
    from requests.auth import HTTPBasicAuth
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

_APP_DIR    = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_JIRA_CFG   = os.path.normpath(
    os.path.join(_APP_DIR, '..', 'config', 'integrations', 'jira', 'connection.yaml')
)


def _resolve_env(value: str) -> str:
    """Replace ${ENV_VAR_NAME} placeholders with actual environment variable values."""
    if not isinstance(value, str):
        return value
    pattern = re.compile(r'\$\{(\w+)\}')
    def replacer(match):
        return os.environ.get(match.group(1), match.group(0))
    return pattern.sub(replacer, value)


def _load_jira_config() -> dict:
    if yaml is None or not os.path.exists(_JIRA_CFG):
        return {}
    with open(_JIRA_CFG, 'r', encoding='utf-8') as f:
        raw = yaml.safe_load(f) or {}
    return {k: _resolve_env(v) for k, v in raw.items()}


class JiraAdapter(BasePMAdapter):
    """
    Jira REST API v3 adapter.

    Generic PM Action -> Jira API mapping:
      pm_create_task    -> POST /rest/api/3/issue
      pm_assign         -> PUT  /rest/api/3/issue/{id}/assignee
      pm_update_status  -> POST /rest/api/3/issue/{id}/transitions
      pm_add_comment    -> POST /rest/api/3/issue/{id}/comment
      pm_notify_member  -> POST /rest/api/3/issue/{id}/comment (with @mention)
    """

    def __init__(self):
        cfg = _load_jira_config()
        self.base_url      = cfg.get('base_url', '').rstrip('/')
        self.auth_email    = cfg.get('auth_email', '')
        self.api_token     = cfg.get('api_token', '')
        self.default_project = cfg.get('default_project_key', '')
        self.default_issue_type = cfg.get('default_issue_type', 'Task')
        self.default_priority   = cfg.get('default_priority', 'Medium')

        if _REQUESTS_AVAILABLE and self.auth_email and self.api_token:
            self._auth = HTTPBasicAuth(self.auth_email, self.api_token)
            self._headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            }
        else:
            self._auth = None
            self._headers = {}

    def _post(self, endpoint: str, body: dict) -> dict:
        if not _REQUESTS_AVAILABLE:
            return {'error': 'requests library not installed'}
        url = f"{self.base_url}/rest/api/3/{endpoint.lstrip('/')}"
        try:
            r = requests.post(url, json=body, headers=self._headers, auth=self._auth, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {'error': str(e)}

    def _put(self, endpoint: str, body: dict) -> dict:
        if not _REQUESTS_AVAILABLE:
            return {'error': 'requests library not installed'}
        url = f"{self.base_url}/rest/api/3/{endpoint.lstrip('/')}"
        try:
            r = requests.put(url, json=body, headers=self._headers, auth=self._auth, timeout=15)
            r.raise_for_status()
            return r.json() if r.content else {'status': 'ok'}
        except Exception as e:
            return {'error': str(e)}

    def _get_transitions(self, issue_id: str) -> list:
        if not _REQUESTS_AVAILABLE:
            return []
        url = f"{self.base_url}/rest/api/3/issue/{issue_id}/transitions"
        try:
            r = requests.get(url, headers=self._headers, auth=self._auth, timeout=15)
            r.raise_for_status()
            return r.json().get('transitions', [])
        except Exception:
            return []

    # ---- Generic PM interface implementation --------------------------------

    def pm_find_by_thread(self, thread_id: str) -> Optional[dict]:
        """Search Jira for an existing issue created from the same email thread."""
        if not _REQUESTS_AVAILABLE or not thread_id:
            return None
        clean_tid = re.sub(r'[^a-zA-Z0-9_-]', '', thread_id)
        jql = f'labels = "email-thread-{clean_tid}"'
        try:
            r = self._post('search', {'jql': jql, 'maxResults': 1, 'fields': ['key', 'summary', 'status']})
            issues = r.get('issues', [])
            if issues:
                issue = issues[0]
                return {
                    'task_id': issue.get('key'),
                    'url': f"{self.base_url}/browse/{issue.get('key')}",
                    'summary': issue.get('fields', {}).get('summary'),
                }
        except Exception:
            pass
        return None

    def pm_create_task(self, task: PMTask) -> dict:
        """Create a Jira issue from a generic PMTask with thread-level deduplication."""
        # 1. Deduplication check: see if issue already exists for this thread
        if task.thread_id:
            existing = self.pm_find_by_thread(task.thread_id)
            if existing:
                # Add comment linking to ongoing thread instead of duplicate issue
                self.pm_add_comment(
                    existing['task_id'],
                    f"Additional email update received from thread {task.thread_id}:\n{task.summary}"
                )
                return {
                    'task_id': existing['task_id'],
                    'url': existing['url'],
                    'status': 'linked_existing_issue',
                    'raw': existing,
                }

        project_key = task.project_key or self.default_project
        clean_tid = re.sub(r'[^a-zA-Z0-9_-]', '', task.thread_id or '')
        labels = [f"email-thread-{clean_tid}"] if clean_tid else ["email-organizer"]

        body = {
            'fields': {
                'project':   {'key': project_key},
                'summary':   task.summary,
                'description': {
                    'type':    'doc',
                    'version': 1,
                    'content': [{
                        'type':    'paragraph',
                        'content': [{'type': 'text', 'text': task.description or task.summary}],
                    }],
                },
                'issuetype': {'name': self.default_issue_type},
                'priority':  {'name': task.priority or self.default_priority},
                'labels':    labels,
            }
        }
        result = self._post('issue', body)
        issue_key = result.get('key', '')
        return {
            'task_id': issue_key,
            'url':     f"{self.base_url}/browse/{issue_key}" if issue_key else '',
            'raw':     result,
        }

    def pm_assign(self, task_id: str, assignee_email: str) -> dict:
        """Assign a Jira issue to a user by their account email."""
        result = self._put(f'issue/{task_id}/assignee', {'emailAddress': assignee_email})
        return {'task_id': task_id, 'assignee': assignee_email, 'raw': result}

    def pm_update_status(self, task_id: str, new_status: str) -> dict:
        """Transition a Jira issue to a named status."""
        transitions = self._get_transitions(task_id)
        transition_id = None
        for t in transitions:
            if t.get('name', '').lower() == new_status.lower():
                transition_id = t['id']
                break
        if not transition_id:
            return {'error': f'Transition "{new_status}" not found for {task_id}', 'task_id': task_id}
        result = self._post(f'issue/{task_id}/transitions', {'transition': {'id': transition_id}})
        return {'task_id': task_id, 'status': new_status, 'raw': result}

    def pm_add_comment(self, task_id: str, comment: str) -> dict:
        """Add a plain-text comment to a Jira issue."""
        body = {
            'body': {
                'type':    'doc',
                'version': 1,
                'content': [{
                    'type':    'paragraph',
                    'content': [{'type': 'text', 'text': comment}],
                }],
            }
        }
        result = self._post(f'issue/{task_id}/comment', body)
        return {'task_id': task_id, 'comment_id': result.get('id', ''), 'raw': result}

    def pm_notify_member(self, task_id: str, member_email: str, message: str) -> dict:
        """Notify a member via a comment @mention in Jira."""
        comment = f"@{member_email}: {message}"
        return self.pm_add_comment(task_id, comment)