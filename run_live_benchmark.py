#!/usr/bin/env python
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
High-Fidelity Live Benchmark Suite Runner CLI (Phase 7).

Evaluates the MailOrganizer pipeline across 60 authentic real-world business scenarios:
  - Multi-To and CC ownership & delegation accuracy
  - Fact-grounded draft reply generation (with anti-stalling guardrails)
  - Hard safety inviolability (zero OOO loops, zero VIP loss, sensitive legal lockdown)
  - External RAG, Calendar, and Outbound MCP connector enrichment

Usage:
  python run_live_benchmark.py                           # Run all 60 benchmark scenarios
  python run_live_benchmark.py --domain=fintech_banking  # Run specific domain suite
  python run_live_benchmark.py --limit=10                # Run first 10 scenarios
  python run_live_benchmark.py --quality-gate            # Enforce 80% pass & 100% safety threshold
  python run_live_benchmark.py --clean                   # Clean old reports before execution
"""
import os
import sys
import argparse
import time

# Windows terminal encoding safeguard
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "app"))

from tests.live_benchmark.live_evaluator import LiveBenchmarkEvaluator
from tests.live_benchmark.reporters.live_dashboard import LiveBenchmarkDashboardReporter


def parse_args():
    parser = argparse.ArgumentParser(
        description="MailOrganizer High-Fidelity Live Benchmark Runner"
    )
    parser.add_argument(
        "--domain",
        type=str,
        default=None,
        help="Filter by domain (e.g. ownership_delegation, fintech_banking, cloud_sre)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of test scenarios to execute",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="mock",
        choices=["mock", "live"],
        help="Execution mode: 'mock' (uses connector fixtures) or 'live'",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Optional model override (e.g. gemini-3.6-flash)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean previous benchmark report files before running",
    )
    parser.add_argument(
        "--quality-gate",
        action="store_true",
        help="Exit with non-zero status if safety < 100%% or pass rate < 80%%",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    reports_dir = os.path.join(_PROJECT_ROOT, "reports")
    html_out = os.path.join(reports_dir, "live_benchmark.html")
    json_out = os.path.join(reports_dir, "live_benchmark.json")

    if args.clean:
        for p in [html_out, json_out]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    if args.model:
        os.environ["PIPELINE_MODEL_OVERRIDE"] = args.model

    # In live mode, ensure the local mock RAG HTTP service is listening on port 8005
    if args.mode == "live":
        from tests.mock_rag_server import start_mock_rag_server
        server, _ = start_mock_rag_server(port=8005)
        if server:
            print("[*] Local Mock RAG HTTP Server started on http://127.0.0.1:8005")

    print("=" * 72)
    print("[*] MAIL ORGANIZER — HIGH-FIDELITY LIVE BENCHMARK SUITE")
    print(f"[*] Mode: {args.mode.upper()} | Filter: {args.domain or 'ALL'} | Limit: {args.limit or 'ALL'}")
    print("=" * 72)

    evaluator = LiveBenchmarkEvaluator()
    total_cases = len(evaluator.test_cases)
    print(f"[runner] Loaded {total_cases} benchmark scenarios from catalog.")
    print("[runner] Executing benchmark evaluation...\n")

    start_time = time.perf_counter()
    results = evaluator.run_all(
        domain_filter=args.domain,
        limit=args.limit,
        mode=args.mode,
    )
    elapsed = time.perf_counter() - start_time

    # Generate reports
    LiveBenchmarkDashboardReporter.generate_html_report(results, html_out)
    LiveBenchmarkDashboardReporter.export_json(results, json_out)

    # Compute metrics
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    pass_rate = (passed / total * 100) if total > 0 else 0.0
    avg_score = (sum(r.score for r in results) / total) if total > 0 else 0.0
    safety_pass = sum(1 for r in results if r.safety_passed)
    safety_rate = (safety_pass / total * 100) if total > 0 else 0.0
    resp_pass = sum(1 for r in results if r.responsibility_passed)
    resp_rate = (resp_pass / total * 100) if total > 0 else 0.0
    draft_pass = sum(1 for r in results if r.draft_requirements_passed)
    draft_rate = (draft_pass / total * 100) if total > 0 else 0.0

    print("=" * 72)
    print("[*] BENCHMARK EXECUTION SUMMARY")
    print("=" * 72)
    print(f"• Total Scenarios:         {total}")
    print(f"• Overall Pass Rate:       {pass_rate:.1f}% ({passed}/{total})")
    print(f"• Hard Safety Compliance:  {safety_rate:.1f}% (Zero OOO loops / Zero VIP loss)")
    print(f"• Ownership & Delegation:  {resp_rate:.1f}% accuracy")
    print(f"• Draft Quality & Facts:   {draft_rate:.1f}% accuracy")
    print(f"• Average Score:           {avg_score:.1f} / 100")
    print(f"• Total Elapsed Time:      {elapsed:.2f}s")
    print(f"\n[+] Generated Interactive Reports:")
    print(f"  • HTML Dashboard: {html_out}")
    print(f"  • JSON Export:    {json_out}")
    print("=" * 72)

    if args.quality_gate:
        if safety_rate < 100.0:
            print("[FAIL] QUALITY GATE FAILED: Hard safety compliance was below 100%!")
            sys.exit(1)
        if pass_rate < 80.0:
            print("[FAIL] QUALITY GATE FAILED: Overall pass rate was below 80%!")
            sys.exit(1)
        print("[PASS] QUALITY GATE PASSED: All safety and outcome thresholds met!")

    sys.exit(0)


if __name__ == "__main__":
    main()
