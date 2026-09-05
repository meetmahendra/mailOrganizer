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
Interactive HTML Dashboard Report Generator.

Generates a modern, standalone, offline-ready HTML report with:
  • Executive KPI summary cards
  • Pure SVG Heatmap Confusion Matrix (9x9) with cell inspection
  • Department & Domain Performance charts
  • Urgency error distribution bars
  • Interactive, searchable, filterable test case explorer with expandable diffs
"""
import os
import json
import datetime
from typing import List, Dict, Any
from tests.synthetic.schema import TestResult


def generate_svg_confusion_matrix(cm_data: Dict[str, Any]) -> str:
    """Generate inline pure SVG heatmap for the 9x9 confusion matrix."""
    matrix = cm_data.get("matrix", {})
    categories = cm_data.get("categories", [])
    if not categories:
        return "<p>No confusion matrix data.</p>"

    cell_size = 50
    margin_left = 180
    margin_top = 140
    width = margin_left + len(categories) * cell_size + 40
    height = margin_top + len(categories) * cell_size + 60

    max_val = max(max(row.values()) for row in matrix.values()) if matrix else 1
    if max_val == 0:
        max_val = 1

    svg_parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="auto" xmlns="http://www.w3.org/2000/svg" style="font-family: system-ui, sans-serif; font-size: 11px;">',
        '<rect width="100%" height="100%" fill="#1a1e29" rx="8"/>',
        f'<text x="{width//2}" y="30" text-anchor="middle" fill="#f3f4f6" font-size="15" font-weight="700">9×9 Category Confusion Matrix Heatmap</text>',
        f'<text x="{margin_left + (len(categories)*cell_size)//2}" y="55" text-anchor="middle" fill="#9ca3af" font-size="11">Predicted Category (Columns) vs Actual Category (Rows)</text>',
    ]

    # Column Headers (Predicted)
    for col_idx, cat in enumerate(categories):
        x = margin_left + col_idx * cell_size + cell_size // 2
        y = margin_top - 10
        short_cat = cat.replace("Action Required ", "Act: ").replace("Informational/Logs", "Info/Logs").replace("Receipts/Financial", "Finance").replace("Promotions/Marketing", "Promo").replace("System Alert", "Sys Alert")
        svg_parts.append(f'<text x="{x}" y="{y}" transform="rotate(-45 {x} {y})" text-anchor="start" fill="#93c5fd" font-weight="600">{short_cat}</text>')

    # Rows (Actual)
    for row_idx, actual_cat in enumerate(categories):
        row_y = margin_top + row_idx * cell_size
        short_cat = actual_cat.replace("Action Required ", "Act: ").replace("Informational/Logs", "Info/Logs").replace("Receipts/Financial", "Finance").replace("Promotions/Marketing", "Promo").replace("System Alert", "Sys Alert")
        svg_parts.append(f'<text x="{margin_left - 12}" y="{row_y + cell_size//2 + 4}" text-anchor="end" fill="#d1d5db" font-weight="600">{short_cat}</text>')

        for col_idx, pred_cat in enumerate(categories):
            count = matrix.get(actual_cat, {}).get(pred_cat, 0)
            cell_x = margin_left + col_idx * cell_size
            intensity = count / max_val
            
            if actual_cat == pred_cat:
                # Diagonal (Correct) -> Green / Cyan
                fill_color = f"rgba(16, 185, 129, {0.2 + 0.8 * intensity})" if count > 0 else "#232838"
                text_color = "#ffffff" if intensity > 0.4 else "#a7f3d0"
            else:
                # Off-diagonal (Errors) -> Red / Orange
                fill_color = f"rgba(239, 68, 68, {0.2 + 0.8 * intensity})" if count > 0 else "#232838"
                text_color = "#ffffff" if intensity > 0.4 else "#fca5a5"

            svg_parts.append(f'<rect x="{cell_x}" y="{row_y}" width="{cell_size-2}" height="{cell_size-2}" rx="4" fill="{fill_color}"/>')
            if count > 0:
                svg_parts.append(f'<text x="{cell_x + cell_size//2 - 1}" y="{row_y + cell_size//2 + 4}" text-anchor="middle" fill="{text_color}" font-weight="700">{count}</text>')

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def generate_html_report(stats: Dict[str, Any], results: List[TestResult], output_path: str) -> str:
    """Generate a rich standalone interactive HTML dashboard."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    summary = stats.get("summary", {})
    cm = stats.get("confusion_matrix", {})
    urg = stats.get("urgency_metrics", {})
    safety = stats.get("safety_compliance", {})
    dept = stats.get("department_metrics", {})
    lat = stats.get("latency_metrics", {})

    cm_svg = generate_svg_confusion_matrix(cm)

    # Encode test results for client-side search/filtering
    results_json = json.dumps([{
        "id": r.test_id,
        "suite": r.suite,
        "domain": r.domain,
        "title": r.title,
        "passed": r.passed,
        "actual_cat": r.expected.category,
        "pred_cat": r.predicted_category,
        "actual_urg": f"{r.expected.urgency_score_range[0]}-{r.expected.urgency_score_range[1]}",
        "pred_urg": r.predicted_urgency,
        "is_vip": r.expected.is_vip,
        "is_no_reply": r.expected.is_no_reply,
        "duration_ms": r.duration_ms,
        "sender": r.email_sender,
        "subject": r.email_subject,
        "reasoning": r.reasoning,
        "suggested_reply": r.suggested_reply,
        "actions": r.predicted_actions,
    } for r in results])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Email Organizer — Synthetic Test & Statistical QA Report</title>
  <style>
    :root {{
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #38bdf8;
      --success: #10b981;
      --danger: #ef4444;
      --warning: #f59e0b;
      --accent: #818cf8;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); padding: 24px; line-height: 1.5; }}
    .container {{ max-width: 1400px; margin: 0 auto; }}
    header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 20px; margin-bottom: 24px; }}
    h1 {{ font-size: 26px; font-weight: 800; background: linear-gradient(135deg, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
    .badge {{ display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 700; text-transform: uppercase; }}
    .badge-success {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #059669; }}
    .badge-danger {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #dc2626; }}
    
    /* Grid & Cards */
    .grid-kpi {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }}
    .card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); }}
    .card-title {{ font-size: 13px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; font-weight: 600; }}
    .card-val {{ font-size: 32px; font-weight: 800; color: var(--text); }}
    .card-sub {{ font-size: 12px; color: var(--text-muted); margin-top: 4px; }}

    /* Layout Sections */
    .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }}
    @media (max-width: 1024px) {{ .two-col {{ grid-template-columns: 1fr; }} }}

    /* Table Styles */
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }}
    th, td {{ padding: 12px 14px; border-bottom: 1px solid var(--border); }}
    th {{ background: #0f172a; color: var(--text-muted); font-weight: 600; position: sticky; top: 0; }}
    tr:hover {{ background: rgba(255,255,255,0.02); }}
    
    /* Explorer Controls */
    .controls {{ display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }}
    input, select {{ background: #0f172a; border: 1px solid var(--border); color: var(--text); padding: 10px 14px; border-radius: 8px; font-size: 14px; outline: none; }}
    input:focus, select:focus {{ border-color: var(--primary); }}
    .search-bar {{ flex: 1; min-width: 260px; }}

    /* Drawer / Modal */
    .drawer {{ display: none; background: #0f172a; border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin: 8px 0; font-size: 13px; }}
    .diff-box {{ background: #1e293b; padding: 12px; border-radius: 6px; margin-top: 8px; font-family: monospace; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>⚡ Email Organizer — Comprehensive Test & Statistical Report</h1>
        <p style="color: var(--text-muted); font-size: 13px; margin-top: 4px;">Generated on {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | Mode: Complete Statistical Validation</p>
      </div>
      <div>
        <span class="badge {'badge-success' if safety.get('passed_safety_gate') else 'badge-danger'}">
          {'QUALITY GATE PASSED' if safety.get('passed_safety_gate') else 'SAFETY VIOLATION DETECTED'}
        </span>
      </div>
    </header>

    <!-- KPI Metric Cards -->
    <div class="grid-kpi">
      <div class="card">
        <div class="card-title">Overall Accuracy</div>
        <div class="card-val" style="color: var(--primary);">{cm.get('overall_accuracy', 0)*100:.1f}%</div>
        <div class="card-sub">{summary.get('passed_tests', 0)} of {summary.get('total_tests', 0)} cases passed</div>
      </div>
      <div class="card">
        <div class="card-title">Macro F1-Score</div>
        <div class="card-val" style="color: var(--accent);">{cm.get('macro_f1', 0):.3f}</div>
        <div class="card-sub">Weighted F1: {cm.get('weighted_f1', 0):.3f}</div>
      </div>
      <div class="card">
        <div class="card-title">VIP Safety Inviolability</div>
        <div class="card-val" style="color: var(--success);">{safety.get('vip_compliance_rate', 1.0)*100:.1f}%</div>
        <div class="card-sub">{safety.get('vip_protected', 0)} / {safety.get('vip_total_tested', 0)} VIP emails preserved</div>
      </div>
      <div class="card">
        <div class="card-title">Urgency Score MAE</div>
        <div class="card-val">{urg.get('mae', 0):.2f}</div>
        <div class="card-sub">{urg.get('within_one_rate', 0)*100:.1f}% within ±1 point</div>
      </div>
      <div class="card">
        <div class="card-title">P95 Latency</div>
        <div class="card-val">{lat.get('p95_ms', 0):.0f}ms</div>
        <div class="card-sub">Median p50: {lat.get('median_p50_ms', 0):.0f}ms</div>
      </div>
    </div>

    <!-- Middle: Heatmap & Department Breakdown -->
    <div class="two-col">
      <div class="card">
        <div class="card-title">Confusion Matrix Heatmap</div>
        <div style="overflow-x: auto; margin-top: 10px;">
          {cm_svg}
        </div>
      </div>

      <div class="card">
        <div class="card-title">Departmental & Domain Performance</div>
        <div style="overflow-x: auto; margin-top: 10px;">
          <table>
            <thead>
              <tr>
                <th>Domain / Department</th>
                <th>Cases</th>
                <th>Accuracy</th>
                <th>Urgency Acc</th>
                <th>Avg Latency</th>
              </tr>
            </thead>
            <tbody>
              {"".join(f'''
              <tr>
                <td style="font-weight: 600;">{dom}</td>
                <td>{d['total_cases']}</td>
                <td style="color: {'#34d399' if d['category_accuracy'] >= 0.9 else '#f59e0b'}; font-weight: 700;">{d['category_accuracy']*100:.1f}%</td>
                <td>{d['urgency_accuracy']*100:.1f}%</td>
                <td>{d['avg_latency_ms']:.0f}ms</td>
              </tr>
              ''' for dom, d in dept.items())}
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Category Performance Table -->
    <div class="card" style="margin-bottom: 24px;">
      <div class="card-title">Detailed Per-Category Performance Breakdown</div>
      <div style="overflow-x: auto; margin-top: 10px;">
        <table>
          <thead>
            <tr>
              <th>Canonical Category</th>
              <th>Support</th>
              <th>Precision</th>
              <th>Recall</th>
              <th>F1-Score</th>
              <th>TP / FP / FN</th>
            </tr>
          </thead>
          <tbody>
            {"".join(f'''
            <tr>
              <td style="font-weight: 600; color: var(--primary);">{cat}</td>
              <td>{c['support']}</td>
              <td>{c['precision']:.3f}</td>
              <td>{c['recall']:.3f}</td>
              <td style="font-weight: 700; color: {'#34d399' if c['f1_score'] >= 0.85 else '#f87171'};">{c['f1_score']:.3f}</td>
              <td style="color: var(--text-muted);">{c['tp']} / {c['fp']} / {c['fn']}</td>
            </tr>
            ''' for cat, c in cm.get('per_class', {}).items() if c['support'] > 0)}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Interactive Test Case Explorer -->
    <div class="card">
      <div class="card-title">Interactive Test Case Explorer & Deep-Dive</div>
      <div class="controls" style="margin-top: 14px;">
        <input type="text" id="searchInput" class="search-bar" placeholder="🔍 Search test title, sender, subject, or ID..." oninput="filterCases()">
        <select id="statusFilter" onchange="filterCases()">
          <option value="ALL">All Statuses</option>
          <option value="PASSED">Passed Only</option>
          <option value="FAILED">Failed Only</option>
        </select>
        <select id="suiteFilter" onchange="filterCases()">
          <option value="ALL">All Suites</option>
          {"".join(f'<option value="{s}">{s}</option>' for s in sorted(list(set(r.suite for r in results))))}
        </select>
      </div>

      <div style="overflow-x: auto;">
        <table id="testTable">
          <thead>
            <tr>
              <th>ID</th>
              <th>Title & Subject</th>
              <th>Domain</th>
              <th>Expected vs Predicted</th>
              <th>Urgency</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody id="testTbody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    const data = {results_json};

    function renderRows(items) {{
      const tbody = document.getElementById("testTbody");
      if (items.length === 0) {{
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #94a3b8; padding: 24px;">No test cases match filter.</td></tr>';
        return;
      }}
      tbody.innerHTML = items.map((r, i) => `
        <tr>
          <td style="font-family: monospace; font-weight: 700; color: #38bdf8;">${{r.id}}</td>
          <td>
            <div style="font-weight: 600;">${{r.title}}</div>
            <div style="color: #94a3b8; font-size: 11px;">${{r.subject}} — from <em>${{r.sender}}</em></div>
          </td>
          <td><span style="font-size: 11px; background: #334155; padding: 2px 6px; border-radius: 4px;">${{r.domain}}</span></td>
          <td>
            <div style="font-size: 11px;">Exp: <strong>${{r.actual_cat}}</strong></div>
            <div style="font-size: 11px; color: ${{r.actual_cat === r.pred_cat ? '#34d399' : '#f87171'}};">Pred: <strong>${{r.pred_cat}}</strong></div>
          </td>
          <td>
            <div style="font-size: 11px;">Exp: ${{r.actual_urg}}</div>
            <div style="font-size: 11px; color: #38bdf8;">Pred: ${{r.pred_urg}}</div>
          </td>
          <td>
            <span class="badge ${{r.passed ? 'badge-success' : 'badge-danger'}}">
              ${{r.passed ? 'PASSED' : 'FAILED'}}
            </span>
          </td>
          <td>
            <button onclick="toggleDrawer(${{i}})" style="background: #334155; border: none; color: #fff; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px;">Details ▼</button>
          </td>
        </tr>
        <tr id="drawer-${{i}}" class="drawer">
          <td colspan="7">
            <div class="diff-box">
              <strong>LLM Reasoning:</strong> ${{r.reasoning || "N/A"}}<br>
              <strong>Suggested Reply:</strong> ${{r.suggested_reply ? r.suggested_reply.substring(0, 180) + '...' : 'None'}}<br>
              <strong>Actions Planned:</strong> ${{JSON.stringify(r.actions)}}
            </div>
          </td>
        </tr>
      `).join("");
    }}

    function toggleDrawer(idx) {{
      const d = document.getElementById("drawer-" + idx);
      d.style.display = (d.style.display === "table-row") ? "none" : "table-row";
    }}

    function filterCases() {{
      const q = document.getElementById("searchInput").value.toLowerCase();
      const status = document.getElementById("statusFilter").value;
      const suite = document.getElementById("suiteFilter").value;

      const filtered = data.filter(r => {{
        const matchQ = !q || r.id.toLowerCase().includes(q) || r.title.toLowerCase().includes(q) || r.subject.toLowerCase().includes(q) || r.sender.toLowerCase().includes(q);
        const matchStatus = status === "ALL" || (status === "PASSED" && r.passed) || (status === "FAILED" && !r.passed);
        const matchSuite = suite === "ALL" || r.suite === suite;
        return matchQ && matchStatus && matchSuite;
      }});
      renderRows(filtered);
    }}

    // Initial render
    renderRows(data);
  </script>
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path
