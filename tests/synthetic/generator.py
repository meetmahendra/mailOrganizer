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
Procedural Synthetic Email Generator.

Synthesizes high-volume, parameterized, hyper-realistic enterprise email test cases
with authentic headers, multi-paragraph corporate bodies, thread turns, and exact ground truth.
Outputs to streaming JSONL files in tests/synthetic/generated_data/batches/.
"""
import os
import json
import random
import datetime
from typing import List, Dict, Any, Optional

from tests.synthetic.org_model import (
    load_org_roster,
    load_external_stakeholders,
    generate_corporate_signature,
    generate_client_signature,
    CONFIDENTIALITY_DISCLAIMERS,
)

_APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BATCHES_DIR = os.path.normpath(os.path.join(_APP_DIR, 'tests', 'synthetic', 'generated_data', 'batches'))


TEMPLATES = {
    "Action Required (High)": [
        {
            "subject": "[CRITICAL P0] {project} Production Latency Spike & Gateway Timeout",
            "body": "Hi {recipient_name},\n\nWe are experiencing elevated latency and error rates on {project}.\nP99 latency is currently at {latency}ms (SLA threshold is 500ms).\n\nError details:\n[ERROR] upstream request timeout on /v2/transactions (HTTP 504)\n\nCould you please immediately check the service connection pool and provide an update on the incident war-room bridge?\n\n{signature}",
            "urgency_range": [8, 10],
            "reply_necessary": True,
            "reason": "Production P0 incident requiring immediate triage and status update",
            "tags": ["incident", "engineering", "critical", "action-required", "high-priority"],
            "actions": [{"action": "keep_inbox"}, {"action": "apply_label", "label": "@Urgent"}, {"action": "star_thread"}, {"action": "create_draft_reply"}, {"action": "queue_pm_task"}],
        },
        {
            "subject": "[URGENT] {client_name} - Contract Signature & Approval Deadline Today",
            "body": "Hi {recipient_name},\n\nAttached is the revised Master Services Agreement (MSA) for {client_name}.\nCustomer procurement has agreed to our revised liability cap but requires execution by 5:00 PM EST today to avoid delaying the Q4 rollout.\n\nPlease review and execute via DocuSign as soon as possible.\n\n{signature}",
            "urgency_range": [8, 10],
            "reply_necessary": True,
            "reason": "Urgent contract execution deadline requiring same-day executive response",
            "tags": ["contract", "legal", "client", "action-required", "high-priority"],
            "actions": [{"action": "keep_inbox"}, {"action": "apply_label", "label": "@Urgent"}, {"action": "create_draft_reply"}],
        },
    ],
    "Action Required (Med/Low)": [
        {
            "subject": "Code Review Request: {project} Pull Request #{pr_number}",
            "body": "Hi {recipient_name},\n\nWhen you have some time today or tomorrow, could you please take a look at PR #{pr_number} on {project}?\n\nSummary of changes:\n- Refactored database query caching\n- Added integration tests for webhook retry logic\n\nLink: https://github.com/yourcompany/repo/pull/{pr_number}\n\n{signature}",
            "urgency_range": [4, 6],
            "reply_necessary": True,
            "reason": "Routine peer code review request requiring review and response",
            "tags": ["engineering", "update", "action-required", "medium-priority"],
            "actions": [{"action": "remove_inbox"}, {"action": "apply_label", "label": "@Action_Required"}, {"action": "create_draft_reply"}, {"action": "queue_pm_task"}],
        },
        {
            "subject": "Q3 Department Planning & OKR Review Input Needed",
            "body": "Hi Team,\n\nPlease review our draft Q3 OKRs and add your comments by the end of the week.\nWe will finalize the scorecard during our sprint retrospective next Monday.\n\n{signature}",
            "urgency_range": [4, 6],
            "reply_necessary": True,
            "reason": "Collaborative team input request with reasonable end-of-week deadline",
            "tags": ["management", "update", "action-required", "medium-priority"],
            "actions": [{"action": "remove_inbox"}, {"action": "apply_label", "label": "@Action_Required"}, {"action": "create_draft_reply"}],
        },
    ],
    "Calendar/Scheduling": [
        {
            "subject": "Reschedule: 1:1 Sync with {sender_name} / {recipient_name}",
            "body": "Hi {recipient_name},\n\nCan we reschedule our 1:1 sync from Thursday at 2 PM to Friday morning?\nI have a conflict with the {client_name} executive review.\n\nPlease let me know what times work on your calendar.\n\n{signature}",
            "urgency_range": [5, 7],
            "reply_necessary": True,
            "reason": "Meeting reschedule request expecting availability coordination",
            "tags": ["meeting", "schedule-meeting", "internal", "time-sensitive"],
            "actions": [{"action": "remove_inbox"}, {"action": "apply_label", "label": "@Scheduling"}, {"action": "create_draft_reply"}],
        },
        {
            "subject": "Architecture Deep-Dive: {project} Scaling Review",
            "body": "Hi {recipient_name},\n\nWe would like to schedule a 45-minute technical deep dive to review the multi-region topology for {project}.\nAre you available next Tuesday between 10 AM and 2 PM PST?\n\n{signature}",
            "urgency_range": [4, 6],
            "reply_necessary": True,
            "reason": "Meeting scheduling inquiry asking for attendee availability",
            "tags": ["meeting", "schedule-meeting", "engineering"],
            "actions": [{"action": "remove_inbox"}, {"action": "apply_label", "label": "@Scheduling"}, {"action": "create_draft_reply"}],
        },
    ],
    "Informational/Logs": [
        {
            "subject": "CI/CD Pipeline Build Report: {project} (Build #{build_number})",
            "body": "Pipeline Execution Status: SUCCESS\n\nRepository: yourcompany/{project}\nBranch: main\nCommit: 8f9b2c{build_number}\nDuration: 3m 42s\n\nTest Results:\n- Unit Tests: 842 passed, 0 failed\n- Lint & Security Scan: PASSED (0 high/critical vulnerabilities)\n- Artifact: registry.yourcompany.com/app:v{build_number}\n\nAutomated notification from CI/CD Worker.",
            "urgency_range": [1, 3],
            "reply_necessary": False,
            "reason": "Automated CI/CD build log; informational only",
            "tags": ["update", "engineering", "infrastructure", "automated", "no-action"],
            "actions": [{"action": "remove_inbox"}, {"action": "apply_label", "label": "Log/Updates"}, {"action": "mark_as_read"}],
        },
        {
            "subject": "Weekly Engineering Operations Digest & Changelog",
            "body": "Here is the weekly changelog for the engineering organization:\n\n1. Completed database index optimization for payments\n2. Deployed multi-AZ failover automation in staging\n3. Onboarded 2 new engineers to the Platform team\n\nHave a great weekend everyone!\n\n{signature}",
            "urgency_range": [1, 3],
            "reply_necessary": False,
            "reason": "Company informational update / weekly status report",
            "tags": ["update", "announcement", "internal", "informational", "no-action"],
            "actions": [{"action": "remove_inbox"}, {"action": "apply_label", "label": "Log/Updates"}, {"action": "mark_as_read"}],
        },
    ],
    "Receipts/Financial": [
        {
            "subject": "Invoice #{inv_number} from Amazon Web Services for August 2026",
            "body": "Amazon Web Services Billing Notification\n\nAccount: 8821-9920-1102\nBilling Period: Aug 01, 2026 - Aug 31, 2026\nTotal Amount Due: ${amount:,.2f} USD\nPayment Method: Corporate Credit Card (**8821)\n\nYour PDF tax invoice is available in the AWS Billing & Cost Management console.\n\nThank you for using Amazon Web Services.",
            "urgency_range": [2, 4],
            "reply_necessary": False,
            "reason": "Automated monthly cloud infrastructure billing statement and receipt",
            "tags": ["invoice", "payment", "finance", "vendor", "informational"],
            "actions": [{"action": "remove_inbox"}, {"action": "apply_label", "label": "Finance/Receipts"}, {"action": "mark_as_read"}, {"action": "apply_label", "label": "@Expense_Review"}],
        },
        {
            "subject": "Transaction Alert for Corporate Card ending in 4102",
            "body": "Bank Transaction Alert:\n\nA purchase of ${amount:,.2f} at {vendor_name} was authorized on 2026-08-31.\nCard: Platinum Corporate Visa (**4102)\nLocation: San Francisco, CA\n\nIf you did not authorize this charge, please contact corporate card support immediately.",
            "urgency_range": [2, 4],
            "reply_necessary": False,
            "reason": "Automated banking transaction confirmation alert",
            "tags": ["transaction", "bank", "credit-card", "finance", "automated"],
            "actions": [{"action": "remove_inbox"}, {"action": "apply_label", "label": "Finance/Receipts"}, {"action": "mark_as_read"}, {"action": "apply_label", "label": "@Expense_Review"}],
        },
    ],
    "Promotions/Marketing": [
        {
            "subject": "Limited Time Offer: 35% Off Cloud Observability Subscriptions",
            "body": "Unlock advanced distributed tracing and AI anomaly detection for your infrastructure.\nSign up before the end of the month and save 35% on enterprise annual plans.\n\nExplore plans: https://promo.cloud-insights.io/special-offer\n\nTo manage your email preferences or unsubscribe, click here.",
            "urgency_range": [1, 2],
            "reply_necessary": False,
            "reason": "Standard cold outreach marketing promotion for SaaS software",
            "tags": ["marketing", "announcement", "external", "low-priority", "no-action"],
            "actions": [{"action": "remove_inbox"}, {"action": "safe_archive", "label": "_LLM/Promotions"}, {"action": "mark_as_read"}],
        },
    ],
    "Spam/Trash": [
        {
            "subject": "URGENT: Your mailbox is full! Verify credentials to prevent deactivation",
            "body": "Dear User,\n\nYour mailbox storage quota has exceeded 99.8%.\nYou will not be able to send or receive emails unless you verify your password immediately.\n\nClick here to restore account: http://fake-login-verify-account.com/auth\n\nHelpdesk Administrator",
            "urgency_range": [1, 3],
            "reply_necessary": False,
            "reason": "Obvious phishing and credential harvesting attempt; safe archive to spam",
            "tags": ["security", "external", "no-action"],
            "actions": [{"action": "safe_archive", "label": "_LLM/Suspected_Spam"}, {"action": "mark_as_read"}],
        },
    ],
    "System Alert": [
        {
            "subject": "[SECURITY ALERT] Inactive OAuth 2.0 Credentials Deletion Notice",
            "body": "Google Cloud Developer Notification:\n\nWe identified inactive OAuth 2.0 client IDs in project 'techglobal-prod-8821' that have not made API requests in the past 180 days.\nPursuant to our security policy, these clients will be automatically disabled on Sept 30, 2026 unless verified in the GCP Console.\n\nAction required: Review OAuth client IDs in Cloud Console.\nAutomated notification; do not reply to this email.",
            "urgency_range": [6, 8],
            "reply_necessary": False,
            "reason": "Automated security alert from platform requiring administrative review",
            "tags": ["alert", "security", "infrastructure", "engineering", "automated"],
            "actions": [{"action": "keep_inbox"}, {"action": "apply_label", "label": "@System_Alert"}, {"action": "create_user_task"}],
        },
    ],
}


PROJECTS = ["Project Apollo", "Project Sentinel", "Project Titan", "Project Nexus"]
CLIENTS = ["Apex Global Financial", "Starlight Enterprise Systems", "Acme International"]
VENDORS = ["Amazon Web Services", "Datadog", "Stripe", "Snowflake", "GitHub", "Atlassian"]


def generate_synthetic_case(case_idx: int) -> Dict[str, Any]:
    """Generate a single realistic synthetic email test case."""
    employees = load_org_roster()
    stakeholders = load_external_stakeholders()
    categories = list(TEMPLATES.keys())
    
    # Weight categories for realistic corporate distribution
    weights = [0.15, 0.25, 0.15, 0.15, 0.15, 0.08, 0.04, 0.03]
    category = random.choices(categories, weights=weights)[0]
    tpl = random.choice(TEMPLATES[category])

    # Select sender and recipient
    if employees and len(employees) >= 2:
        sender_emp = random.choice(employees)
        recipient_emp = random.choice([e for e in employees if e != sender_emp] or employees)
    else:
        sender_emp = {"name": "Marcus Vance", "email": "marcus.vance@yourcompany.com", "title": "CTO", "department": "Executive", "is_vip": True}
        recipient_emp = {"name": "Arjun Mehta", "email": "arjun.mehta@yourcompany.com", "title": "Tech Lead", "department": "Engineering", "is_vip": False}

    project = random.choice(PROJECTS)
    client = random.choice(CLIENTS)
    vendor = random.choice(VENDORS)
    sig = generate_corporate_signature(sender_emp["name"], sender_emp["title"], sender_emp["department"], sender_emp["email"])

    # Substitute variables
    subj = tpl["subject"].format(
        project=project,
        client_name=client,
        pr_number=random.randint(100, 999),
        sender_name=sender_emp["name"],
        recipient_name=recipient_emp["name"],
        build_number=random.randint(1000, 9999),
        inv_number=random.randint(10000, 99999),
    )
    body = tpl["body"].format(
        recipient_name=recipient_emp["name"].split()[0],
        project=project,
        client_name=client,
        latency=random.randint(1500, 4200),
        pr_number=random.randint(100, 999),
        sender_name=sender_emp["name"],
        build_number=random.randint(1000, 9999),
        inv_number=random.randint(10000, 99999),
        amount=random.uniform(250.0, 48500.0),
        vendor_name=vendor,
        signature=sig,
    )

    is_no_reply = category in ("Informational/Logs", "Receipts/Financial", "Promotions/Marketing", "System Alert") and "Alert" in subj or "CI/CD" in subj or "Invoice" in subj
    sender_email = f"no-reply@{vendor.lower().replace(' ', '')}.com" if is_no_reply else sender_emp["email"]
    sender_header = f"{vendor} Automated Billing <{sender_email}>" if is_no_reply else f"{sender_emp['name']} <{sender_email}>"

    is_vip = sender_emp.get("is_vip", False) and not is_no_reply
    has_critical = "CRITICAL" in subj.upper() or "P0" in subj.upper() or "URGENT" in subj.upper()

    return {
        "id": f"GEN-SYN-{case_idx:05d}",
        "suite": "procedural_synthetic",
        "domain": sender_emp.get("department", "Enterprise"),
        "title": f"Synthetic: {subj[:60]}",
        "description": f"Procedurally synthesized email for {category}",
        "email": {
            "gmail_id": f"gen_msg_{case_idx:05d}",
            "thread_id": f"gen_thd_{case_idx:05d}",
            "message_id_header": f"<20260831.gen.{case_idx:05d}@yourcompany.com>",
            "headers": {
                "Date": "Mon, 31 Aug 2026 12:00:00 -0700",
                "From": sender_header,
                "To": f"{recipient_emp['name']} <{recipient_emp['email']}>",
                "Subject": subj,
                "X-Priority": "1" if tpl["urgency_range"][0] >= 8 else "3",
                "Authentication-Results": "spf=pass; dkim=pass"
            },
            "sender": sender_header,
            "to": f"{recipient_emp['name']} <{recipient_emp['email']}>",
            "subject": subj,
            "snippet": body[:140].replace('\n', ' '),
            "body": body,
            "thread_history": []
        },
        "expected": {
            "category": category,
            "acceptable_categories": [category],
            "urgency_score_range": tpl["urgency_range"],
            "is_reply_necessary": tpl["reply_necessary"] and not is_no_reply,
            "reply_necessity_reason": tpl["reason"],
            "is_no_reply": is_no_reply,
            "is_vip": is_vip,
            "has_critical_subject": has_critical,
            "required_actions": [{"action": "apply_label", "label": "@VIP"}] if is_vip else [],
            "forbidden_actions": [{"action": "remove_inbox"}, {"action": "safe_archive"}] if is_vip else [],
            "expected_tags_contains": tpl["tags"],
            "should_trigger_calendar": category == "Calendar/Scheduling",
            "should_queue_pm": category.startswith("Action Required")
        }
    }


def generate_batch(count: int = 1000, output_path: Optional[str] = None) -> str:
    """
    Generate a high-volume batch of realistic synthetic emails and write to a JSONL file.
    """
    os.makedirs(_BATCHES_DIR, exist_ok=True)
    if not output_path:
        output_path = os.path.join(_BATCHES_DIR, f"synthetic_batch_{count}.jsonl")

    print(f"[generator] Procedurally generating {count:,} realistic enterprise emails...")
    with open(output_path, 'w', encoding='utf-8') as f:
        for idx in range(1, count + 1):
            case = generate_synthetic_case(idx)
            f.write(json.dumps(case) + "\n")

    print(f"[generator] Successfully saved {count:,} synthetic test cases to disk: {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate scalable synthetic email datasets on disk")
    parser.add_argument("--count", type=int, default=1000, help="Number of synthetic emails to generate (default: 1000)")
    parser.add_argument("--output", type=str, default=None, help="Custom output JSONL file path")
    args = parser.parse_args()
    generate_batch(count=args.count, output_path=args.output)
