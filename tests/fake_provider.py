"""A local stand-in for a vision API, so the import feature is tested without network or keys."""

from __future__ import annotations

import contextlib
import json
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@dataclass
class Seen:
    path: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, object] = field(default_factory=dict)


@dataclass
class Fake:
    url: str
    seen: Seen
    reply: dict[str, object]


@contextlib.contextmanager
def serve() -> Iterator[Fake]:
    """Serve canned replies on localhost. Set ``fake.reply`` keys status, body, raw, delay."""
    seen = Seen()
    reply: dict[str, object] = {"status": 200, "body": {}, "delay": 0.0, "raw": None}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            seen.path = self.path
            seen.headers = {k.lower(): v for k, v in self.headers.items()}
            seen.body = json.loads(self.rfile.read(length))
            time.sleep(float(reply["delay"]))  # type: ignore[arg-type]
            raw = reply["raw"]
            payload = raw if isinstance(raw, bytes) else json.dumps(reply["body"]).encode()
            self.send_response(int(reply["status"]))  # type: ignore[call-overload]
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            with contextlib.suppress(OSError):
                self.wfile.write(payload)

        def log_message(self, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Fake(f"http://127.0.0.1:{server.server_address[1]}", seen, reply)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
