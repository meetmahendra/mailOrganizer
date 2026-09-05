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
Interactive HTML Dashboard Reporter for Partitioned Audit Reports.
"""
import os
import html as html_lib
from typing import List, Dict, Any
from pipeline.audit_schema import AuditRecord


class AuditDashboardReporter:
    """Generates standalone interactive HTML reports for audit log partitions."""

    @staticmethod
    def generate_partition_html(records: List[AuditRecord], output_path: str, part_num: int) -> str:
        total = len(records)
        sources: Dict[str, int] = {}
        for r in records:
            sources[r.entry_point] = sources.get(r.entry_point, 0) + 1

        avg_latency = (sum(r.execution_time_seconds for r in records) / total) if total > 0 else 0.0
        total_llm_calls = sum(len(r.llm_communications) for r in records)

        source_badges = "".join(
            f'<span class="badge-source">{html_lib.escape(src)}: {cnt}</span> '
            for src, cnt in sources.items()
        )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MailOrganizer — Audit Report (Part {part_num:04d})</title>
    <style>
        :root {{
            --bg: #0b1120;
            --surface: #1e293b;
            --surface-hover: #24344d;
            --border: #334155;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --accent: #38bdf8;
            --accent-purple: #c084fc;
            --pass: #10b981;
            --fail: #f43f5e;
            --code-bg: #0f172a;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 24px;
            line-height: 1.5;
        }}
        .container {{ max-width: 1440px; margin: 0 auto; }}
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
        .badge-source {{
            background: #1e3a8a;
            color: #93c5fd;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 700;
        }}
        .badge-mode {{
            background: #334155;
            color: #f1f5f9;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }}
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
            padding: 18px;
        }}
        .card-title {{
            font-size: 11px;
            color: var(--text-muted);
            text-transform: uppercase;
            font-weight: 700;
            letter-spacing: 0.05em;
            margin-bottom: 6px;
        }}
        .card-value {{ font-size: 26px; font-weight: 800; }}
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
        .btn {{
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
        }}
        .btn.active {{ background: #0284c7; border-color: #38bdf8; color: #fff; }}
        .search-box {{
            flex-grow: 1;
            max-width: 400px;
            background: var(--code-bg);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 7px 12px;
            border-radius: 6px;
            font-size: 13px;
        }}
        .scenario-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            margin-bottom: 14px;
            overflow: hidden;
        }}
        .scenario-header {{
            padding: 14px 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            gap: 16px;
            background: var(--surface);
        }}
        .scenario-body {{
            padding: 20px;
            border-top: 1px solid var(--border);
            background: #131d2e;
        }}
        .tab-bar {{
            display: flex;
            gap: 8px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 10px;
            margin-bottom: 16px;
            flex-wrap: wrap;
        }}
        .tab-btn {{
            background: transparent;
            border: 1px solid var(--border);
            color: var(--text-muted);
            padding: 5px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
        }}
        .tab-btn.active {{
            background: var(--accent);
            color: #0b1120;
            border-color: var(--accent);
        }}
        .tab-pane {{ display: none; }}
        .tab-pane.active {{ display: block; }}
        .content-box {{
            background: #090d16;
            border: 1px solid #1e293b;
            border-radius: 6px;
            padding: 12px;
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-size: 12.5px;
            line-height: 1.5;
            white-space: pre-wrap;
            word-break: break-word;
            color: #cbd5e1;
            max-height: 300px;
            overflow-y: auto;
        }}
        .sub-card {{
            background: var(--code-bg);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 12px;
        }}
        .meta-row {{ display: flex; margin-bottom: 6px; gap: 8px; font-size: 13px; }}
        .meta-label {{ color: var(--text-muted); width: 110px; flex-shrink: 0; font-weight: 600; }}
        .tag-chip {{
            display: inline-block;
            background: #0369a1;
            color: #e0f2fe;
            font-size: 11px;
            padding: 2px 7px;
            border-radius: 4px;
            margin-right: 4px;
            margin-bottom: 4px;
        }}
        .breadcrumb {{
            display: flex;
            align-items: center;
            gap: 6px;
            flex-wrap: wrap;
            font-family: monospace;
            font-size: 12px;
            background: #090d16;
            padding: 10px;
            border-radius: 6px;
            border: 1px solid #1e293b;
        }}
        .breadcrumb-item {{
            background: #1e293b;
            padding: 3px 8px;
            border-radius: 4px;
            color: var(--accent);
        }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <div>
            <h1 style="margin:0; font-size: 24px; font-weight: 800;">
                MailOrganizer <span style="color: var(--accent);">•</span> Universal Audit Report
            </h1>
            <p style="margin: 4px 0 0 0; color: var(--text-muted); font-size: 14px;">
                Partition Part {part_num:04d} • Up to 100 Emails per Partition • <a href="../index.html" style="color: var(--accent);">← Back to Master Index</a>
            </p>
        </div>
        <div>{source_badges}</div>
    </div>

    <div class="grid">
        <div class="card">
            <div class="card-title">Emails in Partition</div>
            <div class="card-value" style="color: var(--accent);">{total} / 100</div>
        </div>
        <div class="card">
            <div class="card-title">Average Latency</div>
            <div class="card-value">{avg_latency:.2f}s</div>
        </div>
        <div class="card">
            <div class="card-title">LLM Communications</div>
            <div class="card-value" style="color: var(--accent-purple);">{total_llm_calls}</div>
        </div>
        <div class="card">
            <div class="card-title">Entry Points</div>
            <div class="card-value">{len(sources)}</div>
        </div>
    </div>

    <div class="controls-bar">
        <div style="display:flex; gap: 8px;">
            <button class="btn active" onclick="filterSource('all')">All Sources</button>
            <button class="btn" onclick="toggleAll(true)">Expand All</button>
            <button class="btn" onclick="toggleAll(false)">Collapse All</button>
        </div>
        <input type="text" id="searchInput" class="search-box" placeholder="Search by sender, subject, tags, prompts..." oninput="searchCards()" />
    </div>

    <div id="cardsList">
"""

        for idx, r in enumerate(records):
            cid = f"card_{part_num}_{idx}"
            tag_chips = "".join(f'<span class="tag-chip">{html_lib.escape(t)}</span>' for t in r.context_tags) or "None"

            # LLM sub-cards
            llm_cards = ""
            for l in r.llm_communications:
                llm_cards += f"""
                <div class="sub-card">
                    <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                        <strong style="color:var(--accent); font-size:13px;">Step: {html_lib.escape(l.step.upper())}</strong>
                        <span class="badge-mode">{html_lib.escape(l.model)} | {l.duration_ms:.1f}ms</span>
                    </div>
                    <details style="margin-bottom:6px;">
                        <summary style="font-size:12px; color:var(--text-muted); cursor:pointer;">View System Prompt ({len(l.system_prompt)} chars)</summary>
                        <div class="content-box">{html_lib.escape(l.system_prompt)}</div>
                    </details>
                    <details style="margin-bottom:6px;">
                        <summary style="font-size:12px; color:var(--text-muted); cursor:pointer;">View Human Prompt ({len(l.human_prompt)} chars)</summary>
                        <div class="content-box">{html_lib.escape(l.human_prompt)}</div>
                    </details>
                    <div style="margin-top:6px;">
                        <span style="font-size:11px; color:var(--text-muted); font-weight:600;">RAW COMPLETION / OUTPUT:</span>
                        <div class="content-box">{html_lib.escape(l.raw_response)}</div>
                    </div>
                </div>
                """
            if not llm_cards:
                llm_cards = '<span style="color:var(--text-muted); font-style:italic;">No direct LLM calls made for this item.</span>'

            # Connector sub-cards
            conn_cards = ""
            for c in r.connector_communications:
                facts_str = "\n".join(f"• {f.get('content', '')}" for f in c.raw_facts_returned) or "No facts returned"
                conn_cards += f"""
                <div class="sub-card">
                    <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                        <strong style="color:var(--accent); font-size:13px;">Connector: {html_lib.escape(c.connector_id)}</strong>
                        <span class="badge-mode">{html_lib.escape(c.status)} | {c.duration_ms:.1f}ms | {c.facts_count} facts</span>
                    </div>
                    <div class="meta-row"><span class="meta-label">Query Sent:</span><span><code>{html_lib.escape(c.query_sent)}</code></span></div>
                    <div style="margin-top:6px;">
                        <span style="font-size:11px; color:var(--text-muted); font-weight:600;">FACTS / ARTIFACTS RETURNED:</span>
                        <div class="content-box">{html_lib.escape(facts_str)}</div>
                    </div>
                </div>
                """
            if not conn_cards:
                conn_cards = '<span style="color:var(--text-muted); font-style:italic;">No external connectors queried.</span>'

            # Pipeline trace breadcrumbs
            pipe_items = []
            for p in r.pipeline_trace:
                dec = f" <em>({html_lib.escape(p.routing_decision)})</em>" if p.routing_decision else ""
                pipe_items.append(f'<span class="breadcrumb-item">{html_lib.escape(p.node)} ({p.duration_ms:.1f}ms){dec}</span>')
            pipe_html = " ➔ ".join(pipe_items) if pipe_items else "Direct Execution"

            to_str = ", ".join(r.to_recipients) if r.to_recipients else "None"
            cc_str = ", ".join(r.cc_recipients) if r.cc_recipients else "None"

            html += f"""
        <details class="scenario-card" data-source="{html_lib.escape(r.entry_point.lower())}">
            <summary class="scenario-header">
                <div style="display:flex; align-items:center; gap:10px; font-weight:600;">
                    <span class="badge-source">{html_lib.escape(r.entry_point)}</span>
                    <span class="badge-mode">{'DRY_RUN' if r.dry_run else 'LIVE'}</span>
                    <code>{html_lib.escape(r.gmail_id or f'msg_{idx+1}')}</code>
                    <span>{html_lib.escape(r.subject)}</span>
                </div>
                <div style="display:flex; gap:10px; align-items:center;">
                    <span class="badge-mode">{html_lib.escape(r.category)}</span>
                    <span style="font-weight:700; font-size:13px; color:var(--accent);">{r.execution_time_seconds:.2f}s</span>
                </div>
            </summary>
            <div class="scenario-body">
                <div class="tab-bar">
                    <button class="tab-btn active" onclick="switchTab('{cid}', 'packet')">✉️ Email Packet</button>
                    <button class="tab-btn" onclick="switchTab('{cid}', 'intel')">🧠 Intent & Ownership</button>
                    <button class="tab-btn" onclick="switchTab('{cid}', 'llm')">🤖 LLM Communications ({len(r.llm_communications)})</button>
                    <button class="tab-btn" onclick="switchTab('{cid}', 'connectors')">🔌 Connectors ({len(r.connector_communications)})</button>
                    <button class="tab-btn" onclick="switchTab('{cid}', 'trace')">🛣️ Pipeline Trace</button>
                    <button class="tab-btn" onclick="switchTab('{cid}', 'draft')">✍️ Draft & Actions</button>
                </div>

                <!-- Tab 1: Email Packet -->
                <div id="{cid}_packet" class="tab-pane active">
                    <div class="meta-row"><span class="meta-label">From:</span><span>{html_lib.escape(r.sender)}</span></div>
                    <div class="meta-row"><span class="meta-label">To:</span><span>{html_lib.escape(to_str)}</span></div>
                    <div class="meta-row"><span class="meta-label">Cc:</span><span>{html_lib.escape(cc_str)}</span></div>
                    <div class="meta-row"><span class="meta-label">Subject:</span><span><strong>{html_lib.escape(r.subject)}</strong></span></div>
                    <div style="margin-top:10px;">
                        <span style="font-weight:600; color:var(--text-muted); font-size:11px; text-transform:uppercase;">Verbatim Email Body:</span>
                        <div class="content-box">{html_lib.escape(r.body)}</div>
                    </div>
                </div>

                <!-- Tab 2: Intent & Ownership -->
                <div id="{cid}_intel" class="tab-pane">
                    <div class="meta-row"><span class="meta-label">Category:</span><span><strong>{html_lib.escape(r.category)}</strong></span></div>
                    <div class="meta-row"><span class="meta-label">Urgency Score:</span><span>{r.urgency_score} / 10</span></div>
                    <div class="meta-row"><span class="meta-label">Confidence:</span><span>{r.confidence_score}%</span></div>
                    <div class="meta-row"><span class="meta-label">Context Tags:</span><span>{tag_chips}</span></div>
                    <div class="meta-row"><span class="meta-label">Responsibility:</span><span><code>{html_lib.escape(r.responsibility_role)}</code></span></div>
                    <div class="meta-row"><span class="meta-label">Reasoning:</span><span><em>{html_lib.escape(r.ownership_reason or r.reasoning)}</em></span></div>
                </div>

                <!-- Tab 3: LLM Communications -->
                <div id="{cid}_llm" class="tab-pane">
                    {llm_cards}
                </div>

                <!-- Tab 4: Connector Communications -->
                <div id="{cid}_connectors" class="tab-pane">
                    {conn_cards}
                </div>

                <!-- Tab 5: Pipeline Trace -->
                <div id="{cid}_trace" class="tab-pane">
                    <div class="breadcrumb">{pipe_html}</div>
                </div>

                <!-- Tab 6: Draft & Actions -->
                <div id="{cid}_draft" class="tab-pane">
                    <span style="font-weight:600; color:var(--text-muted); font-size:11px; text-transform:uppercase;">Verbatim Generated Draft:</span>
                    <div class="content-box">{html_lib.escape(r.enriched_draft_reply or 'Draft was suppressed')}</div>
                </div>
            </div>
        </details>
            """

        html += """
    </div>
</div>

<script>
    function switchTab(cardId, tabName) {
        const card = document.getElementById(cardId + '_' + tabName).closest('.scenario-body');
        card.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        card.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
        event.target.classList.add('active');
        document.getElementById(cardId + '_' + tabName).classList.add('active');
    }

    function filterSource(source) {
        document.querySelectorAll('.btn').forEach(b => b.classList.remove('active'));
        event.target.classList.add('active');
        const cards = document.querySelectorAll('.scenario-card');
        cards.forEach(card => {
            if (source === 'all') {
                card.style.display = 'block';
            } else {
                card.style.display = card.getAttribute('data-source') === source ? 'block' : 'none';
            }
        });
    }

    function searchCards() {
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
    def generate_master_index(parts_meta: List[Dict[str, Any]], output_path: str) -> str:
        """Generates audit_logs/index.html linking to all partitions."""
        total_parts = len(parts_meta)
        total_emails = sum(p["count"] for p in parts_meta)

        rows = ""
        for p in parts_meta:
            sources_str = ", ".join(p.get("sources", []))
            rows += f"""
            <tr>
                <td><a href="{p['html_file']}" style="color:#38bdf8; font-weight:700;">Part {p['partition_number']:04d}</a></td>
                <td>{p['count']} emails</td>
                <td><span style="background:#1e3a8a; color:#93c5fd; padding:2px 8px; border-radius:4px; font-size:12px;">{sources_str}</span></td>
                <td style="color:#94a3b8; font-size:13px;">{p.get('start_timestamp', '')}</td>
                <td><a href="{p['json_file']}" style="color:#94a3b8; font-size:12px;">Download JSON</a></td>
            </tr>
            """

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>MailOrganizer — Audit Reports Master Catalog</title>
    <style>
        body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:#0b1120; color:#f8fafc; margin:0; padding:32px; }}
        .container {{ max-width:1000px; margin:0 auto; }}
        table {{ width:100%; border-collapse:collapse; margin-top:20px; background:#1e293b; border-radius:8px; overflow:hidden; }}
        th, td {{ padding:12px 16px; border-bottom:1px solid #334155; text-align:left; }}
        th {{ background:#0f172a; color:#94a3b8; text-transform:uppercase; font-size:11px; }}
    </style>
</head>
<body>
<div class="container">
    <h1>MailOrganizer • Master Audit Catalog</h1>
    <p style="color:#94a3b8;">Total Partitions: {total_parts} | Total Audited Emails: {total_emails}</p>
    <table>
        <thead><tr><th>Partition</th><th>Volume</th><th>Sources</th><th>Created At</th><th>Data</th></tr></thead>
        <tbody>{rows}</tbody>
    </table>
</div>
</body>
</html>
"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return output_path
