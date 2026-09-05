# Changelog

All notable changes to the **Email Organizer** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
* Technical documentation suite: `README.md`, `ARCHITECTURE.md`, `SECURITY.md`, `CONTRIBUTING.md`, and `CHANGELOG.md`.
* Project licensing: Apache License 2.0.
* `.gitignore` configuration for compiled code, environment configurations, and OAuth credential locks.
* `.env.example` template config file.
* Licensing headers across all core Python source files.

---

## [2.0.0] - 2026-08-27

### Added
* **Safety Rules Engine (Layer 1)**: Deterministic pre-checks in `app/pipeline/safety_rules.py` targeting VIP email lists, trusted domains, and critical subjects.
* **Semantic Triage Engine (Layer 2)**: Shifted categorization to a LangGraph-managed StateGraph that validates classifications with a confidence index check (forcing `Needs Review` if confidence is under 85%).
* **Structured Classifications**: Implemented Pydantic output constraints (`EmailClassification`) return schemas for LLM category outputs.
* **Google Calendar Scheduling Check (Layer 3)**: Queries calendar free/busy slots during scheduling emails to inject availability strings directly into drafted replies.
* **Project Management Queue (Layer 4)**: Created `pm_action_queue` to hold tasks extracted from work items. Built endpoints to list, approve, reject, and execute tasks via a dynamic `JiraAdapter`.
* **SSE Model Context Protocol (MCP) Server**: Created `mcp_server/server.py` allowing external tool execution and data resource calls over Server-Sent Events.
* **Date-Wise Draft Sorting**: Gmail replies are automatically labeled with current date tags (e.g. `Drafts/2026-08-27`) to facilitate bulk reviews.

---

## [1.0.0] - 2026-08-20

### Added
* Ported CLI script logic into a structured **FastAPI** web application with routing controls.
* Installed **LangGraph** orchestrator to handle pipeline logic.
* Standardized database storage via SQLAlchemy, defining `users`, `emails`, and `email_tags` tables.
* Automated CSV audit logging of all pipeline decisions (`audit_log.csv`).
* Seeding scripts to inject mock database entries for testing.

---

## [0.1.0] - 2026-08-10

### Added
* Initial prototype CLI script (`main.py` at root) that fetches unread emails via the Google API Python client, calls Gemini API to draft a response, and prompts the terminal user to send it.
