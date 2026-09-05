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
Centralized Audit Manager with 100-email file auto-partitioning.
"""
import os
import csv
import json
import glob
import re
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from pipeline.audit_schema import (
    AuditRecord,
    LLMCommunication,
    ConnectorCommunication,
    PipelineNodeTrace,
)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AUDIT_DIR = os.path.normpath(os.path.join(_PROJECT_ROOT, "audit_logs"))
HTML_DIR = os.path.join(AUDIT_DIR, "html")
JSON_DIR = os.path.join(AUDIT_DIR, "json")
AUDIT_CSV = os.path.join(AUDIT_DIR, "audit_log.csv")
ROOT_CSV = os.path.join(_PROJECT_ROOT, "audit_log.csv")

PARTITION_SIZE = 100


class AuditManager:
    """Thread-safe singleton managing audit log records, rotation, and reports."""
    _instance: Optional["AuditManager"] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "AuditManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        os.makedirs(HTML_DIR, exist_ok=True)
        os.makedirs(JSON_DIR, exist_ok=True)

    def record_email(self, state: Dict[str, Any]) -> None:
        """
        Convert EmailState to an AuditRecord, append to active partition,
        and rotate if partition reaches 100 emails.
        """
        with self._lock:
            try:
                record = self._build_audit_record(state)
                part_num, part_records = self._append_to_partition(record)
                
                # Regenerate HTML dashboard for this partition
                from pipeline.reporters.audit_dashboard import AuditDashboardReporter
                html_path = os.path.join(HTML_DIR, f"audit_report_part_{part_num:04d}.html")
                AuditDashboardReporter.generate_partition_html(part_records, html_path, part_num)

                # Update master index
                self._update_master_index()

                # Sync CSV
                self._write_csv_summary(record)

            except Exception as e:
                print(f"[AuditManager] Warning: Failed to record audit log: {e}")

    def _build_audit_record(self, state: Dict[str, Any]) -> AuditRecord:
        """Construct a validated AuditRecord from state."""
        start_time = state.get("pipeline_start_time")
        duration = (datetime.now(timezone.utc).timestamp() - start_time) if start_time else 0.0

        # Parse LLM communications
        llm_comms = []
        for c in state.get("llm_communications", []):
            if isinstance(c, dict):
                llm_comms.append(LLMCommunication(**c))
            elif isinstance(c, LLMCommunication):
                llm_comms.append(c)

        # Parse Connector communications
        conn_comms = []
        for c in state.get("connector_communications", []):
            if isinstance(c, dict):
                conn_comms.append(ConnectorCommunication(**c))
            elif isinstance(c, ConnectorCommunication):
                conn_comms.append(c)

        # Parse Pipeline node trace
        pipe_trace = []
        for t in state.get("pipeline_trace", []):
            if isinstance(t, dict):
                pipe_trace.append(PipelineNodeTrace(**t))
            elif isinstance(t, PipelineNodeTrace):
                pipe_trace.append(t)

        return AuditRecord(
            entry_point=state.get("entry_point", "DRY_RUN"),
            dry_run=state.get("dry_run", True),
            timestamp=datetime.now(timezone.utc).isoformat(),
            execution_time_seconds=duration,
            gmail_id=state.get("gmail_id", ""),
            thread_id=state.get("thread_id", ""),
            message_id_header=state.get("message_id_header", ""),
            sender=state.get("sender", ""),
            to_recipients=state.get("to_recipients", []) or [],
            cc_recipients=state.get("cc_recipients", []) or [],
            subject=state.get("subject", ""),
            body=state.get("body", "") or "",
            snippet=state.get("snippet", "") or "",
            category=state.get("category", ""),
            urgency_score=state.get("urgency_score", 0) or 0,
            confidence_score=state.get("confidence_score", 0) or 0,
            reasoning=state.get("reasoning", "") or "",
            context_tags=state.get("context_tags", []) or [],
            is_reply_necessary=state.get("is_reply_necessary", False) or False,
            reply_necessity_reason=state.get("reply_necessity_reason", "") or "",
            is_vip=state.get("is_vip", False) or False,
            is_no_reply=state.get("is_no_reply", False) or False,
            responsibility_role=state.get("responsibility_role", "PRIMARY_ACTIONEE"),
            ownership_reason=state.get("ownership_reason", "") or "",
            delegation_target=state.get("delegation_target"),
            retrieved_facts=state.get("retrieved_facts", "") or "",
            calendar_context=state.get("calendar_context", "") or "",
            planned_actions=state.get("gmail_actions", []) or [],
            actions_taken=state.get("actions_taken", []) or [],
            enriched_draft_reply=state.get("enriched_draft_reply", "") or "",
            pending_pm_tasks=state.get("pending_pm_tasks", []) or [],
            pending_mutations=state.get("pending_mutations", []) or [],
            llm_communications=llm_comms,
            connector_communications=conn_comms,
            pipeline_trace=pipe_trace,
        )

    def _append_to_partition(self, record: AuditRecord) -> tuple[int, List[AuditRecord]]:
        """Append to the current partition JSON; rotate if current count == 100."""
        part_num = self._get_active_partition_number()
        json_path = os.path.join(JSON_DIR, f"audit_report_part_{part_num:04d}.json")

        records: List[Dict[str, Any]] = []
        if os.path.isfile(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    records = json.load(f)
            except Exception:
                records = []

        if len(records) >= PARTITION_SIZE:
            part_num += 1
            json_path = os.path.join(JSON_DIR, f"audit_report_part_{part_num:04d}.json")
            records = []

        records.append(record.model_dump())

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)

        return part_num, [AuditRecord(**r) for r in records]

    def _get_active_partition_number(self) -> int:
        """Find the latest partition index from json directory."""
        files = glob.glob(os.path.join(JSON_DIR, "audit_report_part_*.json"))
        if not files:
            return 1
        numbers = []
        for f in files:
            match = re.search(r"audit_report_part_(\d+)\.json", os.path.basename(f))
            if match:
                numbers.append(int(match.group(1)))
        return max(numbers) if numbers else 1

    def _update_master_index(self) -> None:
        """Generate/update audit_logs/index.html linking to all partitions."""
        from pipeline.reporters.audit_dashboard import AuditDashboardReporter
        parts_meta = []
        json_files = sorted(glob.glob(os.path.join(JSON_DIR, "audit_report_part_*.json")))
        for jf in json_files:
            match = re.search(r"audit_report_part_(\d+)\.json", os.path.basename(jf))
            if not match:
                continue
            p_num = int(match.group(1))
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    count = len(data)
                    sources = list({r.get("entry_point", "UNKNOWN") for r in data})
                    start_ts = data[0].get("timestamp", "") if data else ""
                    end_ts = data[-1].get("timestamp", "") if data else ""
                    parts_meta.append({
                        "partition_number": p_num,
                        "count": count,
                        "sources": sources,
                        "start_timestamp": start_ts,
                        "end_timestamp": end_ts,
                        "html_file": f"html/audit_report_part_{p_num:04d}.html",
                        "json_file": f"json/audit_report_part_{p_num:04d}.json",
                    })
            except Exception:
                continue

        index_path = os.path.join(AUDIT_DIR, "index.html")
        AuditDashboardReporter.generate_master_index(parts_meta, index_path)

    def _write_csv_summary(self, record: AuditRecord) -> None:
        """Sync row to both audit_logs/audit_log.csv and root audit_log.csv."""
        fieldnames = [
            "timestamp",
            "entry_point",
            "dry_run",
            "gmail_id",
            "subject",
            "sender",
            "is_no_reply",
            "is_vip",
            "category",
            "urgency_score",
            "confidence_score",
            "reasoning",
            "is_reply_necessary",
            "reply_necessity_reason",
            "context_tags",
            "suggested_reply_preview",
            "planned_actions",
            "actions_taken",
            "calendar_context",
        ]

        def _fmt_acts(acts):
            parts = []
            for a in acts:
                lbl = a.get("label", "")
                st = a.get("status", "")
                base = a.get("action", "")
                parts.append(f"{base}({lbl})[{st}]" if lbl else f"{base}[{st}]")
            return " | ".join(parts)

        row = {
            "timestamp": record.timestamp,
            "entry_point": record.entry_point,
            "dry_run": record.dry_run,
            "gmail_id": record.gmail_id,
            "subject": record.subject,
            "sender": record.sender,
            "is_no_reply": record.is_no_reply,
            "is_vip": record.is_vip,
            "category": record.category,
            "urgency_score": record.urgency_score,
            "confidence_score": record.confidence_score,
            "reasoning": record.reasoning[:200],
            "is_reply_necessary": record.is_reply_necessary,
            "reply_necessity_reason": record.reply_necessity_reason[:200],
            "context_tags": "; ".join(record.context_tags),
            "suggested_reply_preview": record.enriched_draft_reply[:300],
            "planned_actions": _fmt_acts(record.planned_actions),
            "actions_taken": _fmt_acts(record.actions_taken),
            "calendar_context": record.calendar_context[:200],
        }

        for path in [AUDIT_CSV, ROOT_CSV]:
            file_exists = os.path.isfile(path)
            with open(path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row)
