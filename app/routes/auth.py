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

import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from sqlalchemy.orm import Session
from database import get_db
from models import User
from services.auth_service import get_auth_url, exchange_code

router = APIRouter()


@router.get("/login")
def login():
    """Generate and return the Google OAuth2 consent URL."""
    url, state = get_auth_url()
    return RedirectResponse(url)


@router.get("/oauth2callback")
def oauth2callback(code: str, state: str, db: Session = Depends(get_db)):
    """
    Google redirects here after user grants permission.
    Exchanges the auth code for tokens and stores them in the database.
    """
    try:
        creds_dict = exchange_code(code, state)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {e}")

    # Identify user by their email from the token info
    # (We use the 'id_token' hint or a fallback email)
    email = creds_dict.get("id_token", {})
    if isinstance(email, dict):
        email = email.get("email", "unknown@user.com")
    else:
        email = "default@user.com"

    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, credentials_json=json.dumps(creds_dict))
        db.add(user)
    else:
        user.credentials_json = json.dumps(creds_dict)

    db.commit()
    db.refresh(user)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Authentication Successful</title></head>
    <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px; background-color: #f9f9f9;">
        <div style="max-width: 500px; margin: auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <h2 style="color: #2e7d32; margin-top: 0;">Authentication Successful!</h2>
            <p>Connected to Google account: <strong>{user.email}</strong></p>
            <p style="color: #666; font-size: 14px;">You can now close this browser tab and return to Email Organizer.</p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.get("/users")
def list_users(db: Session = Depends(get_db)):
    """List all authenticated users."""
    users = db.query(User).all()
    return [{"id": u.id, "email": u.email} for u in users]
