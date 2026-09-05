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
Email Organizer — V1 FastAPI Application Entry Point.

V1 changes:
  • DRY_RUN mode loaded from .env at startup (shown in banner).
  • New /pipeline router registered.
  • Database tables auto-created/extended on startup.
"""
import os
from dotenv import load_dotenv

# Load .env BEFORE any module that reads env vars (pipeline, services, etc.)
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

from fastapi import FastAPI
from database import engine, Base
from routes import auth, emails, search
from routes import pipeline as pipeline_route
from routes import digest as digest_route

# Create / migrate all tables
Base.metadata.create_all(bind=engine)

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Email Organizer API",
    version="1.0.0",
    description=(
        "Intelligent inbox automation pipeline built with LangGraph + LangChain. "
        "Set DRY_RUN=false in .env to enable live Gmail mutations."
    ),
)

app.include_router(auth.router,           prefix="/auth",     tags=["Auth"])
app.include_router(emails.router,         prefix="/emails",   tags=["Emails"])
app.include_router(search.router,         prefix="/search",   tags=["Search"])
app.include_router(pipeline_route.router, prefix="/pipeline", tags=["Pipeline"])
app.include_router(digest_route.router,   prefix="/digest",   tags=["Digest"])



@app.get("/")
def read_root():
    dry_run = os.getenv("DRY_RUN", "true").strip().lower() != "false"
    return {
        "message": "Email Organizer V1 - LangGraph Pipeline",
        "mode":    "DRY_RUN [OK] (safe)" if dry_run else "[!] LIVE MODE - Gmail mutations ACTIVE",
        "docs":    "http://localhost:8000/docs",
        "pipeline_status": "http://localhost:8000/pipeline/status",
    }


# ── Startup banner ────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_banner():
    dry_run = os.getenv("DRY_RUN", "true").strip().lower() != "false"
    mode_str = "DRY_RUN (all actions -> audit_log.csv, Gmail untouched)" if dry_run \
               else "[!] LIVE MODE (real Gmail mutations ENABLED)"
    print("\n" + "=" * 60)
    print("  Email Organizer V1 - LangGraph Pipeline")
    print(f"  Mode: {mode_str}")
    print("  Docs: http://localhost:8000/docs")
    print("=" * 60 + "\n")
