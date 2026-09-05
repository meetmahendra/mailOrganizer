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
Text normalisation utilities.

Handles:
  - MIME encoded-word decoding (=?UTF-8?B?...?= and =?UTF-8?Q?...?=)
  - Character encoding normalisation (UTF-8, ISO-8859-1)
  - HTML body stripping (text/html payloads)
  - HTML entity decoding (&amp;, &#x26;, etc.)

Applied in Layer 1 pre-checks BEFORE any LLM or business logic.
"""
import re
import html
from email.header import decode_header, make_header
from typing import Optional


def normalise_subject(raw_subject: str) -> str:
    """
    Decode a raw email Subject header that may contain MIME encoded-words.
    Handles: =?UTF-8?B?...?= (base64) and =?UTF-8?Q?...?= (quoted-printable)
    as well as plain UTF-8 / ISO-8859-1 strings.

    Examples:
        '=?UTF-8?B?SGVsbG8gV29ybGQ=?=' -> 'Hello World'
        '=?iso-8859-1?Q?Caf=E9?='      -> 'Cafe'
        'Plain subject'                 -> 'Plain subject'
    """
    if not raw_subject:
        return ''
    try:
        decoded = str(make_header(decode_header(raw_subject)))
        return decoded.strip()
    except Exception:
        # Fallback: attempt UTF-8 decode of raw bytes
        try:
            if isinstance(raw_subject, bytes):
                return raw_subject.decode('utf-8', errors='replace').strip()
            return raw_subject.strip()
        except Exception:
            return raw_subject


def normalise_body(text: str, mime_type: str = 'text/plain') -> str:
    """
    Normalise an email body for safe LLM consumption.

    For text/html:
      1. Strip all HTML tags.
      2. Decode HTML entities.
      3. Collapse excessive whitespace.

    For text/plain:
      1. Decode HTML entities (some plain-text emails include them).
      2. Normalise line endings.
    """
    if not text:
        return ''

    if mime_type == 'text/html':
        # Remove <style> and <script> blocks first
        text = re.sub(r'<(style|script)[^>]*>.*?</\1>', '', text, flags=re.DOTALL | re.IGNORECASE)
        # Strip all HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)
        # Decode HTML entities (&amp; &#x26; etc.)
        text = html.unescape(text)
        # Collapse whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
    else:
        # Plain text: just decode entities and normalise line endings
        text = html.unescape(text)
        text = text.replace('\r\n', '\n').replace('\r', '\n')

    return text.strip()


def safe_decode_bytes(data: bytes, preferred: str = 'utf-8') -> str:
    """
    Decode a bytes object, trying preferred encoding first then falling back
    to ISO-8859-1 and finally replacing undecodeable characters.
    """
    for encoding in (preferred, 'utf-8', 'iso-8859-1'):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode('utf-8', errors='replace')


def detect_no_reply_sender(sender: str, no_reply_patterns: Optional[list] = None) -> bool:
    """
    Return True if the sender address looks like an automated / no-reply address.
    Patterns are matched case-insensitively against the local part of the email.

    Args:
        sender: Full From header value, e.g. 'Alerts <noreply@github.com>'
        no_reply_patterns: List of substrings to match. Falls back to built-in defaults.
    """
    if no_reply_patterns is None:
        no_reply_patterns = [
            'noreply', 'no-reply', 'donotreply', 'do-not-reply',
            'notifications', 'automated', 'mailer-daemon', 'postmaster',
            'bounce', 'alerts', 'support-noreply',
        ]

    # Extract just the email address from 'Display Name <email@domain.com>' format
    match = re.search(r'<([^>]+)>', sender)
    email_addr = match.group(1) if match else sender
    local_part = email_addr.split('@')[0].lower()

    for pattern in no_reply_patterns:
        if pattern.lower() in local_part:
            return True
    return False


def detect_vip_sender(
    sender: str,
    vip_addresses: Optional[list] = None,
    vip_domains: Optional[list] = None,
) -> bool:
    """
    Return True if the sender matches any VIP address or VIP domain.
    Comparison is case-insensitive.
    """
    if not vip_addresses:
        vip_addresses = []
    if not vip_domains:
        vip_domains = []

    match = re.search(r'<([^>]+)>', sender)
    email_addr = (match.group(1) if match else sender).lower().strip()

    # Exact address match
    if email_addr in [v.lower() for v in vip_addresses]:
        return True

    # Domain match
    if '@' in email_addr:
        domain = email_addr.split('@')[1]
        if domain in [d.lower() for d in vip_domains]:
            return True

    return False


def has_critical_keyword(subject: str, keywords: Optional[list] = None) -> bool:
    """
    Return True if the subject contains any critical keyword (case-insensitive).
    """
    if not keywords:
        return False
    subject_lower = subject.lower()
    return any(kw.lower() in subject_lower for kw in keywords)
