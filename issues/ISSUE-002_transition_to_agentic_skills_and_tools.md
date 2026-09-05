# ISSUE-002: Architectural Transition from Hardcoded Rules & Heuristics to Agentic Skills & Tools

| Metadata | Details |
|---|---|
| **Issue ID** | `ISSUE-002` |
| **Title** | Architectural Transition from Hardcoded Rules & Static Heuristics to Agentic Skills & Tools (Function Calling) |
| **Status** | Proposed / Architectural Backlog |
| **Type** | Architectural Evolution / Paradigm Shift |
| **Target Era** | Modern Autonomous Agentic AI (Gemini 2.5/3.0+, Tool Use / Function Calling) |
| **Date Logged** | 2026-09-03 |

---

## 1. Executive Summary & Strategic Rationale

The current MailOrganizer implementation is a **hybrid system** that combines state-of-the-art LLMs (`gemini-3.6-flash`) with **pre-LLM heuristic rule engines**:
- Deterministic YAML mapping tables (`connectors.yaml`, `delegation_policies.yaml`, `rules/defaults.yaml`, `vip_rules.yaml`).
- Hardcoded regex string matching (e.g., matching `"taking this"` or `"fyi"` in email bodies).
- Recipient threshold counts (`len(recipients) > 5`).
- Rigid set-intersection tag routing.
- A fixed 9-node linear LangGraph DAG.

In the current era of AI/LLMs with **native function calling, structured tool use, and multi-turn conversational comprehension**, hand-coded heuristic logic is brittle, prone to configuration drift, and difficult to maintain. 

This proposal outlines the comprehensive plan to transition MailOrganizer from **brittle heuristic rule lookup** to an **Agentic Skills & Tools Architecture**, where the LLM is directly equipped with native tools and autonomously decides which tools to query and which actions to take.

---

## 2. Comprehensive Audit of Current Hardcoded Heuristics

The codebase currently contains five major subsystems operating on static rules:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CURRENT HEURISTIC INVENTORY                            │
├──────────────────────────┬──────────────────────────┬───────────────────────┤
│ Component                │ Current Mechanism        │ Files Affected        │
├──────────────────────────┼──────────────────────────┼───────────────────────┤
│ 1. Connector Selection   │ Static tag routing rules │ config/connectors.yaml│
│                          │ & set-intersection logic │ connector_manager.py  │
├──────────────────────────┼──────────────────────────┼───────────────────────┤
│ 2. Delegation & Ownership│ Regexes ("on it", "fyi"),│ delegation_policies.  │
│                          │ threshold count (>5),    │ yaml, ownership_      │
│                          │ keyword team member maps │ evaluator.py          │
├──────────────────────────┼──────────────────────────┼───────────────────────┤
│ 3. Action Planning       │ 550 synthetic rules      │ config/rules/         │
│                          │ mapping Category -> array│ defaults.yaml,        │
│                          │ of static action dicts   │ rules_engine.py       │
├──────────────────────────┼──────────────────────────┼───────────────────────┤
│ 4. Safety & Content      │ Regexes for no-reply/OOO,│ safety_rules.py,      │
│                          │ static keyword lists     │ vip_rules.yaml        │
│                          │ for sensitive content    │                       │
├──────────────────────────┼──────────────────────────┼───────────────────────┤
│ 5. Pipeline Topology     │ Fixed 9-node chain with  │ graph.py, nodes.py    │
│                          │ rigid router functions   │                       │
└──────────────────────────┴──────────────────────────┴───────────────────────┘
```

### Detailed Problem Breakdown by Component

#### 1. Connector Routing (`config/connectors.yaml`, `connector_manager.py`)
- **Current Mechanism**: The classifier outputs 8–15 string tags. `resolve_connectors_for_tags()` checks if any tag intersects with a hardcoded list in YAML (e.g. `["invoice", "pricing"]` $\rightarrow$ `["erp_financial", "gmail_search"]`).
- **Limitation**: If the classifier outputs `"accounting-inquiry"`, the connector is never triggered. The model cannot dynamically ask for context it realizes it needs.

#### 2. Delegation & Ownership (`config/delegation_policies.yaml`, `ownership_evaluator.py`)
- **Current Mechanism**:
  - Checks if `len(to_recipients) > 5` to decide if an email is a distribution list broadcast.
  - Regexes like `r"\b(visibility|fyi|cc'd)\b"` to check if user is an observer.
  - Regexes like `r"i('ll| will) (take|handle|grab|own) this"` to check if a teammate claimed it.
  - Keyword search like `["cloud", "architecture"]` to map to `david.miller@yourcompany.com`.
- **Limitation**: Natural human communication is subtle. A colleague saying *"I can review this tomorrow if needed"* may confuse regexes. An email with 6 recipients might still be a direct action for Marcus.

#### 3. Action Planning (`config/rules/defaults.yaml`, `rules_engine.py`)
- **Current Mechanism**: Category strings are looked up in a dictionary to fetch a static list of actions (e.g., `keep_inbox`, `@Urgent`, `create_draft_reply`).
- **Limitation**: Adding a new label or nuance requires updating YAML files and running tests against 550 synthetic rules.

#### 4. Safety & Content Pre-Checks (`safety_rules.py`)
- **Current Mechanism**: Python regexes search for strings like `subpoena`, `whistleblower`, `out of office`.
- **Limitation**: Easily triggered by false positives (e.g., a newsletter discussing whistleblower legislation) or bypassed by novel phrasing.

---

## 3. Target Architecture: The Agentic Skills & Tools Paradigm

Instead of a rigid assembly line of Python functions, the architecture transitions to an **Autonomous Agent equipped with a Toolbox**:

```
                              INCOMING EMAIL
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AUTONOMOUS MAIL AGENT                              │
│                    (Powered by Gemini Function Calling)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  "Let me read this email... The sender is asking about our Kafka latency    │
│   and scheduling a review with CTO Marcus Vance. Let me call my tools:"     │
│                                                                             │
│  Tool Call 1: search_mailbox_history(sender="sarah.connor@...", topic="kafka")
│  Tool Call 2: query_enterprise_rag(domain="engineering", query="kafka sla") │
│  Tool Call 3: check_calendar_schedule(date="2026-09-04", duration="30m")   │
│                                                                             │
│  "Now that I have the facts, I will take actions and compose the draft:"    │
│                                                                             │
│  Tool Call 4: mailbox_actions(                                              │
│                 apply_labels=["@Urgent"],                                   │
│                 keep_inbox=True,                                            │
│                 star=True,                                                  │
│                 draft_reply="I am reviewing the deployment topology under..."│
│               )                                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Proposed Tool Suite Specifications

```python
# 1. Historical Mailbox Intelligence Tool
def search_mailbox_history(sender: Optional[str], query: str, max_results: int = 3) -> List[dict]:
    """Search user's past email threads for prior agreements, context, or quotes."""

# 2. Enterprise Knowledge Tool (Consolidating RAG + MCP)
def query_enterprise_rag(domain: str, query: str) -> List[str]:
    """Query company knowledge bases (engineering docs, HR policies, legal terms)."""

# 3. Calendar & Availability Tool
def check_calendar_schedule(start_date: str, end_date: str, duration_minutes: int = 30) -> List[str]:
    """Query user's calendar for actual free/busy meeting slots."""

# 4. Organization Directory & Skill Matcher Tool
def find_team_specialist(topic_or_skill: str) -> Optional[dict]:
    """Dynamically find the right team member to delegate to based on team directory."""

# 5. Mailbox Action Execution Tool
def execute_mailbox_actions(
    labels_to_apply: List[str],
    inbox_action: str,  # 'keep_inbox' | 'archive' | 'trash'
    star_thread: bool = False,
    draft_reply_text: Optional[str] = None
) -> dict:
    """Execute label, star, archive, and draft actions on the email thread."""
```

---

## 4. What Remains Deterministic (The Safety Sandbox)

An agentic system does not mean uncontrolled execution. Deterministic boundaries form the **Safety Sandbox**:

1. **Safety Circuit Breakers**:
   - The model can *request* `delete_email`, but a deterministic guardrail intercepts and blocks destructive operations.
   - Sensitive legal/whistleblower emails deterministically lock down drafting before any external tool is touched.
2. **Dry-Run Enforcement**:
   - All tool mutations (drafting, archiving, labeling) pass through the deterministic dry-run flag.
3. **Authentication & Rate Limiting**:
   - OAuth token refresh, token caching, and quota backoff remain strictly managed by Python infrastructure.
4. **Audit Logging**:
   - Deterministic CSV/database auditing logs every tool call, argument, and reasoning trace for full human accountability.

---

## 5. Phased Migration Roadmap

```text
Phase A: Toolification ──> Phase B: Semantic Delegation ──> Phase C: Graph Collapse
(Connectors -> Tools)     (Regexes -> LLM Context)       (9 Nodes -> ReAct Loop)
```

### Phase A: Toolification of External Knowledge (Connectors $\rightarrow$ Tools)
- Wrap `RAGConnector`, `GmailSearchConnector`, and `CalendarConnector` as standard LangChain / Gemini Callable Tools.
- In `enrich_context`, instead of tag routing, allow the LLM to call these tools dynamically if context is needed.

### Phase B: Semantic Delegation & Action Tools
- Replace regex-based `ownership_evaluator.py` with an LLM Ownership prompt that natively understands thread roles.
- Replace `rules/defaults.yaml` with the `execute_mailbox_actions` tool.

### Phase C: Graph Streamlining & Simplification
- Collapse the multi-step pipeline into a streamlined, high-performance Agentic ReAct loop.
- Remove deprecated YAML rule matrices, reducing configuration overhead by over 70%.

---

## 6. Business & Developer Benefits

1. **Zero Configuration Overhead**: Eliminates the need to maintain hundreds of synthetic YAML rules and regexes.
2. **Nuance & Resilience**: LLMs naturally understand human phrasing variations, sarcasm, and implicit commitments that regexes miss.
3. **Self-Correction**: The agent can inspect a search result, realize it needs more info, and execute a follow-up tool call before finalizing a reply.
4. **Massive Code Reduction**: Replaces ~1,500 lines of brittle heuristic code with concise tool definitions and clean prompt guidelines.
