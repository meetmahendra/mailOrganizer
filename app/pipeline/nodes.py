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
LangGraph nodes for the V2 email automation pipeline.

Each function receives the full EmailState and returns ONLY the keys it mutates.
LangGraph merges the returned dict back into the state automatically.

Node execution order (see graph.py):
  pre_check_email
      -> classify_email
      -> plan_gmail_actions
      -> [handle_calendar?]
      -> execute_actions
      -> log_result

V2 changes:
  • pre_check_email: encoding normalisation, no-reply & VIP detection (Layer 1)
  • classify_email: semantic reply necessity, confidence score, 8-15 taxonomy tags,
                    multi-model routing via models.yaml
  • plan_gmail_actions: uses external rules engine (rules_engine.py)
  • execute_actions: safe_archive, create_user_task, queue_pm_task support,
                     day-wise draft labels, VIP enforcement, quota error handling
  • log_result: persists all V2 fields to DB
"""
import os
import sys
import time
import datetime
from dotenv import load_dotenv

load_dotenv()

# Ensure app/ is on the path when this runs standalone (e.g. from poll_worker)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

try:
    import yaml
except ImportError:
    yaml = None

from pipeline.state import EmailState
from pipeline.csv_writer import write_audit_row
from pipeline.safety_rules import run_pre_checks, enforce_vip_constraints
from pipeline.rules_engine import get_actions_for_category
from utils.text_utils import normalise_subject, normalise_body
from services.org_context_service import (
    is_org_vip,
    get_department_labels,
    build_org_context_for_prompt,
)
from services.history_context_service import (
    build_thread_history,
    build_non_chained_topic_history,
    format_history_context_block,
)


# ── Config loaders ────────────────────────────────────────────────────────────

_APP_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_DIR = os.path.normpath(os.path.join(_APP_DIR, '..', 'config'))

_MODELS_CONFIG: dict = {}
_MODELS_LOADED = False


def _load_models_config() -> dict:
    global _MODELS_CONFIG, _MODELS_LOADED
    if _MODELS_LOADED:
        return _MODELS_CONFIG
    path = os.path.join(_CONFIG_DIR, 'models.yaml')
    if yaml and os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            _MODELS_CONFIG = yaml.safe_load(f) or {}
    _MODELS_LOADED = True
    return _MODELS_CONFIG


def _get_action_cfg(action_key: str) -> dict:
    """Return the full config block for a given action key."""
    return _load_models_config().get(action_key, {})


def _build_llm(action_key: str, default_model: str = 'gemini-3.6-flash', default_temp: float = 0.1):
    """
    Build a LangChain chat model for the given pipeline action.

    Reads provider, model, temperature, and api_key_env from models.yaml.

    Supported providers:
      google    — Gemini models via ChatGoogleGenerativeAI (langchain-google-genai)
      openai    — GPT models via ChatOpenAI (langchain-openai)
      anthropic — Claude models via ChatAnthropic (langchain-anthropic)
      mistral   — Mistral models via ChatMistralAI (langchain-mistralai)
      qwen      — Qwen/Tongyi models via ChatTongyi (langchain-community + dashscope)

    Example models.yaml entry:
      draft_reply:
        provider: qwen
        model: qwen-max
        temperature: 0.3
        api_key_env: DASHSCOPE_API_KEY
    """
    cfg         = _get_action_cfg(action_key)
    provider    = cfg.get('provider', 'google').lower()
    override    = os.getenv('PIPELINE_MODEL_OVERRIDE')
    model       = override if override else cfg.get('model', default_model)
    temperature = float(cfg.get('temperature', default_temp))
    api_key_env = cfg.get('api_key_env', None)   # override which env var to read

    # ── Google / Gemini ───────────────────────────────────────────────────────
    if provider == 'google':
        api_key = os.getenv(api_key_env or 'GEMINI_API_KEY')
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            temperature=temperature,
        )

    # ── OpenAI ────────────────────────────────────────────────────────────────
    elif provider == 'openai':
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise ImportError("Install langchain-openai: pip install langchain-openai")
        api_key  = os.getenv(api_key_env or 'OPENAI_API_KEY')
        base_url = cfg.get('base_url', None)
        kwargs   = dict(model=model, api_key=api_key, temperature=temperature)
        if base_url:
            kwargs['base_url'] = base_url
        return ChatOpenAI(**kwargs)

    # ── Anthropic / Claude ────────────────────────────────────────────────────
    elif provider == 'anthropic':
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            raise ImportError("Install langchain-anthropic: pip install langchain-anthropic")
        api_key = os.getenv(api_key_env or 'ANTHROPIC_API_KEY')
        return ChatAnthropic(
            model=model,
            anthropic_api_key=api_key,
            temperature=temperature,
        )

    # ── Mistral ───────────────────────────────────────────────────────────────
    elif provider == 'mistral':
        try:
            from langchain_mistralai import ChatMistralAI
        except ImportError:
            raise ImportError("Install langchain-mistralai: pip install langchain-mistralai")
        api_key = os.getenv(api_key_env or 'MISTRAL_API_KEY')
        return ChatMistralAI(
            model=model,
            mistral_api_key=api_key,
            temperature=temperature,
        )

    # ── Qwen / Tongyi (DashScope) ─────────────────────────────────────────────
    elif provider == 'qwen':
        try:
            from langchain_community.chat_models import ChatTongyi
        except ImportError:
            raise ImportError(
                "Install qwen dependencies: pip install langchain-community dashscope"
            )
        api_key = os.getenv(api_key_env or 'DASHSCOPE_API_KEY')
        # ChatTongyi reads DASHSCOPE_API_KEY from env automatically;
        # set it explicitly in case a custom env var name was specified.
        if api_key:
            os.environ['DASHSCOPE_API_KEY'] = api_key
        return ChatTongyi(
            model=model,
            temperature=temperature,
        )

    # ── Unknown provider ──────────────────────────────────────────────────────
    else:
        raise ValueError(
            f"Unknown provider '{provider}' for action '{action_key}'. "
            f"Supported: google, openai, anthropic, mistral, qwen"
        )


# ── Category constants ────────────────────────────────────────────────────────

VALID_CATEGORIES = [
    "Action Required (High)",
    "Action Required (Med/Low)",
    "Calendar/Scheduling",
    "Informational/Logs",
    "Receipts/Financial",
    "Promotions/Marketing",
    "Spam/Trash",
    "System Alert",
    "Needs Review",
]


# ── Context tag taxonomy ──────────────────────────────────────────────────────

TAG_TAXONOMY = """
Use tags from the following taxonomy first before creating new ones.
Pick the most applicable 8-15 tags across all dimensions:

TOPIC: invoice, meeting, deadline, follow-up, onboarding, announcement, report,
       update, alert, notification, contract, approval, feedback, question, request,
       complaint, incident, security, payment, subscription, renewal, cancellation

DOMAIN: engineering, finance, hr, legal, marketing, sales, operations, customer-support,
        management, product, design, infrastructure, data, compliance

SENDER TYPE: internal, external, automated, vendor, client, bank, government,
             newsletter, recruiter, support-ticket

ACTION TYPE: reply-needed, review-needed, action-required, informational, schedule-meeting,
             archive, delegate, expense-claim, no-action

URGENCY: critical, high-priority, medium-priority, low-priority, time-sensitive, overdue

TIME: q1, q2, q3, q4, this-week, this-month, end-of-quarter, eoy

DOMAIN-SPECIFIC (banking/finance): bank, transaction, credit-card, debit, wire-transfer,
                                   otp, fraud-alert, account-statement, tax
"""


# ── LLM output schema ─────────────────────────────────────────────────────────

class EmailClassification(BaseModel):
    category: str = Field(
        description=(
            "Classify into EXACTLY one of: "
            + ", ".join(f'"{c}"' for c in VALID_CATEGORIES)
        )
    )
    urgency_score: int = Field(
        ge=1, le=10,
        description="Urgency 1 (trivial) to 10 (critical / time-sensitive)"
    )
    confidence_score: int = Field(
        ge=1, le=100,
        description="Your confidence in this classification from 1 (guessing) to 100 (certain)"
    )
    reasoning: str = Field(
        description="One-sentence explanation of why you chose this category"
    )
    suggested_reply: str = Field(
        description=(
            "Professional draft reply. Required ONLY for Action Required and Calendar/Scheduling "
            "categories AND when is_reply_necessary=true. Empty string for all other cases."
        )
    )
    context_tags: list[str] = Field(
        description=(
            "8-15 tags drawn from the taxonomy provided. Include tags for topic, domain, "
            "sender-type, action-type, urgency, and any project or time-period context. "
            "Always include domain-specific tags (e.g. 'bank', 'transaction') when applicable."
        )
    )
    is_reply_necessary: bool = Field(
        description=(
            "SEMANTIC analysis: does this email genuinely require a reply? "
            "Consider the full intent and meaning of the email. "
            "True if: sender is asking a question, making a request, or expects a response. "
            "False if: the email is informational, a receipt, a log, an announcement, a status update, "
            "a newsletter, or the content does not direct any action at the recipient. "
            "Do NOT rely on specific phrases — read the meaning."
        )
    )
    reply_necessity_reason: str = Field(
        description="Brief explanation of your is_reply_necessary decision"
    )


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = f"""You are an expert email triage assistant for a busy professional.

Classify the incoming email into EXACTLY one of these categories:
1. "Action Required (High)"   — Deadlines, VIP issues, urgent requests requiring immediate response.
2. "Action Required (Med/Low)"— Routine tasks, general queries, non-urgent follow-ups.
3. "Calendar/Scheduling"      — Meeting invites, rescheduling, availability checks.
4. "Informational/Logs"       — Project updates, system logs, newsletters, FYI messages.
5. "Receipts/Financial"       — Invoices, transaction confirmations, bills, renewal notices.
6. "Promotions/Marketing"     — Cold outreach, marketing campaigns, promotional offers.
7. "Spam/Trash"               — Obvious junk, spam, or malicious content.
8. "System Alert"             — Automated system notifications: storage alerts, quota warnings,
                                security alerts, CI/CD results, infrastructure alerts.
9. "Needs Review"             — Use ONLY if you are genuinely unsure (confidence < 85).

Rules for suggested_reply:
- Write a polite professional reply ONLY for Action Required and Calendar/Scheduling emails
  AND ONLY when is_reply_necessary=true.
- For Calendar/Scheduling, include a placeholder "[availability will be appended]".
- Leave suggested_reply as empty string for all other cases.

Context Tag Instructions:
{TAG_TAXONOMY}

Reply Necessity Instructions:
- is_reply_necessary must reflect the SEMANTIC meaning of the email, not surface phrases.
- A VIP sender sending a status report does NOT require a reply.
- A no-reply sender address has already been detected separately — still assess content meaning.
- Receipts, automated notifications, newsletters, announcements: almost always false.
- Confidence below 85: classify as "Needs Review" instead.
"""


# ── Node 0: pre_check_email ───────────────────────────────────────────────────

def pre_check_email(state: EmailState) -> dict:
    """
    Node 0 — Layer 1 pre-checks (no LLM involved).

    1. Normalise subject and body encoding.
    2. Detect no-reply sender (suppresses draft creation downstream).
    3. Detect VIP sender (via vip_rules.yaml + organization roster).
    4. Detect critical subject keywords.
    """
    # Normalise encoding
    clean_subject = normalise_subject(state.get("subject", ""))
    clean_body    = normalise_body(state.get("body", ""))

    # Run safety pre-checks (sender first, then subject — matches safety_rules.py signature)
    checks = run_pre_checks(state.get("sender", ""), clean_subject)
    is_vip = checks["is_vip"] or is_org_vip(state.get("sender", ""))

    return {
        "subject":              clean_subject,
        "body":                 clean_body,
        "is_no_reply":          checks["is_no_reply"],
        "is_vip":               is_vip,
        "has_critical_subject": checks["has_critical_subject"],
    }


# ── Node 1: classify_email ────────────────────────────────────────────────────

def classify_email(state: EmailState) -> dict:
    """
    Node 1 — LLM classification. Always runs, including for VIP senders.

    Uses model configured under 'classification' in config/models.yaml.
    Enriched with Organizational Intelligence and Thread/Topic History.
    Falls back gracefully if API key is missing.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[classify_email] WARNING: GEMINI_API_KEY not set. Defaulting to Needs Review.")
        return {
            "category":              "Needs Review",
            "urgency_score":         5,
            "confidence_score":      0,
            "reasoning":             "API key not configured",
            "suggested_reply":       "",
            "context_tags":          ["classification-error"],
            "is_reply_necessary":    False,
            "reply_necessity_reason": "Cannot classify without API key",
        }

    try:
        llm = _build_llm("classification", default_model="gemini-3.5-flash-lite", default_temp=0.1)
        structured_llm = llm.with_structured_output(EmailClassification)

        # Build organizational context
        org_context = build_org_context_for_prompt(
            state.get("sender", ""),
            state.get("subject", ""),
            state.get("body", "")
        )

        # Build conversation & topic history
        thread_id = state.get("thread_id", "")
        creds = state.get("creds", None)
        thread_turns = build_thread_history(creds, thread_id, state.get("gmail_id", "")) if creds and thread_id else []
        topic_memories = build_non_chained_topic_history(state.get("sender", ""), state.get("subject", ""))
        history_context = format_history_context_block(thread_turns, topic_memories)

        human_parts = [
            f"Subject: {state.get('subject', '')}",
            f"From: {state.get('sender', '')}",
        ]
        if org_context:
            human_parts.append(org_context)
        if history_context:
            human_parts.append(history_context)
        human_parts.append(f"Email Body:\n{(state.get('body') or '')[:4000]}")

        prompt = ChatPromptTemplate.from_messages([
            ("system", "{system_text}"),
            ("human", "{human_text}"),
        ])
        chain = prompt | structured_llm

        t0_llm = time.perf_counter()
        human_text_assembled = "\n\n".join(human_parts)
        result: EmailClassification = chain.invoke({
            "system_text": _SYSTEM_PROMPT,
            "human_text": human_text_assembled,
        })
        llm_latency_ms = (time.perf_counter() - t0_llm) * 1000

        llm_comms = list(state.get("llm_communications") or [])
        llm_comms.append({
            "step": "classification",
            "model": os.getenv("MODEL_ROUTER_CLASSIFICATION", "gemini-3.6-flash"),
            "temperature": 0.1,
            "system_prompt": _SYSTEM_PROMPT,
            "human_prompt": human_text_assembled,
            "raw_response": result.model_dump_json() if hasattr(result, "model_dump_json") else str(result),
            "duration_ms": round(llm_latency_ms, 2),
            "status": "success",
        })

        # If confidence is low, override to Needs Review
        confidence = max(1, min(100, result.confidence_score))
        category   = result.category if result.category in VALID_CATEGORIES else "Needs Review"
        if confidence < 85 and category not in ("Spam/Trash", "System Alert"):
            category = "Needs Review"

        return {
            "category":              category,
            "urgency_score":         max(1, min(10, result.urgency_score)),
            "confidence_score":      confidence,
            "reasoning":             result.reasoning or "",
            "suggested_reply":       result.suggested_reply or "",
            "context_tags":          result.context_tags or [],
            "is_reply_necessary":    result.is_reply_necessary,
            "reply_necessity_reason": result.reply_necessity_reason or "",
            "thread_history":        thread_turns,
            "llm_communications":    llm_comms,
        }

    except Exception as e:
        # Quota / rate-limit handling
        err_str = str(e).lower()
        if "quota" in err_str or "resource_exhausted" in err_str or "429" in err_str:
            print(f"[classify_email] QUOTA ERROR: {e}")
            return {
                "category":              "Needs Review",
                "urgency_score":         5,
                "confidence_score":      0,
                "reasoning":             f"Gemini API quota exceeded: {e}",
                "suggested_reply":       "",
                "context_tags":          ["quota-error", "needs-manual-review"],
                "is_reply_necessary":    False,
                "reply_necessity_reason": "Quota error — manual review required",
                "error":                 f"QUOTA_EXCEEDED: {e}",
            }

        print(f"[classify_email] Error: {e}")
        return {
            "category":              "Needs Review",
            "urgency_score":         5,
            "confidence_score":      0,
            "reasoning":             f"Classification error: {e}",
            "suggested_reply":       "",
            "context_tags":          ["classification-error"],
            "is_reply_necessary":    False,
            "reply_necessity_reason": "Error during classification",
        }


# ── Node 2: ownership_gate ────────────────────────────────────────────────────

def ownership_gate(state: EmailState) -> dict:
    """
    Node 2 — Evaluate email ownership through the delegation subsystem.

    Determines the user's responsibility role (PRIMARY_ACTIONEE, OBSERVER_ONLY,
    DELEGATOR, TEAMMATE_HANDLING, NEEDS_INTERNAL_INPUT, OOO_SENDER) and whether
    draft generation should proceed.
    """
    try:
        from delegation.ownership_evaluator import evaluate_ownership

        # Build thread history if available in state or via creds
        thread_history = state.get("thread_history", [])
        if not thread_history and state.get("creds") and state.get("thread_id"):
            try:
                from services.history_context_service import build_thread_history
                thread_history = build_thread_history(state["creds"], state["thread_id"], state.get("gmail_id", ""))
            except Exception:
                thread_history = []

        decision = evaluate_ownership(
            sender=state.get("sender", ""),
            to_recipients=state.get("to_recipients", []),
            cc_recipients=state.get("cc_recipients", []),
            body=state.get("body", ""),
            auto_reply_headers=state.get("auto_reply_headers", {}),
            category=state.get("category", ""),
            context_tags=state.get("context_tags", []),
            thread_history=thread_history,
        )

        result = {
            "responsibility_role": decision.role.value,
            "ownership_reason": decision.reason,
            "delegation_target": None,
        }

        if decision.delegation_target:
            result["delegation_target"] = decision.delegation_target.model_dump()

        # If a holding reply is prescribed (NEEDS_INTERNAL_INPUT), set it as the draft
        if decision.holding_reply:
            result["enriched_draft_reply"] = decision.holding_reply

        return result

    except Exception as e:
        print(f"[ownership_gate] Error: {e}")
        return {
            "responsibility_role": "PRIMARY_ACTIONEE",
            "ownership_reason": f"Ownership evaluation failed: {e}; defaulting to primary",
            "delegation_target": None,
        }


# ── Node 3: enrich_context ───────────────────────────────────────────────────

def enrich_context(state: EmailState) -> dict:
    """
    Node 3 — Query external connectors in parallel for enterprise context enrichment.

    Uses tag-based deterministic routing (zero LLM cost) to select connectors,
    then dispatches queries via ThreadPoolExecutor with 2.0s hard timeouts.
    """
    try:
        from connectors.connector_manager import get_connector_manager

        manager = get_connector_manager()
        context_tags = state.get("context_tags", [])
        connector_ids = manager.resolve_connectors_for_tags(context_tags)

        # Ensure gmail_search is queried whenever an email warrants a reply
        if state.get("is_reply_necessary", False):
            if "gmail_search" in manager.connectors and manager.connectors["gmail_search"].is_available():
                if "gmail_search" not in connector_ids:
                    connector_ids.append("gmail_search")

        if not connector_ids:
            return {"retrieved_facts": "", "pending_mutations": []}

        # Build query from email subject and key body excerpt
        subject = state.get("subject", "")
        body_excerpt = (state.get("body") or "")[:500]
        query = f"{subject} {body_excerpt}".strip()

        facts = manager.query_connectors(
            query=query,
            connector_ids=connector_ids,
            timeout_seconds=2.0,
            creds=state.get("creds"),
            sender=state.get("sender", ""),
            current_msg_id=state.get("gmail_id", ""),
            subject=subject,
        )

        synthesized = manager.synthesize_facts(facts, max_bullets=4, max_words_per_bullet=150)

        conn_comms = list(state.get("connector_communications") or [])
        if hasattr(manager, "get_last_query_telemetry"):
            conn_comms.extend(manager.get_last_query_telemetry())

        return {
            "retrieved_facts": synthesized,
            "pending_mutations": [],
            "connector_communications": conn_comms,
        }

    except Exception as e:
        print(f"[enrich_context] Error: {e}")
        return {"retrieved_facts": "", "pending_mutations": []}


# ── Node 4: generate_enriched_draft ──────────────────────────────────────────

def generate_enriched_draft(state: EmailState) -> dict:
    """
    Node 4 — Single authoritative draft generation path.

    Consolidates all context (persona, retrieved facts, calendar, ownership decision)
    into one fact-grounded, persona-aware reply draft.

    This replaces both:
      - The old suggested_reply from classification (removed)
      - The old _generate_draft_reply fallback in execute_actions (removed)
    """
    # If a holding reply was already set by ownership gate, keep it
    existing = state.get("enriched_draft_reply", "").strip()
    if existing:
        return {"enriched_draft_reply": existing}

    # Only draft if the email warrants a reply
    if not state.get("is_reply_necessary", False):
        return {"enriched_draft_reply": ""}

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"enriched_draft_reply": ""}

    try:
        # Load persona config for voice/tone/rules
        persona_name = "Professional User"
        persona_title = ""
        persona_tone = "professional, concise"
        persona_rules = []
        persona_signature = ""

        try:
            from config.schemas import load_and_validate_user_persona_config
            persona = load_and_validate_user_persona_config()
            persona_name = persona.name
            persona_title = persona.title
            persona_tone = persona.tone
            persona_rules = persona.communication_rules or []
            persona_signature = persona.signature or ""
        except Exception:
            pass

        # Build context blocks
        retrieved_facts = state.get("retrieved_facts", "")
        calendar_context = state.get("calendar_context", "")
        responsibility = state.get("responsibility_role", "PRIMARY_ACTIONEE")
        delegation_target = state.get("delegation_target")
        thread_history = state.get("thread_history", [])

        context_parts = []
        if thread_history:
            thread_lines = ["--- 📜 CONVERSATION THREAD (PRIOR TURNS) ---"]
            for t in thread_history[-5:]:
                s = t.get("sender", "Sender")
                d = f" ({t.get('date', '')})" if t.get("date") else ""
                snip = t.get("snippet", "")
                thread_lines.append(f"• Turn {t.get('turn', '')}{d} from {s}: \"{snip}\"")
            context_parts.append("\n".join(thread_lines))

        if retrieved_facts:
            context_parts.append(retrieved_facts)
        if calendar_context:
            context_parts.append(f"--- CALENDAR AVAILABILITY ---\n{calendar_context}")

        rules_text = ""
        if persona_rules:
            rules_text = "\n".join(f"- {r}" for r in persona_rules)

        delegation_instruction = ""
        if responsibility == "DELEGATOR" and delegation_target:
            target_name = delegation_target.get("name", "the specialist")
            target_email = delegation_target.get("email", "")
            delegation_instruction = (
                f"\nIMPORTANT: This email should be delegated. Loop in {target_name} "
                f"({target_email}) in your reply. Explain that they are the right person "
                f"to handle this and introduce the context briefly."
            )

        system_prompt = f"""You are drafting an email reply as {persona_name}, {persona_title}.

Tone: {persona_tone}
{f"Communication Rules:{chr(10)}{rules_text}" if rules_text else ""}
{delegation_instruction}

CRITICAL INSTRUCTIONS:
- Use the retrieved facts and context below to write a substantive, grounded reply.
- If prior conversation thread turns are provided, maintain continuity and address previous turns directly.
- Reference specific data points (dates, amounts, ticket IDs, policy details) from the context.
- Do NOT use vague stalling phrases like "I will look into this" or "Let me get back to you."
- If calendar context is provided and the email involves scheduling, propose 2 specific time slots.
- Keep the reply concise but complete. A busy executive wrote this.
- Do NOT include a greeting line or signature — those are added automatically.

{chr(10).join(context_parts)}"""

        llm = _build_llm("draft_reply", default_model="gemini-3.6-flash", default_temp=0.3)
        prompt = ChatPromptTemplate.from_messages([
            ("system", "{system_text}"),
            ("human", "Draft a reply to this email:\n\nSubject: {subject}\nFrom: {sender}\n\n{body}"),
        ])
        chain = prompt | llm

        t0_draft = time.perf_counter()
        human_prompt_text = f"Draft a reply to this email:\n\nSubject: {state.get('subject', '')}\nFrom: {state.get('sender', '')}\n\n{(state.get('body') or '')[:3000]}"
        result = chain.invoke({
            "system_text": system_prompt,
            "subject": state.get("subject", ""),
            "sender": state.get("sender", ""),
            "body": (state.get("body") or "")[:3000],
        })
        draft_latency_ms = (time.perf_counter() - t0_draft) * 1000

        if hasattr(result, "content"):
            if isinstance(result.content, list):
                draft = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in result.content
                ).strip()
            else:
                draft = str(result.content).strip()
        else:
            draft = str(result).strip()

        # Append signature
        if persona_signature and persona_signature not in draft:
            draft = f"{draft}\n\n{persona_signature}"

        llm_comms = list(state.get("llm_communications") or [])
        llm_comms.append({
            "step": "draft_generation",
            "model": os.getenv("MODEL_ROUTER_DRAFT_REPLY", "gemini-3.6-flash"),
            "temperature": 0.3,
            "system_prompt": system_prompt,
            "human_prompt": human_prompt_text,
            "raw_response": draft,
            "duration_ms": round(draft_latency_ms, 2),
            "status": "success",
        })

        return {"enriched_draft_reply": draft, "llm_communications": llm_comms}

    except Exception as e:
        print(f"[generate_enriched_draft] Error: {e}")
        # Fall back to the classification's suggested_reply if enriched generation fails
        fallback = state.get("suggested_reply", "").strip()
        return {"enriched_draft_reply": fallback}


# ── Node 5: plan_gmail_actions ────────────────────────────────────────────────

def plan_gmail_actions(state: EmailState) -> dict:
    """
    Node 5 — Load actions from external rules engine, apply VIP constraints,
    enforce OOO/sensitive content safety, and ownership-based draft suppression.
    """
    from pipeline.safety_rules import enforce_ooo_safety, enforce_sensitive_lockdown

    category = state.get("category", "Informational/Logs")

    # Get filtered actions from external rules engine
    actions = get_actions_for_category(category, state)

    # Append department/client labels from organizational context
    dept_labels = get_department_labels(state.get("sender", ""))
    for dlabel in dept_labels:
        if not any(a.get("action") == "apply_label" and a.get("label") == dlabel for a in actions):
            actions.append({"action": "apply_label", "label": dlabel})

    # Apply VIP constraints (ensures @VIP label, removes archive/trash actions)
    vip_result = enforce_vip_constraints({**state, "gmail_actions": actions})
    actions = vip_result.get("gmail_actions", actions)

    # V3 Phase 5: OOO loop prevention — strip draft if sender is auto-responder
    ooo_result = enforce_ooo_safety({**state, "gmail_actions": actions})
    actions = ooo_result.get("gmail_actions", actions)

    # V3 Phase 5: Sensitive content lockdown — block drafts for legal/HR/regulatory
    sensitive_result = enforce_sensitive_lockdown({**state, "gmail_actions": actions})
    actions = sensitive_result.get("gmail_actions", actions)

    # Override: no-reply suppresses draft creation
    if state.get("is_no_reply"):
        actions = [a for a in actions if a.get("action") != "create_draft_reply"]

    # V3 Phase 5: Ownership-based draft suppression
    # If ownership gate decided the user is an observer or teammate is handling,
    # strip any draft creation action as an extra safety layer
    role = state.get("responsibility_role", "")
    if role in ("OBSERVER_ONLY", "TEAMMATE_HANDLING", "OOO_SENDER"):
        actions = [a for a in actions if a.get("action") != "create_draft_reply"]

    return {"gmail_actions": actions}


# ── Node 3: handle_calendar ───────────────────────────────────────────────────

def handle_calendar(state: EmailState) -> dict:
    """Node 3 — Fetch Google Calendar free/busy + upcoming events and build availability summary."""
    try:
        # If calendar context was already provided (e.g. from test fixture), preserve it
        if state.get("calendar_context"):
            return {"calendar_context": state["calendar_context"]}

        creds = state.get("creds")
        if not creds:
            return {"calendar_context": ""}

        from services.calendar_service import check_freebusy, get_upcoming_events

        freebusy = check_freebusy(creds)
        events   = get_upcoming_events(creds, max_results=3)

        busy_slots = freebusy.get("busy_slots", [])
        if busy_slots:
            slot_strs = "; ".join(
                f"{s['start']} -> {s['end']}" for s in busy_slots[:3]
            )
            avail = f"I have existing commitments: {slot_strs}."
        else:
            avail = "I appear to be free for most of the next 24 hours."

        if events:
            ev_strs = "; ".join(f"{e['summary']} at {e['start']}" for e in events)
            avail += f"\n\nUpcoming meetings: {ev_strs}."

        return {"calendar_context": avail}
    except Exception as e:
        print(f"[handle_calendar] Error: {e}")
        return {"calendar_context": ""}


# ── Node 4: execute_actions ───────────────────────────────────────────────────

def execute_actions(state: EmailState) -> dict:
    """
    Node 4 — Execute Gmail API mutations (live) or record to CSV (dry-run).

    V2 new action types:
      safe_archive      — archive to a named label (not INBOX removal)
      create_user_task  — create a local user task (for system alerts, no-reply emails)
      queue_pm_task     — queue a PM action for user approval
      create_draft_reply — now generates draft via capable model; adds day-wise label
    """
    dry_run       = state.get("dry_run", True)
    actions_taken: list[dict] = []
    pending_pm:   list[dict] = []

    if dry_run:
        for action in state.get("gmail_actions", []):
            actions_taken.append({**action, "status": "DRY_RUN"})
        write_audit_row({**state, "actions_taken": actions_taken})
        return {"actions_taken": actions_taken, "pending_pm_tasks": pending_pm}

    # ── LIVE MODE ─────────────────────────────────────────────────────────────
    from services.gmail_service import (
        apply_label, remove_inbox_label, star_thread,
        move_to_trash, mark_as_read, create_draft_reply,
    )

    creds     = state["creds"]
    gmail_id  = state["gmail_id"]
    thread_id = state["thread_id"]
    today_label = f"Drafts/{datetime.date.today().isoformat()}"  # e.g. Drafts/2026-08-21

    for action in state.get("gmail_actions", []):
        act           = action.get("action", "")
        result_action = dict(action)
        try:
            if act == "keep_inbox":
                pass  # Deliberate no-op

            elif act == "apply_label":
                apply_label(creds, gmail_id, action["label"])

            elif act == "remove_inbox":
                remove_inbox_label(creds, gmail_id)

            elif act == "safe_archive":
                # Archive to named label (reversible — email stays in Gmail, just not INBOX)
                label = action.get("label", "_LLM/Archived")
                apply_label(creds, gmail_id, label)
                remove_inbox_label(creds, gmail_id)
                result_action["archived_to"] = label

            elif act == "star_thread":
                star_thread(creds, thread_id)

            elif act == "mark_as_read":
                mark_as_read(creds, gmail_id)

            elif act == "create_draft_reply":
                # Use the enriched draft from the consolidated draft node (Phase 4)
                body = state.get("enriched_draft_reply", "").strip()
                if not body:
                    # Fallback: use suggested_reply from classification if enriched is empty
                    body = _generate_draft_reply(state)
                cal = state.get("calendar_context", "")
                if cal and "[availability" not in body.lower():
                    body += f"\n\n---\nMy availability:\n{cal}"

                draft_id = create_draft_reply(
                    creds, gmail_id, thread_id,
                    state["subject"], state["sender"],
                    body, state.get("message_id_header", ""),
                )
                # Apply day-wise label to the draft message
                try:
                    apply_label(creds, draft_id, today_label)
                except Exception:
                    pass  # Day label is non-critical
                result_action["draft_id"] = draft_id

            elif act == "create_user_task":
                # Local task entry for system alerts and no-reply emails
                result_action["task_summary"] = (
                    f"[User Task] {state.get('category', 'System Alert')}: "
                    f"{state.get('subject', '')} — from {state.get('sender', '')}"
                )
                # Future: persist to a local tasks table

            elif act == "queue_pm_task":
                # Queue a PM task for user approval (no execution yet)
                pm_summary = _extract_pm_summary(state)
                pm_entry = {
                    "summary":     pm_summary,
                    "gmail_id":    gmail_id,
                    "subject":     state.get("subject", ""),
                    "sender":      state.get("sender", ""),
                    "priority":    _urgency_to_priority(state.get("urgency_score", 5)),
                    "status":      "pending_approval",
                }
                pending_pm.append(pm_entry)
                result_action["pm_task"] = pm_entry

            result_action["status"] = "success"
        except Exception as e:
            err_str = str(e).lower()
            if "quota" in err_str or "resource_exhausted" in err_str:
                print(f"[execute_actions] QUOTA ERROR on {act}: {e}")
                result_action["status"] = f"quota_error: {e}"
            else:
                print(f"[execute_actions] Action {act} failed: {e}")
                result_action["status"] = f"error: {e}"

        actions_taken.append(result_action)

    write_audit_row({**state, "actions_taken": actions_taken})
    return {"actions_taken": actions_taken, "pending_pm_tasks": pending_pm}


def _generate_draft_reply(state: EmailState) -> str:
    """
    Generate a polished draft reply using the model configured for 'draft_reply'.
    Falls back to the existing suggested_reply from classification if generation fails.
    """
    existing = state.get("suggested_reply", "").strip()

    # If classification already produced a draft via the capable model, use it
    if existing:
        return existing

    # Otherwise generate via the dedicated draft model
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "Thank you for your email. I will respond shortly."

    try:
        llm = _build_llm("draft_reply", default_model="gemini-3.6-flash", default_temp=0.3)
        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "You are a professional email assistant. "
                "Write a polite, concise, and professional reply to the email below. "
                "Do not add placeholder text — write a complete, ready-to-send draft."
            )),
            ("human", "Subject: {subject}\nFrom: {sender}\n\n{body}"),
        ])
        chain = prompt | llm
        result = chain.invoke({
            "subject": state.get("subject", ""),
            "sender":  state.get("sender", ""),
            "body":    (state.get("body") or "")[:3000],
        })
        return result.content.strip() if hasattr(result, "content") else str(result).strip()
    except Exception as e:
        print(f"[execute_actions] Draft generation failed: {e}")
        return "Thank you for your email. I will get back to you shortly."


def _extract_pm_summary(state: EmailState) -> str:
    """Build a concise PM task summary from email state."""
    category  = state.get("category", "")
    subject   = state.get("subject", "")
    sender    = state.get("sender", "")
    return f"[{category}] {subject} — from {sender}"


def _urgency_to_priority(urgency_score: int) -> str:
    """Map urgency score (1-10) to PM priority string."""
    if urgency_score >= 9:
        return "Highest"
    elif urgency_score >= 7:
        return "High"
    elif urgency_score >= 4:
        return "Medium"
    elif urgency_score >= 2:
        return "Low"
    return "Lowest"


# ── Node 5: log_result ────────────────────────────────────────────────────────

def log_result(state: EmailState) -> dict:
    """Node 5 — Persist all V2 pipeline results to SQLite."""
    from database import SessionLocal
    from models import Email, EmailTag, EmailProcessingLog, PMActionQueue
    import json

    db = SessionLocal()
    try:
        # Write pipeline execution record (V2 fields included)
        log_entry = EmailProcessingLog(
            gmail_id               = state.get("gmail_id", ""),
            subject                = state.get("subject", ""),
            sender                 = state.get("sender", ""),
            category               = state.get("category", ""),
            urgency_score          = state.get("urgency_score", 0),
            suggested_reply        = state.get("suggested_reply", ""),
            actions_taken          = state.get("actions_taken", []),
            dry_run                = state.get("dry_run", True),
            pipeline_version       = "v2",
            user_id                = state.get("user_id"),
            confidence_score       = state.get("confidence_score"),
            reasoning              = state.get("reasoning", ""),
            is_reply_necessary     = state.get("is_reply_necessary"),
            reply_necessity_reason = state.get("reply_necessity_reason", ""),
            is_no_reply            = state.get("is_no_reply", False),
            is_vip                 = state.get("is_vip", False),
        )
        db.add(log_entry)

        # Persist pending PM tasks to the queue table (with thread/subject deduplication)
        for pm_task in state.get("pending_pm_tasks", []):
            existing_task = db.query(PMActionQueue).filter(
                (PMActionQueue.gmail_id == pm_task.get("gmail_id")) |
                ((PMActionQueue.email_subject == pm_task.get("subject")) & (PMActionQueue.status == "pending"))
            ).first()
            if not existing_task:
                task_entry = PMActionQueue(
                    gmail_id       = pm_task.get("gmail_id", ""),
                    email_subject  = pm_task.get("subject", ""),
                    email_sender   = pm_task.get("sender", ""),
                    summary        = pm_task.get("summary", ""),
                    priority       = pm_task.get("priority", "Medium"),
                    status         = "pending",
                )
                db.add(task_entry)

        # Update EmailTag if this email exists in the Email table
        email_rec = db.query(Email).filter(Email.gmail_id == state.get("gmail_id")).first()
        if email_rec:
            if email_rec.tags:
                tag = email_rec.tags
                tag.category               = state.get("category")
                tag.urgency_score          = state.get("urgency_score")
                tag.suggested_reply        = state.get("suggested_reply")
                tag.context_tags           = state.get("context_tags", [])
                tag.confidence_score       = state.get("confidence_score")
                tag.is_reply_necessary     = state.get("is_reply_necessary")
                tag.reply_necessity_reason = state.get("reply_necessity_reason", "")
            else:
                tag = EmailTag(
                    email_id               = email_rec.id,
                    primary_intent         = state.get("category", ""),
                    context_tags           = state.get("context_tags", []),
                    urgency_rating         = str(state.get("urgency_score", "")),
                    suggested_action       = "; ".join(
                        a.get("action", "") for a in state.get("gmail_actions", [])
                    ),
                    category               = state.get("category"),
                    urgency_score          = state.get("urgency_score"),
                    suggested_reply        = state.get("suggested_reply"),
                    confidence_score       = state.get("confidence_score"),
                    is_reply_necessary     = state.get("is_reply_necessary"),
                    reply_necessity_reason = state.get("reply_necessity_reason", ""),
                )
                db.add(tag)

        db.commit()
    except Exception as e:
        print(f"[log_result] DB error: {e}")
        db.rollback()
    finally:
        db.close()

    # Universal Audit Engine recording & 100-email auto-partitioning
    try:
        from pipeline.audit_manager import AuditManager
        AuditManager.get_instance().record_email(state)
    except Exception as audit_err:
        print(f"[log_result] Audit record error: {audit_err}")

    return {}
