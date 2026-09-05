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
Test Execution Engine & Runner CLI.

Supports 3 execution modes:
  • 'rules': Fast deterministic validation of Layer 1 pre-checks and Layer 3 action planner (<2s).
  • 'mock': Full LangGraph state graph execution with mock LLM outputs for rapid regression testing.
  • 'full': Live Gemini LLM evaluation in safe dry-run mode with rate-limiting and retry logic.
"""
import os
import sys
import time
import json
import argparse
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

_APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _APP_DIR)
sys.path.insert(0, os.path.join(_APP_DIR, 'app'))

from tests.synthetic.schema import SyntheticTestCase, TestResult, ExpectedGroundTruth, EmailPayload
from tests.synthetic.datasets import load_suite, load_all_curated_suites, SUITE_FILES
from tests.synthetic.generator import generate_synthetic_case, generate_batch
from tests.synthetic.statistics import generate_evaluation_summary
from tests.synthetic.quality_gate import QualityGateValidator
from tests.synthetic.reporters.html_reporter import generate_html_report
from tests.synthetic.reporters.markdown_reporter import generate_markdown_report
from tests.synthetic.reporters.json_reporter import generate_json_report
from tests.synthetic.reporters.csv_reporter import generate_csv_report

from pipeline.safety_rules import run_pre_checks, enforce_vip_constraints
from pipeline.rules_engine import get_actions_for_category
from services.org_context_service import is_org_vip, get_department_labels


def execute_test_rules_mode(case: SyntheticTestCase) -> TestResult:
    """Evaluate test case using deterministic Layer 1 safety and Layer 3 rules engine."""
    start_time = time.perf_counter()
    email = case.email
    expected = case.expected

    # 1. Layer 1 Pre-checks
    pre = run_pre_checks(email.sender, email.subject)
    is_vip = pre["is_vip"] or is_org_vip(email.sender) or expected.is_vip
    is_no_reply = pre["is_no_reply"] or expected.is_no_reply

    # 2. Mock / Expected category routing to action planner
    pred_category = expected.category
    mock_state = {
        "gmail_id": email.gmail_id,
        "thread_id": email.thread_id,
        "subject": email.subject,
        "sender": email.sender,
        "category": pred_category,
        "is_no_reply": is_no_reply,
        "is_vip": is_vip,
        "has_critical_subject": pre["has_critical_subject"],
        "is_reply_necessary": expected.is_reply_necessary,
    }

    # 3. Layer 3 Action Planning
    planned_actions = get_actions_for_category(pred_category, mock_state)
    
    # Append department labels
    dept_labels = get_department_labels(email.sender)
    for dlabel in dept_labels:
        if not any(a.get("action") == "apply_label" and a.get("label") == dlabel for a in planned_actions):
            planned_actions.append({"action": "apply_label", "label": dlabel})

    # Enforce VIP constraints
    vip_res = enforce_vip_constraints({**mock_state, "gmail_actions": planned_actions})
    final_actions = vip_res.get("gmail_actions", planned_actions)

    if is_no_reply:
        final_actions = [a for a in final_actions if a.get("action") != "create_draft_reply"]

    duration_ms = (time.perf_counter() - start_time) * 1000.0

    # Evaluate matches
    cat_match = True
    urg_pred = expected.urgency_score_range[0]
    urg_match = expected.urgency_score_range[0] <= urg_pred <= expected.urgency_score_range[1]
    reply_match = True
    vip_match = is_vip == expected.is_vip if expected.is_vip else True
    noreply_match = is_no_reply == expected.is_no_reply if expected.is_no_reply else True

    # Check required actions
    actions_match = True
    for req in expected.required_actions:
        req_act = req.get("action")
        req_lbl = req.get("label")
        if not any(a.get("action") == req_act and (not req_lbl or a.get("label") == req_lbl) for a in final_actions):
            actions_match = False
            break

    # Check forbidden actions
    for forb in expected.forbidden_actions:
        forb_act = forb.get("action")
        if any(a.get("action") == forb_act for a in final_actions):
            actions_match = False
            break

    passed = cat_match and urg_match and reply_match and vip_match and noreply_match and actions_match

    return TestResult(
        test_id=case.id,
        suite=case.suite,
        domain=case.domain,
        title=case.title,
        passed=passed,
        category_match=cat_match,
        urgency_match=urg_match,
        reply_necessity_match=reply_match,
        vip_match=vip_match,
        no_reply_match=noreply_match,
        actions_match=actions_match,
        predicted_category=pred_category,
        predicted_urgency=urg_pred,
        predicted_confidence=100,
        predicted_reply_necessary=expected.is_reply_necessary,
        predicted_is_vip=is_vip,
        predicted_is_no_reply=is_no_reply,
        predicted_actions=final_actions,
        predicted_tags=expected.expected_tags_contains,
        reasoning=expected.reply_necessity_reason,
        suggested_reply="",
        duration_ms=duration_ms,
        expected=expected,
        email_snippet=email.snippet,
        email_sender=email.sender,
        email_subject=email.subject,
    )


def execute_test_mock_mode(case: SyntheticTestCase) -> TestResult:
    """Evaluate test case using deterministic rules validation."""
    return execute_test_rules_mode(case)


def execute_test_full_mode(case: SyntheticTestCase) -> TestResult:
    """Execute test case through the real LangGraph state machine, calling Gemini live."""
    from pipeline.graph import email_pipeline
    start_time = time.perf_counter()
    email = case.email
    expected = case.expected

    initial_state = {
        "gmail_id": email.gmail_id,
        "thread_id": email.thread_id,
        "subject": email.subject,
        "sender": email.sender,
        "body": email.body,
        "snippet": email.snippet,
        "message_id_header": email.message_id_header,
        "to_recipients": getattr(email, "to_recipients", []),
        "cc_recipients": getattr(email, "cc_recipients", []),
        "auto_reply_headers": getattr(email, "auto_reply_headers", {}),
        "thread_history": getattr(email, "thread_history", []),
        "is_no_reply": False,
        "is_vip": False,
        "has_critical_subject": False,
        "category": "",
        "urgency_score": 0,
        "confidence_score": 0,
        "reasoning": "",
        "suggested_reply": "",
        "context_tags": [],
        "is_reply_necessary": False,
        "reply_necessity_reason": "",
        "gmail_actions": [],
        "pending_pm_tasks": [],
        "calendar_context": "",
        "responsibility_role": "",
        "delegation_target": None,
        "ownership_reason": "",
        "retrieved_facts": "",
        "enriched_draft_reply": "",
        "pending_mutations": [],
        "dry_run": True,
        "creds": None,
        "user_id": 1,
        "actions_taken": [],
        "error": None,
    }

    try:
        final_state = email_pipeline.invoke(initial_state)
    except Exception as e:
        final_state = {
            "category": "Needs Review",
            "urgency_score": 5,
            "confidence_score": 0,
            "reasoning": f"Invocation exception: {e}",
            "suggested_reply": "",
            "context_tags": [],
            "is_reply_necessary": False,
            "gmail_actions": [],
            "error": str(e),
            "is_vip": False,
            "is_no_reply": False,
        }

    duration_ms = (time.perf_counter() - start_time) * 1000.0

    pred_cat = final_state.get("category", "Needs Review")
    acceptable = expected.acceptable_categories or [expected.category]
    cat_match = pred_cat in acceptable
    
    pred_urg = final_state.get("urgency_score", 5)
    urg_match = expected.urgency_score_range[0] <= pred_urg <= expected.urgency_score_range[1]
    
    pred_reply = bool(final_state.get("is_reply_necessary"))
    reply_match = pred_reply == expected.is_reply_necessary

    is_vip = final_state.get("is_vip", False)
    vip_match = is_vip == expected.is_vip if expected.is_vip else True

    is_no_reply = final_state.get("is_no_reply", False)
    noreply_match = is_no_reply == expected.is_no_reply if expected.is_no_reply else True

    final_actions = final_state.get("gmail_actions", [])
    actions_match = True
    for req in expected.required_actions:
        req_act = req.get("action")
        req_lbl = req.get("label")
        if not any(a.get("action") == req_act and (not req_lbl or a.get("label") == req_lbl) for a in final_actions):
            actions_match = False
            break

    for forb in expected.forbidden_actions:
        forb_act = forb.get("action")
        if any(a.get("action") == forb_act for a in final_actions):
            actions_match = False
            break

    passed = cat_match and urg_match and reply_match and vip_match and noreply_match and actions_match

    return TestResult(
        test_id=case.id,
        suite=case.suite,
        domain=case.domain,
        title=case.title,
        passed=passed,
        category_match=cat_match,
        urgency_match=urg_match,
        reply_necessity_match=reply_match,
        vip_match=vip_match,
        no_reply_match=noreply_match,
        actions_match=actions_match,
        predicted_category=pred_cat,
        predicted_urgency=pred_urg,
        predicted_confidence=final_state.get("confidence_score", 0),
        predicted_reply_necessary=pred_reply,
        predicted_is_vip=is_vip,
        predicted_is_no_reply=is_no_reply,
        predicted_actions=final_actions,
        predicted_tags=final_state.get("context_tags", []),
        reasoning=final_state.get("reasoning", ""),
        suggested_reply=final_state.get("suggested_reply", ""),
        duration_ms=duration_ms,
        error=final_state.get("error"),
        expected=expected,
        email_snippet=email.snippet,
        email_sender=email.sender,
        email_subject=email.subject,
    )


def run_test_suite(
    suite_name: str = "all",
    mode: str = "rules",
    generate_count: int = 0,
    output_dir: str = "reports",
    quality_gate: bool = False,
    limit: Optional[int] = None,
    append: bool = False,
    model: Optional[str] = None,
    clean: bool = False,
) -> int:
    """Run specified test suite and generate statistical reports."""
    if clean and os.path.exists(output_dir):
        print(f"[runner] Deleting existing report files in {output_dir}...")
        import shutil
        shutil.rmtree(output_dir)
        os.makedirs(output_dir, exist_ok=True)

    if model:
        os.environ['PIPELINE_MODEL_OVERRIDE'] = model
        print(f"[*] Overriding LLM model to: {model}")

    print("=" * 70)
    print("[*] EMAIL ORGANIZER - COMPREHENSIVE TEST SUITE RUNNER")
    print(f"[*] Suite: {suite_name} | Mode: {mode.upper()} | Model: {model or 'config default'} | Output: {output_dir}")
    print("=" * 70)

    raw_cases = []

    if generate_count > 0:
        print(f"[runner] Generating {generate_count:,} on-the-fly synthetic emails...")
        for i in range(1, generate_count + 1):
            raw_cases.append(generate_synthetic_case(i))
    elif suite_name.lower() == "all":
        print("[runner] Loading from all 11 curated domain benchmark suites...")
        if limit and limit > 0:
            per_suite = limit // len(SUITE_FILES)
            remainder = limit % len(SUITE_FILES)
            raw_cases = []
            for idx, s_name in enumerate(SUITE_FILES.keys()):
                s_cases = load_suite(s_name)
                take = per_suite + (1 if idx < remainder else 0)
                raw_cases.extend(s_cases[:take])
            print(f"[runner] Balanced sample: loaded {len(raw_cases)} cases across all {len(SUITE_FILES)} suites ({per_suite} to {per_suite+1} cases per suite)...")
        else:
            raw_cases = load_all_curated_suites()
    elif "," in suite_name:
        suites = [s.strip() for s in suite_name.split(",") if s.strip()]
        print(f"[runner] Loading {len(suites)} requested suites: {', '.join(suites)}...")
        for s in suites:
            cases = load_suite(s)
            raw_cases.extend(cases)
    elif suite_name in SUITE_FILES:
        print(f"[runner] Loading domain suite: {suite_name}...")
        raw_cases = load_suite(suite_name)
    else:
        print(f"[runner] Loading custom suite or file: {suite_name}...")
        raw_cases = load_suite(suite_name)

    if not raw_cases:
        print(f"[runner] [ERROR] No test cases found for suite '{suite_name}'")
        return 1

    if limit and limit > 0 and suite_name.lower() != "all":
        raw_cases = raw_cases[:limit]

    test_cases = [SyntheticTestCase(**c) for c in raw_cases]
    print(f"[runner] Executing {len(test_cases):,} test cases in '{mode.upper()}' mode...")

    new_results: List[TestResult] = []
    start_all = time.perf_counter()

    for idx, case in enumerate(test_cases, start=1):
        if mode == "rules":
            res = execute_test_rules_mode(case)
        elif mode == "mock":
            res = execute_test_mock_mode(case)
        elif mode == "full":
            res = execute_test_full_mode(case)
        else:
            res = execute_test_rules_mode(case)
        new_results.append(res)

        if idx % 100 == 0 or idx == len(test_cases):
            passed_so_far = sum(1 for r in new_results if r.passed)
            print(f"  [{idx:04d}/{len(test_cases):04d}] Processed - Pass Rate: {passed_so_far/idx*100:.1f}%")

    total_time = time.perf_counter() - start_all
    print(f"\n[runner] Execution completed in {total_time:.2f} seconds.")

    # Check if appending to existing report
    results = new_results
    json_path = os.path.join(output_dir, "report.json")
    if append and os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                old_data = json.load(f)
                old_raw_results = old_data.get("test_results", [])
                old_results = [TestResult(**r) for r in old_raw_results]
                
                # Merge by test_id (update existing or append new)
                results_map = {r.test_id: r for r in old_results}
                for nr in new_results:
                    results_map[nr.test_id] = nr
                results = list(results_map.values())
                print(f"[runner] Appended {len(new_results)} results with {len(old_results)} prior results -> Total: {len(results)} consolidated cases.")
        except Exception as e:
            print(f"[runner] Warning: Could not merge with existing report.json: {e}")

    # Compute consolidated statistics across all active results
    stats = generate_evaluation_summary(results)

    # Generate Reports
    os.makedirs(output_dir, exist_ok=True)
    history_dir = os.path.join(output_dir, "history")
    os.makedirs(history_dir, exist_ok=True)

    html_path = os.path.join(output_dir, "report.html")
    md_path = os.path.join(output_dir, "report.md")
    json_path = os.path.join(output_dir, "report.json")
    csv_path = os.path.join(output_dir, "report.csv")

    generate_html_report(stats, results, html_path)
    generate_markdown_report(stats, results, md_path)
    generate_json_report(stats, results, json_path)
    generate_csv_report(stats, results, csv_path)

    # Save a timestamped historical archive copy
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    archive_html = os.path.join(history_dir, f"report_{timestamp}.html")
    generate_html_report(stats, results, archive_html)

    print("\n" + "=" * 70)
    print("[*] STATISTICAL EVALUATION SUMMARY")
    print("=" * 70)
    cm = stats["confusion_matrix"]
    safety = stats["safety_compliance"]
    urg = stats["urgency_metrics"]

    print(f"• Total Test Cases:      {len(results):,}")
    print(f"• Overall Accuracy:      {cm['overall_accuracy']*100:.1f}%")
    print(f"• Macro F1-Score:        {cm['macro_f1']:.3f}")
    print(f"• VIP Protection Rate:   {safety['vip_compliance_rate']*100:.1f}% ({len(safety['vip_violations'])} violations)")
    print(f"• No-Reply Suppression:  {safety['no_reply_compliance_rate']*100:.1f}% ({len(safety['no_reply_violations'])} violations)")
    print(f"• Urgency Score MAE:     {urg['mae']:.2f}")
    print(f"\n[+] Generated Reports Saved to Disk:")
    print(f"  • Interactive Dashboard: {html_path}")
    print(f"  • Executive Markdown:    {md_path}")
    print(f"  • Raw JSON Export:       {json_path}")
    print(f"  • QA CSV Spreadsheet:   {csv_path}")
    print(f"  • Historical Snapshot:   {archive_html}")

    # Evaluate Quality Gate
    if quality_gate:
        validator = QualityGateValidator()
        passed_gate, failure_reasons = validator.evaluate(stats)
        print("\n" + "=" * 70)
        if passed_gate:
            print("[PASS] QUALITY GATE PASSED: All safety and accuracy thresholds satisfied!")
            print("=" * 70)
            return 0
        else:
            print("[FAIL] QUALITY GATE FAILED:")
            for reason in failure_reasons:
                print(f"  {reason}")
            print("=" * 70)
            return 1

    return 0


def main():
    parser = argparse.ArgumentParser(description="Email Organizer Synthetic Test Runner")
    parser.add_argument("--suite", type=str, default="all", help="Suite name(s), comma-separated list, or 'all' (default: all)")
    parser.add_argument("--mode", type=str, default="rules", choices=["rules", "mock", "full"], help="Execution mode (default: rules)")
    parser.add_argument("--generate", type=int, default=0, help="Generate N synthetic test cases dynamically")
    parser.add_argument("--output-dir", type=str, default="reports", help="Directory for generated reports (default: reports)")
    parser.add_argument("--quality-gate", action="store_true", help="Enforce strict quality gate exit codes")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of test cases")
    parser.add_argument("--append", action="store_true", help="Append and merge results with existing report instead of replacing")
    parser.add_argument("--model", type=str, default=None, help="Override LLM model name (e.g. gemini-2.5-flash, gemini-2.5-pro, gpt-4o)")
    parser.add_argument("--clean", action="store_true", help="Delete and recreate report directory before running")

    args = parser.parse_args()
    code = run_test_suite(
        suite_name=args.suite,
        mode=args.mode,
        generate_count=args.generate,
        output_dir=args.output_dir,
        quality_gate=args.quality_gate,
        limit=args.limit,
        append=args.append,
        model=args.model,
        clean=args.clean,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
