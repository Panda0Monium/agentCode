import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

sys.path.insert(0, "src")


class MockServer:
    def __init__(self):
        self._queue: list[tuple[int, dict]] = []
        self.request_count = 0
        self.request_times: list[float] = []
        self._lock = threading.Lock()
        self._server = HTTPServer(("127.0.0.1", 0), self._make_handler())
        self._port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def enqueue(self, status: int, body: dict | None = None) -> None:
        with self._lock:
            self._queue.append((status, body or {}))

    def reset(self) -> None:
        with self._lock:
            self._queue.clear()
            self.request_count = 0
            self.request_times.clear()

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass

            def _respond(self):
                with server._lock:
                    server.request_count += 1
                    server.request_times.append(time.monotonic())
                    status, body = server._queue.pop(0) if server._queue else (200, {})
                payload = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self): self._respond()

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                if length: self.rfile.read(length)
                self._respond()

        return Handler


@pytest.fixture
def mock_server():
    return MockServer()
