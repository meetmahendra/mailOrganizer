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
Gmail API service — V1.

Covers:
  • Read: fetch_unread_emails, execute_gmail_search
  • Mutations (guarded externally by dry_run flag):
      apply_label, remove_inbox_label, star_thread,
      move_to_trash, mark_as_read, create_draft_reply
  • Helper: ensure_label_exists (idempotent label creation)
"""
import base64
from email.message import EmailMessage
from typing import List

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build(creds: Credentials):
    return build('gmail', 'v1', credentials=creds)


def _extract_body(payload: dict) -> str:
    """Recursively pull plain-text body from a Gmail message payload."""
    text = ""
    if 'parts' in payload:
        for part in payload['parts']:
            if part.get('mimeType') == 'text/plain':
                data = part.get('body', {}).get('data')
                if data:
                    text += base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
            else:
                text += _extract_body(part)
    else:
        data = payload.get('body', {}).get('data')
        if data:
            text += base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
    return text


# ── Read operations ───────────────────────────────────────────────────────────

def fetch_unread_emails(creds: Credentials, max_results: int = 20) -> List[dict]:
    """Fetch unread INBOX emails and return normalised dicts."""
    try:
        service = _build(creds)
        result = service.users().messages().list(
            userId='me',
            labelIds=['INBOX', 'UNREAD'],
            maxResults=max_results,
        ).execute()

        messages = result.get('messages', [])
        emails = []
        for msg in messages:
            raw = service.users().messages().get(
                userId='me', id=msg['id'], format='full'
            ).execute()
            # Case-insensitive header dictionary
            lower_headers = {h['name'].lower(): h['value'] for h in raw['payload'].get('headers', [])}

            # Helper to extract clean email addresses from comma-separated recipient header
            def _parse_addrs(val: str) -> list[str]:
                if not val:
                    return []
                import re
                found = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', val)
                return [a.lower() for a in found] if found else [val.strip().lower()]

            to_recipients = _parse_addrs(lower_headers.get('to', ''))
            cc_recipients = _parse_addrs(lower_headers.get('cc', ''))

            auto_reply_headers = {
                'auto_submitted': lower_headers.get('auto-submitted', ''),
                'x_auto_response_suppress': lower_headers.get('x-auto-response-suppress', ''),
                'precedence': lower_headers.get('precedence', ''),
                'x_autoreply': lower_headers.get('x-autoreply', ''),
            }

            emails.append({
                'gmail_id':          raw['id'],
                'thread_id':         raw.get('threadId', raw['id']),
                'subject':           lower_headers.get('subject', '(no subject)'),
                'sender':            lower_headers.get('from', ''),
                'snippet':           raw.get('snippet', ''),
                'body':              _extract_body(raw['payload']),
                'message_id_header': lower_headers.get('message-id', ''),
                'to_recipients':     to_recipients,
                'cc_recipients':     cc_recipients,
                'auto_reply_headers': auto_reply_headers,
            })
        return emails
    except HttpError as e:
        print(f"[gmail] fetch_unread_emails error: {e}")
        return []


def execute_gmail_search(creds: Credentials, query: str, max_results: int = 20) -> List[dict]:
    """Execute a raw Gmail search query and return matching email summaries."""
    try:
        service = _build(creds)
        result = service.users().messages().list(
            userId='me', q=query, maxResults=max_results
        ).execute()
        messages = result.get('messages', [])
        emails = []
        for msg in messages:
            raw = service.users().messages().get(
                userId='me', id=msg['id'], format='metadata',
                metadataHeaders=['Subject', 'From', 'Date'],
            ).execute()
            headers = {h['name']: h['value'] for h in raw['payload']['headers']}
            emails.append({
                'gmail_id': raw['id'],
                'subject':  headers.get('Subject', '(no subject)'),
                'sender':   headers.get('From', ''),
                'date':     headers.get('Date', ''),
                'snippet':  raw.get('snippet', ''),
            })
        return emails
    except HttpError as e:
        print(f"[gmail] execute_gmail_search error: {e}")
        return []


# ── Label helpers ─────────────────────────────────────────────────────────────

def ensure_label_exists(service, label_name: str) -> str:
    """
    Return the label ID for label_name, creating the label if it doesn't exist.
    This is idempotent — safe to call repeatedly.
    """
    labels = service.users().labels().list(userId='me').execute().get('labels', [])
    for label in labels:
        if label['name'].lower() == label_name.lower():
            return label['id']
    # Not found — create it
    new_label = service.users().labels().create(
        userId='me',
        body={
            'name':                   label_name,
            'messageListVisibility':  'show',
            'labelListVisibility':    'labelShow',
        },
    ).execute()
    return new_label['id']


# ── Mutation operations ───────────────────────────────────────────────────────
# All mutations below are ONLY called by execute_actions when dry_run=False.

def apply_label(creds: Credentials, gmail_id: str, label_name: str) -> None:
    """Apply a named label to a message (creates label if needed)."""
    try:
        service  = _build(creds)
        label_id = ensure_label_exists(service, label_name)
        service.users().messages().modify(
            userId='me', id=gmail_id,
            body={'addLabelIds': [label_id]},
        ).execute()
    except HttpError as e:
        print(f"[gmail] apply_label({label_name}) error: {e}")
        raise


def remove_inbox_label(creds: Credentials, gmail_id: str) -> None:
    """Archive a message by removing the INBOX label."""
    try:
        service = _build(creds)
        service.users().messages().modify(
            userId='me', id=gmail_id,
            body={'removeLabelIds': ['INBOX']},
        ).execute()
    except HttpError as e:
        print(f"[gmail] remove_inbox_label error: {e}")
        raise


def star_thread(creds: Credentials, thread_id: str) -> None:
    """Star an entire thread."""
    try:
        service = _build(creds)
        service.users().threads().modify(
            userId='me', id=thread_id,
            body={'addLabelIds': ['STARRED']},
        ).execute()
    except HttpError as e:
        print(f"[gmail] star_thread error: {e}")
        raise


def move_to_trash(creds: Credentials, gmail_id: str) -> None:
    """Move a message to Gmail's Trash (30-day recovery window remains intact)."""
    try:
        service = _build(creds)
        service.users().messages().trash(userId='me', id=gmail_id).execute()
    except HttpError as e:
        print(f"[gmail] move_to_trash error: {e}")
        raise


def mark_as_read(creds: Credentials, gmail_id: str) -> None:
    """Remove the UNREAD label from a message."""
    try:
        service = _build(creds)
        service.users().messages().modify(
            userId='me', id=gmail_id,
            body={'removeLabelIds': ['UNREAD']},
        ).execute()
    except HttpError as e:
        print(f"[gmail] mark_as_read error: {e}")
        raise


def create_draft_reply(
    creds:              Credentials,
    gmail_id:           str,
    thread_id:          str,
    original_subject:   str,
    sender:             str,
    reply_text:         str,
    message_id_header:  str = "",
) -> str:
    """
    Create a Gmail Draft reply on the specified thread.
    Returns the new draft ID.
    No email is sent — the draft sits in the user's Drafts folder.
    """
    try:
        service = _build(creds)

        msg = EmailMessage()
        msg.set_content(reply_text)
        msg['To']      = sender
        msg['From']    = 'me'
        subject        = original_subject
        if not subject.lower().startswith('re:'):
            subject = f'Re: {subject}'
        msg['Subject'] = subject

        if message_id_header:
            msg['In-Reply-To'] = message_id_header
            msg['References']  = message_id_header

        encoded = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        draft   = service.users().drafts().create(
            userId='me',
            body={'message': {'raw': encoded, 'threadId': thread_id}},
        ).execute()
        return draft['id']
    except HttpError as e:
        print(f"[gmail] create_draft_reply error: {e}")
        raise
