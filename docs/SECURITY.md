# Security & Compliance Policy

This document outlines the security architecture, data handling practices, safety guardrails, and vulnerability disclosure processes for the Email Organizer project to ensure audit readiness and build customer trust.

---

## 🛡️ Core Security Pillars

### 1. Data Isolation & Privacy
* **Local Processing & Storage**: All downloaded email metadata, subject lines, message bodies, and execution logs are stored locally in a SQLite database (`emails.db`). No email content is uploaded to third-party databases or remote indexers.
* **Transient API Usage**: Email content is sent to the configured LLM API (e.g., Google Gemini) solely for classification and draft generation. This data is processed transiently according to the API provider's data protection policies (e.g., Google AI Studio terms state that data sent to API endpoints is not used to train models for paid/commercial accounts).

### 2. Isolation of Credentials
* **Version Control Protection**: Credentials, authorization tokens, database files, and environment configurations are excluded from Git using `.gitignore`.
  * `.env` (API keys)
  * `credentials.json` (Google OAuth Client credentials)
  * `token.json` (User authorization/refresh tokens)
  * `emails.db` (Local data cache)
* **Token Encryption at Rest**: In production, the OAuth tokens stored in the `users` table's `credentials_json` column should be encrypted using standard symmetric encryption (e.g., AES-GCM via the Python cryptography library).

### 3. Multi-Layered Execution Safety (Fail-Safe Archiving)
* **Dry Run Mode (Shadow Mode)**: The system starts in dry-run mode by default (`DRY_RUN=true`). In this mode, no mutations (labeling, drafting, moving) occur on Gmail. Actions are logged exclusively to `audit_log.csv` and SQLite tables.
* **Deterministic Overrides**: Safe sender (VIP) and automated sender (no-reply) checks are written in Python code and executed BEFORE the LLM runs. VIP emails are marked high priority and are guaranteed to remain in the inbox, neutralizing potential LLM hallucinations.
* **Confidence Guardrails**: The LangGraph engine evaluates the LLM's classification confidence. If it is less than 85%, the category is automatically changed to `Needs Review` and the email remains in the `INBOX` under the `@Review_Needed` label.
* **Zero-Deletion Policy**: The default rules do not use destructive Gmail commands (`move_to_trash` or delete). Low-priority emails are archived to labeled folders (such as `_LLM/Promotions`), keeping them searchable.

---

## 🌐 Network and API Security

### CORS (Cross-Origin Resource Sharing)
* **Development Config**: The FastAPI application and MCP server currently configure CORS middleware with `allow_origins=["*"]`. This wildcard is acceptable for local development and local tool orchestration.
* **Production Hardening**: If deploying these services to a remote server, you MUST restrict the origins to specific authorized domain names:
  ```python
  # Example hardening in app/main.py and mcp_server/server.py
  app.add_middleware(
      CORSMiddleware,
      allow_origins=["https://your-secure-frontend.com"],
      allow_methods=["GET", "POST", "OPTIONS"],
      allow_headers=["Content-Type", "Authorization"],
  )
  ```

### API Key Rotation
Ensure that API keys (such as `GEMINI_API_KEY`) are regularly rotated (e.g. every 90 days) in the Google AI Studio console.

---

## 🔍 Vulnerability Disclosure & Audit Reporting

If you find a security vulnerability, please do not open a public issue. Report it directly to the author:

* **Contact Person**: Mahendra GURAV
* **Attribution & Copyright**: 2026 Mahendra GURAV
* **Patch Policy**: Critical vulnerability patches will be applied and documented in the [Changelog](CHANGELOG.md).
