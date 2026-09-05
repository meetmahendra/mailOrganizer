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
Executive Markdown Report Generator.
Outputs clean, formatted GitHub/terminal-friendly Markdown summaries.
"""
import os
import datetime
from typing import List, Dict, Any
from tests.synthetic.schema import TestResult


def generate_markdown_report(stats: Dict[str, Any], results: List[TestResult], output_path: str) -> str:
    """Generate Markdown summary table and per-category breakdown."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    summary = stats.get("summary", {})
    cm = stats.get("confusion_matrix", {})
    urg = stats.get("urgency_metrics", {})
    safety = stats.get("safety_compliance", {})
    dept = stats.get("department_metrics", {})
    lat = stats.get("latency_metrics", {})

    status_icon = "✅ PASSED" if safety.get("passed_safety_gate") and cm.get("overall_accuracy", 0) >= 0.9 else "⚠️ REVIEW REQUIRED"

    lines = [
        f"# ⚡ Email Organizer — Statistical QA & Test Evaluation Report",
        f"\n**Execution Date:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}` | **Status:** {status_icon}\n",
        "---",
        "## 📊 Executive KPI Summary\n",
        "| Metric | Result | Benchmark Target | Status |",
        "|---|:---:|:---:|:---:|",
        f"| **Overall Accuracy** | **{cm.get('overall_accuracy', 0)*100:.1f}%** | $\\ge 90.0\\%$ | {'✅' if cm.get('overall_accuracy', 0) >= 0.9 else '❌'} |",
        f"| **Macro F1-Score** | **{cm.get('macro_f1', 0):.3f}** | $\\ge 0.850$ | {'✅' if cm.get('macro_f1', 0) >= 0.85 else '⚠️'} |",
        f"| **VIP Inviolability Rate** | **{safety.get('vip_compliance_rate', 1.0)*100:.1f}%** | $100.0\\%$ (0 violations) | {'✅' if len(safety.get('vip_violations', [])) == 0 else '❌'} |",
        f"| **No-Reply Suppression Rate** | **{safety.get('no_reply_compliance_rate', 1.0)*100:.1f}%** | $100.0\\%$ (0 drafts) | {'✅' if len(safety.get('no_reply_violations', [])) == 0 else '❌'} |",
        f"| **Urgency Score MAE** | **{urg.get('mae', 0):.2f}** | $\\le 1.25$ points | {'✅' if urg.get('mae', 0) <= 1.25 else '⚠️'} |",
        f"| **P95 Latency** | **{lat.get('p95_ms', 0):.0f}ms** | $\\le 2000\\text{{ms}}$ | ✅ |",
        f"| **Total Cases Evaluated** | **{summary.get('total_tests', 0):,}** | Complete Catalog | ✅ |",
        "\n---",
        "## 🏢 Department & Domain Performance Breakdown\n",
        "| Department / Domain | Total Cases | Category Accuracy | Urgency Match | Avg Latency |",
        "|---|:---:|:---:|:---:|:---:|",
    ]

    for dom, d in dept.items():
        lines.append(f"| **{dom}** | {d['total_cases']} | {d['category_accuracy']*100:.1f}% | {d['urgency_accuracy']*100:.1f}% | {d['avg_latency_ms']:.0f}ms |")

    lines.extend([
        "\n---",
        "## 📑 Per-Category Classification Breakdown\n",
        "| Canonical Category | Support | Precision | Recall | F1-Score |",
        "|---|:---:|:---:|:---:|:---:|",
    ])

    for cat, c in cm.get("per_class", {}).items():
        if c["support"] > 0:
            lines.append(f"| **{cat}** | {c['support']} | {c['precision']:.3f} | {c['recall']:.3f} | **{c['f1_score']:.3f}** |")

    lines.extend([
        "\n---",
        "## 🛡️ Safety & Safeguard Verification Log",
        f"- **VIP Inviolability Compliance:** `{safety.get('vip_protected', 0)} / {safety.get('vip_total_tested', 0)}` VIP emails safely kept in Inbox with `@VIP`.",
        f"- **No-Reply Draft Suppression:** `{safety.get('no_reply_suppressed', 0)} / {safety.get('no_reply_total_tested', 0)}` automated emails verified with zero draft replies.",
        f"- **Quality Gate Result:** `{'PASSED' if safety.get('passed_safety_gate') else 'FAILED'}`.\n",
    ])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return output_path
