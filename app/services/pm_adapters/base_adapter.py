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
Abstract base class for Project Management adapters.

Every PM tool adapter (Jira, GitHub Issues, Trello, etc.) must implement
this interface. The email organiser pipeline only calls these generic methods —
it never calls tool-specific APIs directly.
"""
from abc import ABC, abstractmethod
from typing import Optional


class PMTask:
    """Represents a generic project management task to be created or updated."""

    def __init__(
        self,
        summary: str,
        description: str = "",
        priority: str = "Medium",       # Highest | High | Medium | Low | Lowest
        assignee_email: Optional[str] = None,
        project_key: Optional[str] = None,
        email_gmail_id: Optional[str] = None,
        email_subject: Optional[str] = None,
        email_sender: Optional[str] = None,
        thread_id: Optional[str] = None,
    ):
        self.summary         = summary
        self.description     = description
        self.priority        = priority
        self.assignee_email  = assignee_email
        self.project_key     = project_key
        self.email_gmail_id  = email_gmail_id
        self.email_subject   = email_subject
        self.email_sender    = email_sender
        self.thread_id       = thread_id

    def to_dict(self) -> dict:
        return {
            'summary':        self.summary,
            'description':    self.description,
            'priority':       self.priority,
            'assignee_email': self.assignee_email,
            'project_key':    self.project_key,
            'email_gmail_id': self.email_gmail_id,
            'email_subject':  self.email_subject,
            'email_sender':   self.email_sender,
            'thread_id':      self.thread_id,
        }


class BasePMAdapter(ABC):
    """
    Abstract PM adapter. Implement this class to integrate a new PM tool.
    """

    @abstractmethod
    def pm_create_task(self, task: PMTask) -> dict:
        """
        Create a new task/ticket.
        Returns a dict with at least: {'task_id': str, 'url': str}
        """

    @abstractmethod
    def pm_assign(self, task_id: str, assignee_email: str) -> dict:
        """
        Assign a task to a team member by their email.
        Returns a dict with: {'task_id': str, 'assignee': str}
        """

    @abstractmethod
    def pm_update_status(self, task_id: str, new_status: str) -> dict:
        """
        Transition a task to a new lifecycle status.
        e.g. 'To Do', 'In Progress', 'Blocked', 'Done'
        Returns a dict with: {'task_id': str, 'status': str}
        """

    @abstractmethod
    def pm_add_comment(self, task_id: str, comment: str) -> dict:
        """
        Add a comment to an existing task.
        Returns a dict with: {'task_id': str, 'comment_id': str}
        """

    @abstractmethod
    def pm_notify_member(self, task_id: str, member_email: str, message: str) -> dict:
        """
        Notify a team member about a task (e.g. via @mention or watcher).
        Returns a dict with: {'task_id': str, 'notified': str}
        """