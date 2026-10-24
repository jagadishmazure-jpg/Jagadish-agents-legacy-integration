"""API facade: the COBOL inquiry programs exposed as a small REST API (stdlib only)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from .cobol import LegacyUnavailable
from .gateway import LegacyGateway, ValidationError
from .guards import CircuitOpen, RateLimited, mask_obj


def make_handler(gw: LegacyGateway):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep request lines (and ids) out of stderr
            pass

        def _send(self, code: int, body: dict, headers: dict | None = None):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            parts = [p for p in self.path.split("?")[0].split("/") if p]
            try:
                if parts == ["health"]:
                    return self._send(200, {"breaker": gw.breaker.state})
                if len(parts) == 2 and parts[0] in ("accounts", "policies"):
                    rec = gw.get_account(parts[1]) if parts[0] == "accounts" else gw.get_policy(parts[1])
                    if rec is None:
                        return self._send(404, {"error": "not found"})
                    return self._send(200, mask_obj(rec))
                return self._send(404, {"error": "no such route"})
            except ValidationError as exc:
                return self._send(400, {"error": str(exc)})
            except RateLimited:
                return self._send(429, {"error": "rate limited"}, {"Retry-After": "1"})
            except (LegacyUnavailable, CircuitOpen):
                return self._send(503, {"error": "legacy system unavailable"}, {"Retry-After": "30"})

    return Handler


class Facade:
    def __init__(self, gw: LegacyGateway, port: int = 0):
        self.server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(gw))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def get_json(url: str, timeout: float = 5.0) -> tuple[int, dict]:
    if not url.startswith("http://127.0.0.1:"):
        raise ValueError("facade client only talks to the local facade")
    try:
        with urlopen(url, timeout=timeout) as r:  # noqa: S310 - scheme and host checked above
            return r.status, json.loads(r.read())
    except HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")
    except URLError as e:
        return 503, {"error": f"facade unreachable: {type(e.reason).__name__}"}
