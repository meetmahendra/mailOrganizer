# Email Organizer

Intelligent inbox triage and routing automation engine powered by **LangGraph**, **FastAPI**, and **Google Gemini LLMs**.

Email Organizer connects to your Gmail, automatically retrieves unread messages, analyzes their semantic intent, labels them, and drafts context-aware replies. It features a robust multi-layered safety architecture with deterministic overrides and a daily audit log to ensure critical client and system alerts are never lost or misclassified.

---

## 🌟 Key Features

* **Multi-Layered Safety Architecture**: Out-of-the-box deterministic rules (Layer 1) evaluate sender whitelists (VIP), domains, and critical subject keywords before AI processing.
* **Intelligent LLM Triage (Layer 2)**: Classifies emails into one of 9 canonical categories, calculates urgency scores (1–10), maps context tags across multiple dimensions, and determines if a reply is semantically necessary.
* **Confidence Guardrails**: Overrides LLM categories to `Needs Review` if confidence scores fall below 85%, ensuring ambiguous messages remain in the primary inbox.
* **Zero-Deletion Policy**: Legitimate emails are never deleted. Low-priority and marketing messages are safely archived to designated labels (e.g., `_LLM/Promotions`), keeping them searchable.
* **Google Calendar Integration**: Automatically checks your free/busy schedule to inject real availability into drafted scheduling replies.
* **Human-in-the-Loop Project Management**: Automatically identifies PM tasks from emails, queues them in SQLite, and exports them to adapters (like Jira) upon manual user approval.
* **Model Context Protocol (MCP) Server**: Exposes internal data, logs, task queues, and Gmail operations via an SSE-based MCP server interface for AI agents.

---

## 📂 Directory Structure

```text
d:/mailOrganizer/
├── app/                      # Main application package
│   ├── pipeline/             # LangGraph state machine, nodes, and safety engines
│   ├── routes/               # FastAPI controllers (auth, emails, search, digest)
│   ├── scripts/              # Migration, mock database seeding, and poll workers
│   ├── services/             # Integrations (Gmail, Calendar, LLM, PM adapter)
│   ├── utils/                # Text encoding normalization and string parsers
│   ├── database.py           # SQLAlchemy setup
│   ├── models.py             # Database models for Users, Emails, Tags, Logs
│   └── requirements.txt      # Application package dependencies
├── docs/                     # Technical documentation suite
│   ├── ARCHITECTURE.md       # Technical architecture specification
│   ├── SECURITY.md           # Security & compliance policy
│   ├── CONTRIBUTING.md       # Developer contribution guidelines
│   └── CHANGELOG.md          # Release version history log
├── config/                   # Config YAML files (LLM models, VIP rules, custom default rules)
├── mcp_server/               # Custom SSE-based MCP server
├── LICENSE                   # Apache License 2.0
├── .env.example              # Configuration variables template
├── main.py                   # Simple CLI utility script
├── requirements.txt          # Core dependencies
└── versionControll/          # Historical architecture design documents
```

---

## 📚 Technical Documentation

The comprehensive technical documentation is organized in the `docs` folder:
* 🏢 **[Architecture Specification](docs/ARCHITECTURE.md)**: Component diagrams, LangGraph execution node details, and database schema mappings.
* 🛡️ **[Security & Compliance Policy](docs/SECURITY.md)**: Data privacy, fail-safe rules, credential protection, and production hardening guidelines.
* 🤝 **[Developer Contribution Guidelines](docs/CONTRIBUTING.md)**: Style guides (PEP 8, docstrings), pull request workflows, and copyright header guidelines.
* 📋 **[Changelog](docs/CHANGELOG.md)**: Version history record from initial prototypes (V0) to current state machine (V2).

---

## ⚙️ Setup and Installation

### 1. Prerequisites
Ensure you have **Python 3.10+** installed.

### 2. Install Dependencies
Install the required packages for the core environment and the FastAPI application:
```bash
pip install -r requirements.txt
pip install -r app/requirements.txt
```

### 3. Environment Configuration
Copy the `.env.example` file to `.env`:
```bash
cp .env.example .env
```
Open `.env` and fill in your **Gemini API Key** (obtainable from [Google AI Studio](https://aistudio.google.com/)).

### 4. Enable Google Gmail and Calendar APIs
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project.
3. Enable the **Gmail API** and **Google Calendar API** for your project.
4. Set up the OAuth consent screen (choose User Type: **External**, and add your email as a test user).
5. Go to **Credentials**, click **Create Credentials** -> **OAuth client ID** (select Application Type: **Desktop app**).
6. Download the JSON credentials file and save it as `credentials.json` in the root directory: `d:\mailOrganizer\credentials.json` (also copy it to `d:\mailOrganizer\app\credentials.json` for local API routing).

---

## 🚀 Running the Application

### Option A: Local FastAPI Web Server & REST API
The REST API allows you to authenticate, trigger triages, and check daily digests via a web browser or API tool.
1. Run the database setup:
   ```bash
   python -m app.scripts.migrate_db
   ```
2. Start the FastAPI server:
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```
3. Open your browser and navigate to `http://localhost:8000/auth/login` to authenticate your Gmail account. This generates the `token.json` session file.
4. View the Swagger documentation at `http://localhost:8000/docs`.

### Option B: Background Poll Worker
To process incoming emails continuously in the background:
```bash
python -m app.scripts.poll_worker
```

### Option C: MCP Server
To expose the email organizer tools to an external AI agent or client (e.g. Cursor, Claude Desktop):
```bash
python -m mcp_server.server
```
The server starts on port `8001` and implements the **Model Context Protocol** SSE transport channel (`http://localhost:8001/sse`).

---

## 🛡️ License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.

**Copyright 2026 Mahendra GURAV**
