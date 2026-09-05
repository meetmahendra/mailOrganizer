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
Config Doctor — Enterprise Configuration & Connector Diagnostics CLI.

Run this tool anytime to verify:
  1. YAML configuration syntax and Pydantic schema validity
  2. Environment variable availability (tokens, keys, secrets)
  3. Live reachability and health of external RAG endpoints, MCP servers, and Calendar

Usage:
  python -m app.config_doctor
  or
  python app/config_doctor.py
"""
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

# Windows terminal encoding safeguard
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Ensure project root is in sys.path
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_APP_DIR)
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _APP_DIR)

from config.schemas import validate_all_configs
from connectors.connector_manager import get_connector_manager


def run_diagnostics() -> int:
    print("=" * 72)
    print("[*] MAIL ORGANIZER — ENTERPRISE CONFIGURATION & CONNECTOR DOCTOR")
    print("=" * 72)

    total_checks = 0
    passed_checks = 0
    warnings = []
    errors = []

    # ── Step 1: Validate Configuration Schemas ───────────────────────────────
    print("\n[*] Checking configuration schemas and syntax...")
    try:
        validated = validate_all_configs()
        total_checks += 3
        passed_checks += 3
        print(f"  [+] config/connectors.yaml ......................... [OK: Valid Schema]")
        print(f"  [+] config/delegation_policies.yaml ................ [OK: Valid Schema]")
        print(f"  [+] config/user_persona.yaml ....................... [OK: Valid Schema ({validated['persona'].name})]")
    except Exception as e:
        print(f"  [-] Configuration validation failed: {e}")
        errors.append(f"Config schema error: {e}")
        return 1

    # ── Step 2: Check Environment Variables ──────────────────────────────────
    print("\n[*] Checking environment variables & API tokens...")
    env_keys = [
        ("GEMINI_API_KEY", True, "Required for LLM classification & draft generation"),
        ("HR_RAG_TOKEN", False, "Used by HR Policies RAG endpoint"),
        ("ENG_RAG_TOKEN", False, "Used by Engineering Docs RAG endpoint"),
        ("LEGAL_RAG_TOKEN", False, "Used by Legal Contracts RAG endpoint"),
        ("JIRA_URL", False, "Used by Jira MCP server"),
        ("JIRA_API_TOKEN", False, "Used by Jira MCP server"),
    ]

    for key, required, desc in env_keys:
        total_checks += 1
        val = os.getenv(key)
        if val:
            passed_checks += 1
            masked = val[:4] + "..." + val[-3:] if len(val) > 8 else "***"
            print(f"  [+] {key:<20} ......................... [OK: Set ({masked})]")
        else:
            if required:
                errors.append(f"Missing required environment variable: {key} ({desc})")
                print(f"  [-] {key:<20} ......................... [MISSING: Required]")
            else:
                warnings.append(f"Optional token {key} not set ({desc})")
                print(f"  [!] {key:<20} ......................... [UNSET: Optional]")

    # ── Step 3: Test Connector Availability ──────────────────────────────────
    print("\n[*] Checking registered knowledge connectors...")
    try:
        manager = get_connector_manager()
        print(f"  [i] Total active connectors registered: {len(manager.connectors)}")

        for cid, connector in manager.connectors.items():
            total_checks += 1
            avail = connector.is_available()
            if avail:
                passed_checks += 1
                print(f"  [+] Connector: {cid:<22} ................. [OK: Available]")
            else:
                warnings.append(f"Connector '{cid}' is registered but unavailable.")
                print(f"  [!] Connector: {cid:<22} ................. [UNAVAILABLE]")

    except Exception as e:
        errors.append(f"Connector manager initialization failed: {e}")
        print(f"  [-] Failed to initialize ConnectorManager: {e}")

    # ── Step 4: Test Deterministic Routing Rules ─────────────────────────────
    print("\n[*] Testing deterministic tag-to-connector routing...")
    test_tag_queries = [
        (["meeting", "reschedule"], ["calendar"]),
        (["invoice", "wire-transfer"], ["erp_financial", "gmail_search"]),
        (["incident", "sre", "outage"], ["engineering_docs_rag", "jira_mcp"]),
        (["legal", "compliance", "nda"], ["legal_contracts_rag"]),
    ]

    for tags, expected_any in test_tag_queries:
        total_checks += 1
        resolved = manager.resolve_connectors_for_tags(tags)
        overlap = set(resolved).intersection(set(expected_any))
        if overlap:
            passed_checks += 1
            print(f"  [+] Tags {str(tags):<35} -> {list(overlap)}")
        else:
            warnings.append(f"Tag query {tags} did not resolve to expected connectors: {expected_any}")
            print(f"  [!] Tags {str(tags):<35} -> None resolved")

    # ── Summary & Remediation ────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print(" [*] DIAGNOSTICS SUMMARY")
    print("=" * 72)
    print(f"• Total Checks:  {total_checks}")
    print(f"• Passed Checks: {passed_checks}/{total_checks}")
    print(f"• Warnings:      {len(warnings)}")
    print(f"• Errors:        {len(errors)}")

    if warnings:
        print("\n[!] Recommended Actions (Warnings):")
        for w in warnings:
            print(f"  • {w}")

    if errors:
        print("\n[-] Critical Errors to Resolve:")
        for err in errors:
            print(f"  • {err}")
        print("\n[!] Result: DIAGNOSTICS FAILED — Please resolve critical errors above.")
        return 1

    print("\n[+] Result: ALL SYSTEMS OPERATIONAL! MailOrganizer is ready for live use.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(run_diagnostics())
