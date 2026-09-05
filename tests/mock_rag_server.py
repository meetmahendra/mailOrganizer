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
Local Mock HTTP Enterprise RAG Service.

Implements the standard enterprise RAG REST contract on 127.0.0.1:8005.
Receives real HTTP POST requests from RAGConnector, tests socket connections,
and returns realistic contextual facts without hitting internet DNS.
"""
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional, Tuple


# Knowledge Base mapping topic keywords to enterprise facts
KNOWLEDGE_BASE = {
    "eng": [
        "Production topology review SLA: 48 hours.",
        "Architecture Guild requirement: CTO approval for multi-region clusters.",
        "Kafka migration: Expected 40% latency reduction on event ingestion.",
        "Project Odyssey: Cloud Migration & Modernization lead is David Miller (david.miller@yourcompany.com).",
    ],
    "legal": [
        "Legal Department Contact: Rachel Green (rachel.green@yourcompany.com), Lead Compliance Counsel.",
        "GDPR Article 28 requires standard contractual clauses for external subprocessors.",
        "Mutual Non-Disclosure Agreement (MNDA) standard turnaround is 2 business days.",
    ],
    "hr": [
        "Executive Band 9 compensation ceiling: $325k base, 50k RSUs.",
        "Annual benefits open enrollment deadline: November 15 at midnight.",
        "Standard PTO rollover policy: Maximum 5 accrued days carry over to Q1.",
    ],
}


class MockRAGRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler implementing the enterprise RAG /v1/query contract."""

    def log_message(self, format, *args):
        # Silence default per-request HTTP access logs to keep console clean
        pass

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "healthy"}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            body = json.loads(raw_body.decode("utf-8"))
        except Exception:
            body = {}

        query = body.get("query", "").lower()
        path = self.path.lower()

        # Route to appropriate domain facts
        results = []
        if "eng" in path or any(k in query for k in ["topology", "architecture", "cluster", "kafka", "odyssey", "sla"]):
            results.extend(KNOWLEDGE_BASE["eng"])
        elif "legal" in path or any(k in query for k in ["dpa", "gdpr", "nda", "compliance", "subpoena", "contract"]):
            results.extend(KNOWLEDGE_BASE["legal"])
        elif "hr" in path or any(k in query for k in ["offer", "compensation", "salary", "benefits", "pto", "candidate"]):
            results.extend(KNOWLEDGE_BASE["hr"])
        else:
            results = [
                "TechGlobal Cloud Solutions standard operational policies apply.",
                "Review SLA for customer communications is 24 hours.",
            ]

        # Handle feedback/modify endpoint
        if "feedback" in path or "modify" in path:
            response_data = {"status": "success", "message": "Feedback recorded"}
        else:
            # Handle query endpoint
            response_data = {
                "results": results[:body.get("top_k", 3)],
                "total_matched": len(results),
            }

        response_bytes = json.dumps(response_data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)


def is_port_in_use(port: int = 8005) -> bool:
    """Check if the mock server port is already occupied."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_mock_rag_server(port: int = 8005) -> Tuple[Optional[ThreadingHTTPServer], Optional[threading.Thread]]:
    """Start the mock RAG server in a daemon background thread if not already running."""
    if is_port_in_use(port):
        return None, None

    server = ThreadingHTTPServer(("127.0.0.1", port), MockRAGRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


if __name__ == "__main__":
    port = 8005
    print(f"[*] Starting Mock Enterprise RAG HTTP Server on http://127.0.0.1:{port}...")
    server = ThreadingHTTPServer(("127.0.0.1", port), MockRAGRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down mock RAG server.")
        server.server_close()
