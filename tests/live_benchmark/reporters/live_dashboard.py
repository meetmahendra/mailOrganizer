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
Interactive HTML Dashboard & JSON Reporter for Live Benchmark Results.

Renders full cause-and-effect visibility for every benchmark scenario:
  - Input Email Packet (From, To, Cc, Subject, Body)
  - Intelligence Analysis (Category, Urgency, Context Tags, Reasoning)
  - Ownership Decision & Rationale (Multi-To disambiguation, Delegation Target)
  - Retrieved External Enterprise Facts (RAG endpoints, Calendar)
  - Planned & Executed Actions
  - Verbatim Generated Draft Reply
  - Outcome Validation Breakdown (Safety, Responsibility, Inbox, Keywords)
"""
import os
import json
import html as html_lib
from datetime import datetime
from typing import List, Dict, Any

from tests.live_benchmark.schema import BenchmarkEvaluationResult


class LiveBenchmarkDashboardReporter:
    """Generates standalone interactive HTML reports for live benchmark runs."""

    @staticmethod
    def generate_html_report(results: List[BenchmarkEvaluationResult], output_path: str) -> str:
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        pass_rate = (passed / total * 100) if total > 0 else 0.0
        avg_score = (sum(r.score for r in results) / total) if total > 0 else 0.0

        safety_pass = sum(1 for r in results if r.safety_passed)
        safety_rate = (safety_pass / total * 100) if total > 0 else 0.0

        resp_pass = sum(1 for r in results if r.responsibility_passed)
        resp_rate = (resp_pass / total * 100) if total > 0 else 0.0

        draft_pass = sum(1 for r in results if r.draft_requirements_passed)
        draft_rate = (draft_pass / total * 100) if total > 0 else 0.0

        # Domain breakdown
        domains: Dict[str, Dict[str, Any]] = {}
        for r in results:
            d = r.domain
            if d not in domains:
                domains[d] = {"total": 0, "passed": 0, "scores": []}
            domains[d]["total"] += 1
            if r.passed:
                domains[d]["passed"] += 1
            domains[d]["scores"].append(r.score)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # HTML Head and Styles
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MailOrganizer — High-Fidelity Live Benchmark Dashboard</title>
    <style>
        :root {{
            --bg: #0b1120;
            --surface: #1e293b;
            --surface-hover: #24344d;
            --border: #334155;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --accent: #38bdf8;
            --pass: #10b981;
            --fail: #f43f5e;
            --warning: #f59e0b;
            --code-bg: #0f172a;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 24px;
            line-height: 1.5;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding-bottom: 20px;
            margin-bottom: 24px;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .badge {{
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}
        .badge-pass {{ background: rgba(16, 185, 129, 0.15); color: var(--pass); border: 1px solid var(--pass); }}
        .badge-fail {{ background: rgba(244, 63, 94, 0.15); color: var(--fail); border: 1px solid var(--fail); }}
        .badge-pill {{ background: #334155; color: #e2e8f0; font-size: 11px; padding: 2px 8px; border-radius: 4px; }}
        .badge-role {{ background: #1e3a8a; color: #93c5fd; font-size: 11px; padding: 2px 8px; border-radius: 4px; font-weight: 600; }}
        
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
        }}
        .card-title {{
            font-size: 12px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 8px;
            font-weight: 600;
        }}
        .card-value {{
            font-size: 28px;
            font-weight: 800;
        }}

        .controls-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 12px 16px;
            margin-bottom: 20px;
            gap: 12px;
            flex-wrap: wrap;
        }}
        .filter-group {{
            display: flex;
            gap: 8px;
        }}
        .btn {{
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 6px 14px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s;
        }}
        .btn:hover {{ background: var(--surface-hover); }}
        .btn.active {{ background: #0284c7; border-color: #38bdf8; color: #ffffff; }}
        .search-box {{
            flex-grow: 1;
            max-width: 400px;
            background: var(--code-bg);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 7px 12px;
            border-radius: 6px;
            font-size: 13px;
            outline: none;
        }}
        .search-box:focus {{ border-color: var(--accent); }}

        /* Scenario Accordion Card */
        .scenario-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            margin-bottom: 12px;
            overflow: hidden;
            transition: border-color 0.15s;
        }}
        .scenario-card[data-status="pass"] {{ border-left: 4px solid var(--pass); }}
        .scenario-card[data-status="fail"] {{ border-left: 4px solid var(--fail); }}
        .scenario-header {{
            padding: 14px 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            user-select: none;
            gap: 16px;
            background: var(--surface);
            list-style: none;
        }}
        .scenario-header::-webkit-details-marker {{ display: none; }}
        .scenario-header:hover {{ background: var(--surface-hover); }}
        
        .header-left {{
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
            font-weight: 600;
            font-size: 15px;
        }}
        .header-right {{
            display: flex;
            align-items: center;
            gap: 12px;
            flex-shrink: 0;
        }}
        .chevron {{
            font-size: 12px;
            color: var(--text-muted);
            transition: transform 0.2s;
        }}
        details[open] .chevron {{
            transform: rotate(180deg);
        }}

        .scenario-body {{
            padding: 20px;
            border-top: 1px solid var(--border);
            background: #151f30;
        }}

        /* Two Column Inspection Layout */
        .two-col-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 16px;
        }}
        @media (max-width: 1024px) {{
            .two-col-grid {{ grid-template-columns: 1fr; }}
        }}

        .section-box {{
            background: var(--code-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            font-size: 13px;
        }}
        .section-title {{
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--accent);
            font-weight: 700;
            margin-top: 0;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .meta-row {{
            display: flex;
            margin-bottom: 6px;
            gap: 8px;
        }}
        .meta-label {{
            color: var(--text-muted);
            width: 90px;
            flex-shrink: 0;
            font-weight: 600;
        }}
        .meta-val {{
            color: #e2e8f0;
            word-break: break-word;
        }}
        .content-box {{
            background: #090d16;
            border: 1px solid #1e293b;
            border-radius: 6px;
            padding: 12px;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 12.5px;
            line-height: 1.6;
            white-space: pre-wrap;
            word-break: break-word;
            margin-top: 8px;
            color: #cbd5e1;
            max-height: 280px;
            overflow-y: auto;
        }}
        .facts-list {{
            margin: 0;
            padding-left: 18px;
            color: #94a3b8;
        }}
        .facts-list li {{
            margin-bottom: 4px;
        }}
        .tag-chip {{
            display: inline-block;
            background: #0369a1;
            color: #e0f2fe;
            font-size: 11px;
            padding: 2px 7px;
            border-radius: 4px;
            margin-right: 4px;
            margin-bottom: 4px;
            font-weight: 500;
        }}
        .action-chip {{
            display: inline-block;
            background: #475569;
            color: #f8fafc;
            font-size: 11px;
            padding: 2px 7px;
            border-radius: 4px;
            margin-right: 4px;
            margin-bottom: 4px;
            font-family: monospace;
        }}
        .kw-chip {{
            display: inline-block;
            font-size: 11px;
            padding: 2px 7px;
            border-radius: 4px;
            margin-right: 4px;
            margin-bottom: 4px;
            font-weight: 600;
        }}
        .kw-pass {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid var(--pass); }}
        .kw-fail {{ background: rgba(244, 63, 94, 0.2); color: #fb7185; border: 1px solid var(--fail); }}

        /* Checklist bar */
        .checklist-bar {{
            background: var(--code-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 12px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
            font-size: 12.5px;
        }}
        .check-item {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .alert-box {{
            background: rgba(244, 63, 94, 0.1);
            border: 1px solid var(--fail);
            border-radius: 6px;
            padding: 10px 14px;
            margin-bottom: 16px;
            font-size: 13px;
            color: #fecdd3;
        }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <div>
            <h1 style="margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.02em;">
                MailOrganizer <span style="color: var(--accent);">•</span> High-Fidelity Live Benchmark Dashboard
            </h1>
            <p style="margin: 4px 0 0 0; color: var(--text-muted); font-size: 14px;">
                Evaluated at {timestamp} • Outcome-Based Evaluation Matrix (Phases 7 & 8)
            </p>
        </div>
        <div>
            <span class="badge {'badge-pass' if pass_rate >= 80 else 'badge-fail'}">
                {'QUALITY GATE PASSED' if pass_rate >= 80 else 'QUALITY GATE FAILED'}
            </span>
        </div>
    </div>

    <!-- Summary Metrics Cards -->
    <div class="grid">
        <div class="card">
            <div class="card-title">Overall Pass Rate</div>
            <div class="card-value" style="color: {'var(--pass)' if pass_rate >= 80 else 'var(--fail)'};">{pass_rate:.1f}%</div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">{passed} passed / {failed} failed</div>
        </div>
        <div class="card">
            <div class="card-title">Hard Safety Compliance</div>
            <div class="card-value" style="color: {'var(--pass)' if safety_rate == 100 else 'var(--fail)'};">{safety_rate:.1f}%</div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Zero VIP loss, Zero OOO loop replies</div>
        </div>
        <div class="card">
            <div class="card-title">Ownership Accuracy</div>
            <div class="card-value" style="color: {'var(--pass)' if resp_rate >= 85 else 'var(--warning)'};">{resp_rate:.1f}%</div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Multi-To, CC & Teammate tracking</div>
        </div>
        <div class="card">
            <div class="card-title">Draft Factuality</div>
            <div class="card-value" style="color: {'var(--pass)' if draft_rate >= 80 else 'var(--warning)'};">{draft_rate:.1f}%</div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Grounding facts, anti-stalling</div>
        </div>
        <div class="card">
            <div class="card-title">Average Score</div>
            <div class="card-value" style="color: var(--accent);">{avg_score:.1f} / 100</div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Across {total} authentic scenarios</div>
        </div>
    </div>

    <!-- Interactive Filter & Search Controls -->
    <div class="controls-bar">
        <div class="filter-group">
            <button class="btn active" onclick="filterStatus('all')">All ({total})</button>
            <button class="btn" onclick="filterStatus('pass')">Passed ({passed})</button>
            <button class="btn" onclick="filterStatus('fail')">Failed ({failed})</button>
            <button class="btn" onclick="toggleAll(true)">Expand All</button>
            <button class="btn" onclick="toggleAll(false)">Collapse All</button>
        </div>
        <input type="text" id="searchInput" class="search-box" placeholder="Search ID, title, domain, sender, keyword..." oninput="searchScenarios()" />
    </div>

    <!-- Scenario Accordion List -->
    <div id="scenariosList">
"""

        for r in results:
            status_str = "pass" if r.passed else "fail"
            status_badge = '<span class="badge badge-pass">PASS</span>' if r.passed else '<span class="badge badge-fail">FAIL</span>'
            domain_clean = r.domain.replace('_', ' ').title()

            # Format failure alerts if any
            failure_alert = ""
            if r.failure_reasons:
                items = "".join(f"<li>{html_lib.escape(f)}</li>" for f in r.failure_reasons)
                failure_alert = f'<div class="alert-box"><strong>Failure Diagnostics:</strong><ul style="margin: 4px 0 0 0; padding-left: 18px;">{items}</ul></div>'

            # Tags chips
            tag_chips = "".join(f'<span class="tag-chip">{html_lib.escape(t)}</span>' for t in r.context_tags)
            if not tag_chips:
                tag_chips = '<span style="color: var(--text-muted);">None</span>'

            # Action chips
            action_chips = ""
            for a in r.planned_actions:
                act = a.get("action", "")
                lbl = a.get("label", "")
                label_str = f": {lbl}" if lbl else ""
                action_chips += f'<span class="action-chip">{html_lib.escape(act)}{html_lib.escape(label_str)}</span>'
            if not action_chips:
                action_chips = '<span style="color: var(--text-muted);">None planned</span>'

            # Verified / Missing Keyword chips
            kw_html = ""
            for kw in r.verified_keywords:
                kw_html += f'<span class="kw-chip kw-pass">✓ {html_lib.escape(kw)}</span>'
            for kw in r.missing_keywords:
                kw_html += f'<span class="kw-chip kw-fail">✗ {html_lib.escape(kw)}</span>'
            if not kw_html:
                kw_html = '<span style="color: var(--text-muted);">None specified</span>'

            # Facts formatting
            facts_html = ""
            if r.retrieved_facts:
                fact_lines = [line.strip() for line in r.retrieved_facts.split("\n") if line.strip()]
                items = "".join(f"<li>{html_lib.escape(f)}</li>" for f in fact_lines)
                facts_html = f'<ul class="facts-list">{items}</ul>'
            else:
                facts_html = '<span style="color: var(--text-muted);">No external facts retrieved for this query.</span>'

            # Draft formatting
            draft_html = ""
            if r.actual_draft:
                draft_html = f'<div class="content-box">{html_lib.escape(r.actual_draft)}</div>'
            else:
                draft_html = f'<div style="color: var(--text-muted); font-style: italic; padding: 8px 0;">Draft reply was suppressed (Role: <code>{html_lib.escape(r.actual_responsibility)}</code>).</div>'

            # Delegation target display
            delegation_str = "None (Direct action by Marcus Vance)"
            if r.delegation_target:
                t_name = r.delegation_target.get("name", "")
                t_email = r.delegation_target.get("email", "")
                t_cap = r.delegation_target.get("capability", "")
                delegation_str = f"<strong>{html_lib.escape(t_name)}</strong> &lt;{html_lib.escape(t_email)}&gt; — <em>{html_lib.escape(t_cap)}</em>"

            to_str = ", ".join(r.to_recipients) if r.to_recipients else "None"
            cc_str = ", ".join(r.cc_recipients) if r.cc_recipients else "None"

            # Checkmark icons
            safety_icon = "✓" if r.safety_passed else "✗"
            resp_icon = "✓" if r.responsibility_passed else "✗"
            inbox_icon = "✓" if r.inbox_placement_passed else "✗"
            draft_icon = "✓" if r.draft_requirements_passed else "✗"

            html += f"""
        <details class="scenario-card" data-status="{status_str}" data-domain="{html_lib.escape(r.domain.lower())}">
            <summary class="scenario-header">
                <div class="header-left">
                    {status_badge}
                    <code style="color: var(--accent);">{html_lib.escape(r.test_id)}</code>
                    <span>{html_lib.escape(r.title)}</span>
                    <span class="badge-pill">{domain_clean}</span>
                </div>
                <div class="header-right">
                    <span class="badge-role">{html_lib.escape(r.actual_responsibility)}</span>
                    <span style="font-weight: 700; font-size: 14px; color: {'var(--pass)' if r.passed else 'var(--fail)'};">{r.score:.0f} pts</span>
                    <span class="chevron">▼</span>
                </div>
            </summary>
            <div class="scenario-body">
                {failure_alert}
                
                <div class="two-col-grid">
                    <!-- Column 1: Incoming Packet & Context -->
                    <div>
                        <div class="section-box" style="margin-bottom: 16px;">
                            <h3 class="section-title">✉️ Incoming Email Packet</h3>
                            <div class="meta-row"><span class="meta-label">From:</span><span class="meta-val">{html_lib.escape(r.sender)}</span></div>
                            <div class="meta-row"><span class="meta-label">To:</span><span class="meta-val">{html_lib.escape(to_str)}</span></div>
                            <div class="meta-row"><span class="meta-label">Cc:</span><span class="meta-val">{html_lib.escape(cc_str)}</span></div>
                            <div class="meta-row"><span class="meta-label">Subject:</span><span class="meta-val"><strong>{html_lib.escape(r.subject)}</strong></span></div>
                            <div style="margin-top: 10px;">
                                <span style="font-weight: 600; color: var(--text-muted); font-size: 11px; text-transform: uppercase;">Original Message Body:</span>
                                <div class="content-box">{html_lib.escape(r.body)}</div>
                            </div>
                        </div>

                        <div class="section-box">
                            <h3 class="section-title">📚 Retrieved Knowledge & Facts (RAG / MCP / Calendar)</h3>
                            {facts_html}
                        </div>
                    </div>

                    <!-- Column 2: Reasoning & Output -->
                    <div>
                        <div class="section-box" style="margin-bottom: 16px;">
                            <h3 class="section-title">🧠 Intent & Ownership Reasoning</h3>
                            <div class="meta-row"><span class="meta-label">Category:</span><span class="meta-val"><strong>{html_lib.escape(r.category)}</strong></span></div>
                            <div class="meta-row"><span class="meta-label">Urgency Score:</span><span class="meta-val"><strong>{r.urgency_score} / 10</strong></span></div>
                            <div class="meta-row"><span class="meta-label">Context Tags:</span><span class="meta-val">{tag_chips}</span></div>
                            <div class="meta-row"><span class="meta-label">Responsibility:</span><span class="meta-val"><code>{html_lib.escape(r.actual_responsibility)}</code></span></div>
                            <div class="meta-row"><span class="meta-label">Reasoning:</span><span class="meta-val"><em>{html_lib.escape(r.ownership_reason or r.reasoning or 'Standard deterministic evaluation')}</em></span></div>
                            <div class="meta-row"><span class="meta-label">Delegation:</span><span class="meta-val">{delegation_str}</span></div>
                            <div class="meta-row" style="margin-top: 8px;"><span class="meta-label">Planned Actions:</span><span class="meta-val">{action_chips}</span></div>
                        </div>

                        <div class="section-box">
                            <h3 class="section-title">✍️ Verbatim Generated Reply Draft</h3>
                            {draft_html}
                        </div>
                    </div>
                </div>

                <!-- Checklist Bar Footer -->
                <div class="checklist-bar">
                    <div class="check-item" style="color: {'var(--pass)' if r.safety_passed else 'var(--fail)'};">
                        <strong>[{safety_icon}] Safety Inviolability:</strong> {r.score_breakdown.get('safety', 0):.0f}/35 pts
                    </div>
                    <div class="check-item" style="color: {'var(--pass)' if r.responsibility_passed else 'var(--fail)'};">
                        <strong>[{resp_icon}] Responsibility Assignment:</strong> {r.score_breakdown.get('responsibility', 0):.0f}/25 pts
                    </div>
                    <div class="check-item" style="color: {'var(--pass)' if r.inbox_placement_passed else 'var(--fail)'};">
                        <strong>[{inbox_icon}] Inbox Action:</strong> {r.actual_inbox_action} ({r.score_breakdown.get('inbox_placement', 0):.0f}/20 pts)
                    </div>
                    <div class="check-item" style="color: {'var(--pass)' if r.draft_requirements_passed else 'var(--fail)'};">
                        <strong>[{draft_icon}] Draft Quality:</strong> {r.score_breakdown.get('draft_factuality', 0):.0f}/20 pts
                    </div>
                    <div class="check-item">
                        <span style="color: var(--text-muted); margin-right: 4px;">Keywords:</span> {kw_html}
                    </div>
                </div>
            </div>
        </details>
"""

        html += """
    </div>
</div>

<script>
    function filterStatus(status) {
        document.querySelectorAll('.btn').forEach(b => b.classList.remove('active'));
        event.target.classList.add('active');
        
        const cards = document.querySelectorAll('.scenario-card');
        cards.forEach(card => {
            if (status === 'all') {
                card.style.display = 'block';
            } else {
                card.style.display = card.getAttribute('data-status') === status ? 'block' : 'none';
            }
        });
    }

    function searchScenarios() {
        const query = document.getElementById('searchInput').value.toLowerCase().trim();
        const cards = document.querySelectorAll('.scenario-card');
        cards.forEach(card => {
            const text = card.textContent.toLowerCase();
            card.style.display = text.includes(query) ? 'block' : 'none';
        });
    }

    function toggleAll(openState) {
        document.querySelectorAll('.scenario-card').forEach(c => c.open = openState);
    }
</script>
</body>
</html>
"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return output_path

    @staticmethod
    def export_json(results: List[BenchmarkEvaluationResult], output_path: str) -> str:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        data = [r.model_dump() for r in results]
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return output_path
