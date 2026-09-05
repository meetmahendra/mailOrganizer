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

import os
import json
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar.readonly',
]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDENTIALS_FILE = os.path.join(BASE_DIR, '..', 'credentials.json')
REDIRECT_URI = "http://localhost:8000/auth/oauth2callback"

# In-memory store: maps OAuth `state` → Flow instance
# This bridges the login redirect and the callback in separate HTTP requests.
_pending_flows: dict[str, Flow] = {}


def get_credentials_path() -> str:
    """Finds credentials.json across bundle and source directories."""
    candidates = [
        CREDENTIALS_FILE,
        os.path.join(BASE_DIR, 'credentials.json'),
        os.path.join(os.getcwd(), 'credentials.json'),
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    return CREDENTIALS_FILE


def get_flow() -> Flow:
    return Flow.from_client_secrets_file(
        get_credentials_path(),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )


def get_auth_url() -> tuple[str, str]:
    """
    Create a new Flow, generate the authorization URL (with PKCE),
    store the Flow keyed by its state, and return (url, state).
    """
    flow = get_flow()
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
    )
    # Persist the flow so the callback can reuse it (with its code_verifier)
    _pending_flows[state] = flow
    return auth_url, state


def exchange_code(code: str, state: str) -> dict:
    """
    Retrieve the stored Flow for the given state, then exchange the auth
    code for tokens. Returns credentials as a JSON-serialisable dict.
    """
    flow = _pending_flows.pop(state, None)
    if flow is None:
        raise ValueError(
            "No pending OAuth flow found for this state. "
            "Please restart the login flow via /auth/login."
        )
    flow.fetch_token(code=code)
    creds = flow.credentials
    creds_dict = json.loads(creds.to_json())

    # Write token.json to mail directory for compatibility
    try:
        token_path = os.path.join(os.path.dirname(BASE_DIR), "token.json")
        with open(token_path, "w", encoding="utf-8") as tf:
            tf.write(creds.to_json())
    except Exception:
        pass

    return creds_dict


def credentials_from_json(creds_json: str) -> Credentials:
    """Rebuild a Credentials object from a stored JSON string, refreshing if expired."""
    info = json.loads(creds_json)
    creds = Credentials(
        token=info.get('token'),
        refresh_token=info.get('refresh_token'),
        token_uri=info.get('token_uri'),
        client_id=info.get('client_id'),
        client_secret=info.get('client_secret'),
        scopes=info.get('scopes'),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds
