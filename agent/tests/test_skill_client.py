from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "skill"
    / "jingao-esports-knowledge"
    / "scripts"
    / "jingao_knowledge.py"
)


def test_skill_workflows_use_authenticated_current_api() -> None:
    """The distributed Skill must only exercise currently shipped routes."""

    requests: list[tuple[str, str, dict | None, str | None]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args) -> None:
            return

        def _write(self, payload: dict | list, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            requests.append(
                ("GET", self.path, None, self.headers.get("Authorization"))
            )
            if self.path == "/v1/categories":
                self._write(
                    [{"key": "training", "name": "Training", "active": True}]
                )
                return
            if self.path == "/v1/projects":
                self._write([{"id": "project-1", "name": "高校电竞培训"}])
                return
            if self.path == "/v1/projects/project-1":
                self._write(
                    {
                        "id": "project-1",
                        "name": "高校电竞培训",
                        "has_closing_report": True,
                        "closing_report_reminder": False,
                        "documents": [],
                    }
                )
                return
            self._write({"detail": "not found"}, status=404)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            payload = json.loads(body.decode("utf-8")) if body else None
            requests.append(
                ("POST", self.path, payload, self.headers.get("Authorization"))
            )
            if self.path == "/v1/writing/draft":
                self._write(
                    {
                        "draft": "Grounded draft [S1]",
                        "sources": [{"document_id": "document-1", "page": 1}],
                        "generation_mode": "llm",
                    }
                )
                return
            self._write({"detail": "not found"}, status=404)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = os.environ.copy()
    env["JINGAO_KB_URL"] = f"http://127.0.0.1:{server.server_port}"
    env["JINGAO_KB_TOKEN"] = "test-token"
    env["PYTHONIOENCODING"] = "utf-8"

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    try:
        categories = run("categories")
        writing = run(
            "writing",
            "Create a sourced project summary",
            "--category",
            "training",
            "--scope",
            "history",
        )
        viewed = run("project", "高校电竞培训")
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert categories.returncode == 0
    assert json.loads(categories.stdout)[0]["key"] == "training"
    assert writing.returncode == 0
    assert json.loads(writing.stdout)["generation_mode"] == "llm"
    assert viewed.returncode == 0
    assert json.loads(viewed.stdout)["id"] == "project-1"
    assert all(request[3] == "Bearer test-token" for request in requests)
    assert (
        "POST",
        "/v1/writing/draft",
        {
            "instruction": "Create a sourced project summary",
            "scope": "history",
            "category": "training",
        },
        "Bearer test-token",
    ) in requests
    assert not any("/v1/evolution/" in request[1] for request in requests)
