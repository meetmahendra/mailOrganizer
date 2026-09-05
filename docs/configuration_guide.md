# MailOrganizer Enterprise Configuration Guide & Admin Handbook

> **Audience**: System Administrators, DevOps Engineers, and Enterprise IT Teams deploying and configuring MailOrganizer for their organization or client environments.
>
> **Goal**: Provide step-by-step, recipe-driven guidance for configuring all aspects of MailOrganizer—including external enterprise RAG services, Outbound & Inbound MCP servers, dynamic capability-based delegation, calendar integration, and executive communication style—with zero hardcoded logic.

---

## Table of Contents

1. [Architecture Overview & Governance Principles](#1-architecture-overview--governance-principles)
2. [Configuration Directory Structure](#2-configuration-directory-structure)
3. [Recipe 1: 5-Minute Minimal Setup (Calendar + Roster)](#recipe-1-5-minute-minimal-setup-calendar--roster)
4. [Recipe 2: Connecting External RAG Services (Vertex AI / REST)](#recipe-2-connecting-external-rag-services-vertex-ai--rest)
5. [Recipe 3: Connecting Outbound MCP Tool Servers (Jira, GitHub, Postgres)](#recipe-3-connecting-outbound-mcp-tool-servers-jira-github-postgres)
6. [Recipe 4: Dynamic Capability-Based Delegation (Zero Hardcoding)](#recipe-4-dynamic-capability-based-delegation-zero-hardcoding)
7. [Recipe 5: Executive Persona, Voice & Anti-Stalling Rules](#recipe-5-executive-persona-voice--anti-stalling-rules)
8. [Recipe 6: Understanding Bidirectional MCP (Inbound vs Outbound)](#recipe-6-understanding-bidirectional-mcp-inbound-vs-outbound)
9. [Recipe 7: Pre-Flight Verification with Config Doctor](#recipe-7-pre-flight-verification-with-config-doctor)
10. [Troubleshooting & Common Admin Pitfalls](#troubleshooting--common-admin-pitfalls)

---

## 1. Architecture Overview & Governance Principles

MailOrganizer operates as an **institutional memory agent and intelligent email copilot**. Unlike generic LLM wrapper scripts, it adheres to four core enterprise architectural rules:

1. **No Internal Vector DB Bloat (Federated Consumer)**: MailOrganizer does **not** maintain an internal Chroma/Pinecone vector store. Instead, it federates queries to your organization’s pre-existing, authoritative RAG endpoints (e.g., HR wiki, Engineering runbooks, Legal contract repositories).
2. **Two-Way Integration (Query + Modify)**: Knowledge connectors support both querying facts (`query()`) and recording audit feedback or updating upstream tickets (`modify()`).
3. **Dynamic Capability Delegation (Zero Hardcoded Personnel)**: Email routing and ownership resolution do not hardcode individuals' email addresses in Python scripts. The system queries live enterprise systems (Jira component leads, GitHub CODEOWNERS, PagerDuty on-call schedules, Org Directory) dynamically.
4. **Deterministic Tag-Based Routing**: Connector queries are triggered deterministically based on taxonomy tags identified during email classification. This delivers **zero extra LLM latency or cost** during connector routing.
5. **Fail-Fast Pydantic Schema Validation**: All YAML configurations are strictly validated on boot using Pydantic models in `config/schemas.py`. Any typo or syntax error fails immediately at startup with an explanatory message rather than causing an error midway through processing an email.

---

## 2. Configuration Directory Structure

All runtime behavior is controlled declaratively inside the `config/` directory:

```
config/
├── connectors.yaml             # External RAG, MCP, Calendar, and routing rules
├── connectors.example.yaml     # Heavily commented reference template
├── delegation_policies.yaml    # Dynamic ownership and delegation strategies
├── delegation_policies.example.yaml
├── user_persona.yaml           # Executive voice, tone, and communication rules
├── user_persona.example.yaml
├── models.yaml                 # Multi-provider LLM routing (Gemini, OpenAI, Claude, etc.)
├── vip_rules.yaml              # Domain VIP lists and no-reply patterns
├── schemas.py                  # Pydantic schemas validating all YAML configs
└── organization/               # Enterprise roster and department registry
    ├── company_profile.yaml    # Company name, domains, strategic projects
    ├── departments.yaml        # Departments, default labels, approval hierarchies
    ├── roster.yaml             # Employee directory with reporting hierarchy
    └── external_stakeholders.yaml # Strategic Tier-1 client registry
```

> **Environment Variable Interpolation**: All configuration files support `${ENV_VAR}` syntax. You never need to hardcode API tokens or sensitive credentials in YAML files.

---

## Recipe 1: 5-Minute Minimal Setup (Calendar + Roster)

To get MailOrganizer up and running with Google Calendar availability and organizational VIP awareness:

### Step 1: Set up `.env`
Create or update `.env` in the project root:
```bash
GEMINI_API_KEY=your_gemini_api_key_here
PORT=8000
DEBUG=False
DRY_RUN=True  # Keep True during initial setup to prevent unwanted Gmail mutations
```

### Step 2: Configure User Persona
Copy `config/user_persona.example.yaml` to `config/user_persona.yaml`:
```bash
cp config/user_persona.example.yaml config/user_persona.yaml
```
Open `config/user_persona.yaml` and set the mailbox owner's details:
```yaml
name: "Alex Mercer"
title: "VP of Engineering"
department: "Engineering"
organization: "Acme Cloud Technologies"
tone: "direct, collegial, executive, precise"
signature: |
  Best regards,
  Alex Mercer | VP of Engineering
  Acme Cloud Technologies
  alex.mercer@acme.com
communication_rules:
  - "Always be concise and actionable: provide clear answers or next steps."
  - "When responding to meeting requests, propose 2 concrete slots."
```

### Step 3: Enable Google Calendar in `config/connectors.yaml`
```yaml
calendar:
  enabled: true
  provider: "google"
  timezone: "America/New_York"
  buffer_minutes: 15

routing_rules:
  - tags: ["meeting", "schedule", "calendar", "reschedule", "appointment", "call"]
    connectors: ["calendar"]
```

### Step 4: Verify with Config Doctor
Run the pre-flight diagnostic CLI:
```bash
python -m app.config_doctor
```
If all checks pass, MailOrganizer is ready to triage scheduling requests and draft calendar-aware replies.

---

## Recipe 2: Connecting External RAG Services (Vertex AI / REST)

If your enterprise already maintains internal RAG knowledge bases (e.g. Confluence documentation index, HR policy database, Legal contract repository), you can configure MailOrganizer to query them directly.

### Step 1: Declare RAG Endpoints in `config/connectors.yaml`
```yaml
external_rag_services:
  hr_policies:
    endpoint: "https://rag-gateway.corp.internal/v1/hr/query"
    modify_endpoint: "https://rag-gateway.corp.internal/v1/hr/feedback"
    auth_header: "Bearer ${HR_RAG_TOKEN}"
    description: "Employee health benefits, PTO rules, parental leave, travel expense policy"
    timeout_seconds: 2.0

  engineering_docs:
    endpoint: "https://rag-gateway.corp.internal/v1/engineering/query"
    modify_endpoint: null
    auth_header: "Bearer ${ENG_RAG_TOKEN}"
    description: "Cloud architecture, Kubernetes deployment standards, SLA commitments, runbooks"
    timeout_seconds: 2.0

  legal_contracts:
    endpoint: "https://rag-gateway.corp.internal/v1/legal/query"
    modify_endpoint: null
    auth_header: "Bearer ${LEGAL_RAG_TOKEN}"
    description: "Master Service Agreements (MSA), standard NDAs, data privacy addenda, GDPR guidelines"
    timeout_seconds: 2.5
```

### Step 2: Configure Environment Variables in `.env`
```bash
HR_RAG_TOKEN=secret_hr_token_xyz
ENG_RAG_TOKEN=secret_eng_token_xyz
LEGAL_RAG_TOKEN=secret_legal_token_xyz
```

### Step 3: Map Email Tags to Connectors
Add tag mappings under `routing_rules` in `config/connectors.yaml`:
```yaml
routing_rules:
  - tags: ["contract", "legal", "compliance", "audit", "nda", "gdpr", "soc2"]
    connectors: ["legal_contracts_rag"]

  - tags: ["incident", "outage", "infrastructure", "deployment", "sre", "kubernetes"]
    connectors: ["engineering_docs_rag"]

  - tags: ["benefits", "pto", "leave", "hr", "payroll", "expense"]
    connectors: ["hr_policies_rag"]
```

### Expected RAG API Contract
MailOrganizer sends an HTTP `POST` request with JSON payload:
```json
{
  "query": "What is the policy for parental leave reimbursement cap?",
  "top_k": 3,
  "filters": {}
}
```
And expects a JSON response in any standard format:
```json
{
  "results": [
    {
      "content": "Employees are eligible for up to 16 weeks of fully paid parental leave...",
      "source": "HR Handbook 2026 Section 4.2",
      "timestamp": "2026-01-15"
    }
  ]
}
```
*(Also compatible with `{"chunks": [...]}` or `{"documents": [...]}` formats).*

---

## Recipe 3: Connecting Outbound MCP Tool Servers (Jira, GitHub, Postgres)

MailOrganizer can act as an **Outbound MCP Client**, invoking tools on remote Model Context Protocol servers to query issue trackers, code ownership, or customer databases.

### Supported Transports:
- `stdio`: Spawns a local subprocess (e.g. `npx @modelcontextprotocol/server-jira`).
- `sse`: Connects to an existing remote HTTP Server-Sent Events (SSE) MCP daemon.

### Example: Connecting Jira and PostgreSQL via MCP
In `config/connectors.yaml`:
```yaml
mcp_servers:
  jira:
    transport: "stdio"
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-jira"]
    env:
      JIRA_URL: "${JIRA_URL}"
      JIRA_API_TOKEN: "${JIRA_API_TOKEN}"

  postgres_erp:
    transport: "sse"
    url: "http://internal-erp.corp.local/mcp"

routing_rules:
  - tags: ["incident", "outage", "bug", "jira", "sre"]
    connectors: ["jira_mcp"]
  - tags: ["invoice", "billing", "erp", "payment"]
    connectors: ["postgres_erp_mcp"]
```

Ensure the environment variables are declared in `.env`:
```bash
JIRA_URL=https://yourcompany.atlassian.net
JIRA_API_TOKEN=your_jira_personal_access_token
```

---

## Recipe 4: Dynamic Capability-Based Delegation (Zero Hardcoding)

In real enterprise workflows, emails often arrive where the recipient is not the person who should respond, or where an internal team member is already handling it.

Edit `config/delegation_policies.yaml`:

```yaml
# ── 1. Multi-Recipient & CC Disambiguation ────────────────────────────────────
multi_recipient_to:
  # When multiple recipients are in To:, semantic mention in body takes precedence.
  # If someone else on To: is explicitly named, current user is marked OBSERVER_ONLY.
  strategy: "semantic_mention_priority"

  # If To: recipient count exceeds this threshold and user is not specifically
  # called out by name, treat as broadcast announcement (suppress reply draft).
  broadcast_threshold: 4

# ── 2. Active Teammate Handling Tracker ───────────────────────────────────────
teammate_handling:
  # If an internal colleague has already replied to this thread with a commitment
  # ("I am looking into this", "Handling now"), suppress auto-draft generation.
  suppress_draft_if_internal_reply: true
  reopen_on_unanswered_followups: 2

# ── 3. Dynamic Capability-Based Delegation Strategies ────────────────────────
dynamic_delegation_strategies:
  # Strategy A: Delegate by Project Ownership (Queries PM / Jira)
  - trigger: "email_references_registered_project"
    resolver: "pm_service.get_project_lead"
    params:
      fallback_department: "Engineering"
    template: "Looping in {name} ({email}), the project lead for {project_name}. {first_name}, could you please assist?"

  # Strategy B: Delegate by Live SRE On-Call (Queries PagerDuty / Schedule)
  - trigger: "topic == 'Cloud Infrastructure & SRE' and urgency >= 7"
    resolver: "oncall_service.get_current_oncall"
    params:
      schedule: "sre-primary"
      fallback_role: "Head of SRE"
    template: "Looping in {name} ({email}) from our SRE team who is on-call for infrastructure alerts."

  # Strategy C: Delegate by Legal & Regulatory Capability (Queries Org Directory)
  - trigger: "topic == 'Legal, Risk & Regulatory'"
    resolver: "directory_service.find_by_capability"
    params:
      department: "Legal"
      specialty: "Contracts & Compliance"
    template: "Looping in {name} ({email}) from Legal & Compliance to review the terms."

# ── 4. Missing Information Policy (Holding Replies) ──────────────────────────
missing_information:
  action: "create_internal_task_and_holding_reply"
  default_holding_reply: >
    Thank you for reaching out. I am confirming the details with our engineering and operations
    leads today and will follow up with confirmation by tomorrow afternoon.
```

### How Resolvers Work Dynamically:
- When an email references `"Project Odyssey"`, the system queries the company's registered projects in `config/organization/company_profile.yaml` and finds the assigned project lead.
- If team members rotate, you only update the roster or on-call schedule. **No code or prompt changes are required.**

---

## Recipe 5: Executive Persona, Voice & Anti-Stalling Rules

To prevent the AI from generating generic, embarrassing, or robotic responses (e.g., *"I have received your email and am reviewing it"*), configure `config/user_persona.yaml`:

```yaml
name: "Marcus Vance"
title: "Chief Technology Officer"
department: "Executive Engineering"
organization: "TechGlobal Cloud Solutions"

# Tone profile for generated drafts:
tone: "direct, collegial, executive, precise"

# Default signature template:
signature: |
  Best regards,
  Marcus Vance | Chief Technology Officer
  TechGlobal Cloud Solutions
  marcus.vance@yourcompany.com

# Explicit communication rules enforced on draft generation:
communication_rules:
  - "Never use robotic stalling boilerplate like 'I am gathering documentation' or 'I will look into this shortly'."
  - "Always be concise and actionable: provide clear answers, decisions, or exact time slots."
  - "When responding to calendar requests, propose 2 specific slots rather than open-ended queries."
  - "Reference exact ticket IDs, invoice numbers, or commit hashes when provided in context."
  - "Maintain high professional warmth with strategic clients while remaining brief."
```

---

## Recipe 6: Understanding Bidirectional MCP (Inbound vs Outbound)

MailOrganizer features a **bidirectional Model Context Protocol (MCP)** architecture:

```
                      ┌────────────────────────────────────────┐
                      │    Host AI Agent / Client              │
                      │  (Claude Desktop, Cursor, Custom Agent)│
                      └──────────────────┬─────────────────────┘
                                         │  (SSE / HTTP)
                                         ▼
                      ┌────────────────────────────────────────┐
                      │ INBOUND MCP SERVER (mcp_server/server) │
                      │ • triage_unread_emails                 │
                      │ • search_emails                        │
                      │ • create_draft / execute_action        │
                      └──────────────────┬─────────────────────┘
                                         │
                                         ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        MAILORGANIZER ENGINE                            │
│  LangGraph Pipeline: Pre-Check -> Classify -> Ownership -> Enrich ...  │
└────────────────────────────────┬───────────────────────────────────────┘
                                 │
                 (Outbound Client Calls via Connectors)
                                 │
        ┌────────────────────────┴────────────────────────┐
        ▼                                                 ▼
┌───────────────────────────────┐       ┌───────────────────────────────┐
│ OUTBOUND MCP: Jira / Linear   │       │ OUTBOUND MCP: PostgreSQL ERP  │
│ (Reads tickets, updates bugs) │       │ (Verifies invoices & payments)│
└───────────────────────────────┘       └───────────────────────────────┘
```

### 1. Inbound MCP Server (`mcp_server/`)
- **Purpose**: Exposes MailOrganizer to outside LLMs and orchestrators.
- **Port**: `8001` (SSE Transport at `http://localhost:8001/sse`).
- **How to start**:
  ```bash
  python -m mcp_server.server
  ```
- **How to connect Claude Desktop**:
  Add to your `claude_desktop_config.json`:
  ```json
  {
    "mcpServers": {
      "gmail-organizer": {
        "url": "http://localhost:8001/sse"
      }
    }
  }
  ```

### 2. Outbound MCP Connectors (`app/connectors/mcp_connector.py`)
- **Purpose**: Allows MailOrganizer to reach out to external services (Jira, Postgres, GitHub).
- **Configuration**: Defined in `config/connectors.yaml` under `mcp_servers`.

---

## Recipe 7: Pre-Flight Verification with Config Doctor

Before running MailOrganizer in production, always execute the built-in diagnostic tool:

```bash
python -m app.config_doctor
```

### What Config Doctor Validates:
1. **Schema Validation**: Tests `connectors.yaml`, `delegation_policies.yaml`, and `user_persona.yaml` against Pydantic models.
2. **Environment Variables**: Confirms `GEMINI_API_KEY`, RAG tokens, and MCP credentials are set.
3. **Live Connector Availability**: Sends ping/health checks to configured RAG and calendar services.
4. **Deterministic Routing**: Confirms tag queries correctly resolve to registered connectors.

### Sample Successful Output:
```
========================================================================
[*] MAIL ORGANIZER — ENTERPRISE CONFIGURATION & CONNECTOR DOCTOR
========================================================================

[*] Checking configuration schemas and syntax...
  [+] config/connectors.yaml ......................... [OK: Valid Schema]
  [+] config/delegation_policies.yaml ................ [OK: Valid Schema]
  [+] config/user_persona.yaml ....................... [OK: Valid Schema (Marcus Vance)]

[*] Checking environment variables & API tokens...
  [+] GEMINI_API_KEY       ......................... [OK: Set (AIza...abc)]
  [!] HR_RAG_TOKEN         ......................... [UNSET: Optional]
  [!] JIRA_URL             ......................... [UNSET: Optional]

[*] Checking registered knowledge connectors...
  [i] Total active connectors registered: 5
  [+] Connector: calendar               ............. [OK: Available]
  [+] Connector: gmail_search           ............. [OK: Available]
  [+] Connector: hr_policies_rag        ............. [OK: Available]
  [+] Connector: engineering_docs_rag   ............. [OK: Available]
  [+] Connector: legal_contracts_rag    ............. [OK: Available]

[*] Testing deterministic tag-to-connector routing...
  [+] Tags ['meeting', 'reschedule']           -> ['calendar']
  [+] Tags ['invoice', 'wire-transfer']        -> ['gmail_search']
  [+] Tags ['incident', 'sre', 'outage']       -> ['engineering_docs_rag']
  [+] Tags ['legal', 'compliance', 'nda']      -> ['legal_contracts_rag']

========================================================================
 [*] DIAGNOSTICS SUMMARY
========================================================================
• Total Checks:  17
• Passed Checks: 15/17
• Warnings:      2 (Optional tokens unset)
• Errors:        0

[+] Result: ALL SYSTEMS OPERATIONAL! MailOrganizer is ready for live use.
========================================================================
```

---

## Troubleshooting & Common Admin Pitfalls

### 1. "ValidationError: 1 validation error for ConnectorsConfig"
- **Cause**: Typo in YAML key (e.g. `externl_rag_services` instead of `external_rag_services`).
- **Fix**: Check field names against `config/connectors.example.yaml`. Config Doctor points to the exact line number.

### 2. "Quota Exceeded (HTTP 429) during batch processing"
- **Cause**: Exceeding Gemini API tier requests per minute.
- **Fix**: MailOrganizer automatically catches 429 quota errors and safely marks the email for `Needs Review` with `@Quota_Exceeded` label. To increase throughput, ensure your API key has a billing account linked or configure model overrides in `config/models.yaml`.

### 3. "Windows UnicodeEncodeError (cp1252)"
- **Cause**: PowerShell or Windows cmd.exe default encoding does not support emoji characters.
- **Fix**: All MailOrganizer CLI scripts include `sys.stdout.reconfigure(encoding='utf-8')` and use clean ASCII status indicators (`[+]`, `[-]`, `[!]`). Avoid adding unencoded unicode characters to custom scripts.

### 4. "Draft created for Out of Office message"
- **Cause**: Missing auto-reply headers in custom synthetic payloads.
- **Fix**: Real Gmail messages include `Auto-Submitted: auto-replied` or `X-Auto-Response-Suppress: OOF`. The Phase 5 OOO Infinite Loop Shield automatically strips reply actions when these headers or body patterns ("I am out of the office") are detected.

---

## Summary Checklist for Production Deployment

- [ ] `.env` created with valid `GEMINI_API_KEY`
- [ ] `config/connectors.yaml` configured and validated
- [ ] `config/delegation_policies.yaml` configured
- [ ] `config/user_persona.yaml` customized for the target user
- [ ] `config/organization/roster.yaml` populated with employee contacts
- [ ] Ran `python -m app.config_doctor` with **0 errors**
- [ ] Ran `python run_tests.py --mode=rules --quality-gate` with **100% pass rate**
