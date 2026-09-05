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
SQLAlchemy models — V2 schema.

Upgrade notes (from V1):
  • EmailProcessingLog gains new nullable columns:
      confidence_score, reasoning, is_reply_necessary, reply_necessity_reason,
      is_no_reply, is_vip, user_id
  • New table: PMActionQueue — one row per PM task queued by the pipeline.
    Tasks await user approval before the adapter executes them.

Migration: Delete emails.db and let create_all() rebuild it,
           OR run: python -m scripts.migrate_db
"""
from sqlalchemy import Boolean, Column, Integer, String, Text, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship
import datetime
from database import Base


class User(Base):
    __tablename__ = "users"

    id               = Column(Integer, primary_key=True, index=True)
    email            = Column(String, unique=True, index=True)
    credentials_json = Column(Text, nullable=True)

    emails = relationship("Email", back_populates="user", cascade="all, delete-orphan")


class Email(Base):
    __tablename__ = "emails"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=True)
    gmail_id    = Column(String, unique=True, index=True)
    thread_id   = Column(String, index=True, nullable=True)
    subject     = Column(String)
    sender      = Column(String)
    snippet     = Column(Text)
    body        = Column(Text)
    received_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="emails")
    tags = relationship("EmailTag", back_populates="email", uselist=False, cascade="all, delete-orphan")


class EmailTag(Base):
    """
    Stores LLM classification results for a single email.

    Legacy V0 fields (kept for backward compatibility):
        primary_intent, context_tags, urgency_rating, suggested_action

    V1 fields:
        category        — one of the canonical pipeline categories
        urgency_score   — integer 1-10
        suggested_reply — full draft reply body text

    V2 fields:
        confidence_score      — LLM self-reported confidence 1-100
        is_reply_necessary    — semantic reply necessity decision
        reply_necessity_reason — LLM explanation
    """
    __tablename__ = "email_tags"

    id              = Column(Integer, primary_key=True, index=True)
    email_id        = Column(Integer, ForeignKey("emails.id"))

    # ── Legacy V0 fields ─────────────────────────────────────────────────────
    primary_intent  = Column(String,  nullable=True)
    context_tags    = Column(JSON,    nullable=True)
    urgency_rating  = Column(String,  nullable=True)
    suggested_action = Column(String, nullable=True)

    # ── V1 pipeline fields ───────────────────────────────────────────────────
    category        = Column(String,  nullable=True, index=True)
    urgency_score   = Column(Integer, nullable=True)
    suggested_reply = Column(Text,    nullable=True)

    # ── V2 pipeline fields ───────────────────────────────────────────────────
    confidence_score       = Column(Integer, nullable=True)
    is_reply_necessary     = Column(Boolean, nullable=True)
    reply_necessity_reason = Column(Text,    nullable=True)

    email = relationship("Email", back_populates="tags")


class EmailProcessingLog(Base):
    """
    One row per email processed by the pipeline.
    Written by the log_result node regardless of dry_run mode.
    """
    __tablename__ = "email_processing_log"

    id               = Column(Integer,  primary_key=True, index=True)
    gmail_id         = Column(String,   index=True)
    subject          = Column(String,   nullable=True)
    sender           = Column(String,   nullable=True)
    category         = Column(String,   nullable=True)
    urgency_score    = Column(Integer,  nullable=True)
    suggested_reply  = Column(Text,     nullable=True)
    actions_taken    = Column(JSON,     nullable=True)
    dry_run          = Column(Boolean,  default=True)
    pipeline_version = Column(String,   default="v2")
    processed_at     = Column(DateTime, default=datetime.datetime.utcnow)

    # ── V2 additions ─────────────────────────────────────────────────────────
    user_id                = Column(Integer, nullable=True)
    confidence_score       = Column(Integer, nullable=True)
    reasoning              = Column(Text,    nullable=True)
    is_reply_necessary     = Column(Boolean, nullable=True)
    reply_necessity_reason = Column(Text,    nullable=True)
    is_no_reply            = Column(Boolean, nullable=True)
    is_vip                 = Column(Boolean, nullable=True)


class PMActionQueue(Base):
    """
    Queue of project management tasks awaiting user approval.

    Created by the pipeline when it identifies that a PM action is needed.
    Executed by pm_service.execute_approved_task() after user approval.
    Surfaced in the Daily Audit Digest for review.
    """
    __tablename__ = "pm_action_queue"

    id             = Column(Integer,  primary_key=True, index=True)
    gmail_id       = Column(String,   index=True, nullable=True)
    email_subject  = Column(String,   nullable=True)
    email_sender   = Column(String,   nullable=True)

    # PM task details
    summary        = Column(String,   nullable=False)
    description    = Column(Text,     nullable=True)
    priority       = Column(String,   default="Medium")   # Highest|High|Medium|Low|Lowest
    project_key    = Column(String,   nullable=True)
    assignee_email = Column(String,   nullable=True)

    # Lifecycle
    status         = Column(String,   default="pending", index=True)
    # pending → approved → executed
    # pending → rejected

    result_json    = Column(JSON,     nullable=True)  # Adapter response after execution
    created_at     = Column(DateTime, default=datetime.datetime.utcnow)
    executed_at    = Column(DateTime, nullable=True)
