# ISSUE-003: Raw HTML Ingestion Token Bloat & Type-Aware Email Reply Formatting

| Metadata | Details |
|---|---|
| **Issue ID** | `ISSUE-003` |
| **Title** | Raw HTML Ingestion Token Bloat & Type-Aware Email Reply Formatting |
| **Status** | Open / Planned for Implementation |
| **Severity** | High (Cost, Latency, Token Budget & Draft Quality) |
| **Component** | Email Ingestion & Normalisation (`app/services/gmail_service.py`, `app/utils/text_utils.py`), Pipeline Nodes (`app/pipeline/nodes.py`) |
| **Date Logged** | 2026-09-12 |

---

## 1. Problem Description

Currently, the MailOrganizer pipeline suffers from two interrelated issues that degrade token efficiency, drafting quality, and context utilization:

1. **Unnecessary Token Bloat via Raw HTML Ingestion**:
   - In [`app/services/gmail_service.py`](file:///d:/mailOrganizer/app/services/gmail_service.py#L40-L56), when extracting email content from multipart or HTML-only messages, raw HTML payloads—including `<!DOCTYPE html>`, `<style>`, `<script>`, nested `<table>` tags, inline CSS attributes, navigation menus, tracking pixels, and legal disclaimers—are directly decoded and assigned to the `body` field.
   - In [`app/pipeline/nodes.py:pre_check_email()`](file:///d:/mailOrganizer/app/pipeline/nodes.py#L340), `normalise_body(state.get("body", ""))` is invoked with the default parameter `mime_type='text/plain'`. Consequently, the HTML stripping and regex cleaning logic is completely bypassed.
   - When this uncleaned body is passed to [`classify_email()`](file:///d:/mailOrganizer/app/pipeline/nodes.py#L405) (capped at 4,000 characters) and [`generate_enriched_draft()`](file:///d:/mailOrganizer/app/pipeline/nodes.py#L702-L707) (capped at 3,000 characters), a significant portion of the token limit is consumed by useless DOM boilerplate.
   - **Critical Side Effect**: Because of the hard character cutoffs (`[:4000]` and `[:3000]`), the substantive message text is often truncated before the LLM ever sees it, leading to hallucinated or low-quality replies and wasted tokens/costs.

2. **Lack of Category- & Type-Aware Reply Formatting**:
   - In [`app/pipeline/nodes.py:generate_enriched_draft()`](file:///d:/mailOrganizer/app/pipeline/nodes.py#L677-L692), the drafting prompt uses a static, one-size-fits-all instruction set regardless of the nature or format of the email.
   - The LLM is not instructed on how to structure its response based on the **email type / category** (e.g., bulleted action items with owners and deadlines for operational tasks, structured time-slot proposals for calendar invites, table or itemized breakdowns for invoices/receipts, or high-level BLUF [Bottom Line Up Front] summaries for executives).
   - Furthermore, the LLM is not provided clear guidelines on generating clean, professional text/markdown layouts without raw HTML artifacts.

---

## 2. Root Cause Analysis (RCA)

### Bottleneck 1: `_extract_body` Appends HTML in Multipart Messages
In [`app/services/gmail_service.py`](file:///d:/mailOrganizer/app/services/gmail_service.py#L40-L56):
```python
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
```
- In multipart emails (`multipart/alternative` or `multipart/related`), the loop parses `text/plain` and then enters the `else:` branch for `text/html`, appending the entire raw HTML payload to `text`.
- If an email has no `text/plain` part, the raw HTML is returned directly as the email body.

### Bottleneck 2: Ineffective Sanitization in `pre_check_email()`
In [`app/pipeline/nodes.py`](file:///d:/mailOrganizer/app/pipeline/nodes.py#L340):
```python
clean_body = normalise_body(state.get("body", ""))
```
In [`app/utils/text_utils.py`](file:///d:/mailOrganizer/app/utils/text_utils.py#L58-L90):
- `normalise_body(text, mime_type='text/plain')` defaults to `text/plain`, so lines 74–83 (HTML tag and style/script stripping) are never executed.
- Even when executed, simple regex tag stripping leaves inline styling noise, excess whitespace, and layout breakage.

### Bottleneck 3: Static Prompt in `generate_enriched_draft()`
In [`app/pipeline/nodes.py`](file:///d:/mailOrganizer/app/pipeline/nodes.py#L677-L692):
- The prompt instructs the LLM generically: *"Keep the reply concise but complete. A busy executive wrote this."*
- It fails to adapt formatting to the incoming email category (`Action Required`, `Calendar/Scheduling`, `Receipts/Financial`, etc.).
- It does not combine the sanitized body cleanly with context retrieved from mail search (`gmail_search`), organizational hierarchy, and thread history.

---

## 3. Current vs. Expected Behavior

| Dimension | Current Pipeline Behavior | Expected Pipeline Behavior |
|---|---|---|
| **Email Body Ingestion** | Raw HTML tags (`<head>`, `<style>`, `<div>`, `<table>`), CSS classes, and tracker URLs sent to LLM | Only substantive readable text is extracted; HTML boilerplate, trackers, and redundant styling are stripped |
| **Token Budget Consumption** | 40–70% of character limit consumed by HTML markup | 100% of character limit dedicated to actual email text and enriched context |
| **Context Assembly** | Sliced prematurely (`[:3000]`) due to large HTML overhead, often missing the core message | Sanitized text + historical mail search snippets + org context + calendar availability combined efficiently |
| **Draft Formatting** | Generic prose reply regardless of category or email type | **Category-adaptive layout**: Action items with bullet points for tasks, bulleted time slots with timezones for scheduling, itemized references for billing, BLUF for executives |

---

## 4. Proposed Implementation Plan

### Step 1: Intelligent Content Extraction (`app/utils/text_utils.py` & `app/services/gmail_service.py`)
1. **Prefer `text/plain`**: When multipart contains both `text/plain` and `text/html`, extract `text/plain` exclusively.
2. **HTML-to-Text Parsing**: If only `text/html` is present, use an intelligent text parser (e.g., `BeautifulSoup` or `html2text`) that:
   - Removes `<script>`, `<style>`, `<head>`, `<noscript>`, and tracking pixel tags (`<img width="1" ...>`).
   - Converts headings, paragraphs, and list items into readable markdown/plain text.
   - Cleans excessive whitespace, non-breaking spaces (`&nbsp;`), and footer disclaimers.
3. **Auto-Detect HTML in `normalise_body`**: Check if `text` contains HTML tags (`<html`, `<body`, `<div`, `<table`) regardless of the `mime_type` argument.

### Step 2: Combine Clean Text with Search & Organizational Context
- Ensure the prompt presents:
  - **Clean Email Body** (essential content only).
  - **Historical Mail Context** (past correspondence from `gmail_search`).
  - **Org Context** (sender hierarchy, relationship).
  - **Calendar Availability** (free/busy slots if applicable).

### Step 3: Type-Aware Reply Formatting Directives (`app/pipeline/nodes.py`)
Dynamically append category-specific formatting instructions to `generate_enriched_draft`:
- **`Action Required`**: Structure with an executive summary, clear bulleted next steps, explicit owners, and target dates.
- **`Calendar/Scheduling`**: Propose 2–3 distinct time options in the recipient's timezone with a clear agenda outline.
- **`Receipts/Financial`**: State clear references (Invoice #, PO #, amount), approval status, and next accounting steps.
- **`Informational/Logs`**: Concise acknowledgment, noting key takeaways or confirmation of receipt.
- **`Executive / VIP`**: BLUF (Bottom Line Up Front), high signal-to-noise ratio, direct answers with no filler.

### Step 4: Verification & Benchmarking
1. **Token Measurement**: Compare token counts of raw HTML vs. cleaned text on benchmark emails.
2. **Unit Tests**:
   - Verify HTML tag stripping and text normalization in `tests/test_text_utils.py`.
   - Verify that multipart emails do not duplicate text and HTML.
   - Verify category-adaptive formatting in `tests/test_draft_generation.py`.
