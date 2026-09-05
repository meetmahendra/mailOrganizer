# ISSUE-001: Missing Baseline Email Search for LLM Context Collection

| Metadata | Details |
|---|---|
| **Issue ID** | `ISSUE-001` |
| **Title** | Missing Baseline Email Search for LLM Context Collection When No Connector/Tag Configured |
| **Status** | Open / Planned for Future Phase |
| **Severity** | High (Context & Draft Quality) |
| **Component** | Pipeline Context Enrichment (`app/pipeline/nodes.py`, `app/connectors/`) |
| **Date Logged** | 2026-09-03 |

---

## 1. Problem Description

When an email is processed by the LangGraph pipeline, the LLM is expected to compose fact-grounded, context-aware reply drafts using:
1. Enterprise knowledge connectors (RAG, Calendar, MCP).
2. **Historical email search** (past correspondence and agreements with the sender).

However, during live benchmark inspection and testing, it was observed that **email search is not being executed for the vast majority of emails**. If no external connector matches the email's context tags, or if no tag routing rule is configured, the pipeline completely bypasses email search and sends an empty context block to the drafting LLM.

As a result, even though the user has an active mailbox full of past correspondence with the sender, the LLM drafts replies in a vacuum without knowing past commitments, prior quotes, or previous context.

---

## 2. Root Cause Analysis (RCA)

Investigation of the codebase revealed three specific architectural bottlenecks:

### Bottleneck 1: Restrictive Tag Routing in `config/connectors.yaml`
In [`config/connectors.yaml`](file:///d:/mailOrganizer/config/connectors.yaml#L84-L86), `gmail_search` is configured under `routing_rules` exclusively for financial/billing tags:
```yaml
routing_rules:
  - tags: ["invoice", "payment", "wire-transfer", "receipt", "chargeback", "financial", "pricing"]
    connectors: ["erp_financial", "gmail_search"]
```
If an email is about technical architecture, project updates, executive check-ins, sales inquiries, or general questions, `gmail_search` is **never selected by tag resolution**.

### Bottleneck 2: Early Exit in `app/pipeline/nodes.py:enrich_context()`
In [`app/pipeline/nodes.py`](file:///d:/mailOrganizer/app/pipeline/nodes.py#L523-L539):
```python
def enrich_context(state: EmailState) -> dict:
    manager = get_connector_manager()
    context_tags = state.get("context_tags", [])
    connector_ids = manager.resolve_connectors_for_tags(context_tags)

    if not connector_ids:
        return {"retrieved_facts": "", "pending_mutations": []}  # <--- Bypasses all search!
```
When no tag matches a routing rule, `connector_ids` is empty (`[]`). The node immediately returns an empty string for `retrieved_facts` without checking if `gmail_search` is enabled as a baseline context source.

### Bottleneck 3: Classifier LLM Only Inspects Same Thread & Local SQLite
In `classify_email()` ([`app/pipeline/nodes.py`](file:///d:/mailOrganizer/app/pipeline/nodes.py#L389-L395)), the classification step calls:
- `build_thread_history(creds, thread_id)`: Only retrieves messages sharing the exact same Gmail thread ID.
- `build_non_chained_topic_history(sender, subject)`: Only queries the local SQLite `EmailProcessingLog` table for past app logs.
It does **not** query Gmail across past threads from the sender for prior interactions.

---

## 3. Current vs. Expected Behavior

| Scenario | Current Pipeline Behavior | Expected Baseline Behavior |
|---|---|---|
| **No tag matched or no connector configured** | `enrich_context` exits early; returns `retrieved_facts: ""` | Falls back to `gmail_search` to pull past correspondence with the sender |
| **Non-financial email (e.g. Project Odyssey check-in)** | `gmail_search` is omitted; only RAG query attempted | Queries `gmail_search` for previous emails with the sender about the topic |
| **Drafting LLM input (`generate_enriched_draft`)** | Receives zero past email history unless tagged as invoice/payment | Receives 2–3 concise snippets of past emails with the sender |

---

## 4. Proposed Implementation Plan

When ready to implement, the following changes should be applied:

### Step 1: Add Baseline Fallback in `app/pipeline/nodes.py:enrich_context()`
If `connector_ids` is empty after tag routing, check if `gmail_search` is enabled in `ConnectorManager`. If enabled, automatically include `["gmail_search"]` as the default fallback:
```python
if not connector_ids:
    if manager.is_connector_available("gmail_search"):
        connector_ids = ["gmail_search"]
    else:
        return {"retrieved_facts": "", "pending_mutations": []}
```

### Step 2: Configure Universal Baseline in `config/connectors.yaml`
Add support for a `default_connectors` list or a universal baseline rule that always checks past email history for any primary actionee email:
```yaml
# Connectors that run for all actionable emails as baseline context
baseline_connectors:
  - "gmail_search"
```

### Step 3: Enhance `GmailSearchConnector` Query Synthesis
Ensure `GmailSearchConnector.query()` safely extracts:
- Sender email: `from:{clean_sender}`
- High-value subject keywords (excluding Re:, Fwd:, etc.)
- Capped results: top 2-3 most recent threads, max 150 words per snippet.

### Step 4: Verification & Test Coverage
1. **Unit Test**: Test that `enrich_context` returns past email snippets when `context_tags` is empty.
2. **Live Test**: Verify that drafting an email to a frequent correspondent incorporates prior thread context even when no enterprise RAG tag matches.

---

## 5. Files Affected

- [`config/connectors.yaml`](file:///d:/mailOrganizer/config/connectors.yaml): Connector routing rules and baseline configuration.
- [`app/connectors/connector_manager.py`](file:///d:/mailOrganizer/app/connectors/connector_manager.py): Baseline connector resolution.
- [`app/connectors/gmail_search_connector.py`](file:///d:/mailOrganizer/app/connectors/gmail_search_connector.py): Query formatting and result formatting.
- [`app/pipeline/nodes.py`](file:///d:/mailOrganizer/app/pipeline/nodes.py): `enrich_context` fallback logic.
