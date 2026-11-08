"""scripts/smoke_test.py (DLBS-42): waits for /health, and for the new version after a deploy."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scripts.smoke_test import check, main, wait_until_healthy


def serve(status=200, body=None, version="abc123"):
    """Start a local server that answers /health like the app does."""

    class Health(BaseHTTPRequestHandler):
        def do_GET(self):
            payload = json.dumps({"status": "ok"} if body is None else body).encode()
            self.send_response(status if self.path == "/health" else 404)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-App-Version", version)
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


@pytest.fixture
def healthy_app():
    server, url = serve()
    yield url
    server.shutdown()


def test_healthy_app_passes(healthy_app):
    assert check(healthy_app) == (True, f"{healthy_app}/health: healthy, version abc123")


def test_trailing_slash_is_allowed(healthy_app):
    assert check(healthy_app + "/")[0]


def test_old_version_is_not_enough(healthy_app):
    healthy, message = check(healthy_app, version="def456")

    assert not healthy
    assert "still serving version abc123" in message


def test_new_version_passes(healthy_app):
    assert check(healthy_app, version="abc123")[0]


def test_error_status_fails():
    server, url = serve(status=503)
    try:
        assert not check(url)[0]
    finally:
        server.shutdown()


def test_unexpected_body_fails():
    server, url = serve(body={"status": "starting"})
    try:
        healthy, message = check(url)
    finally:
        server.shutdown()

    assert not healthy
    assert "unexpected answer" in message


def test_no_server_fails():
    assert not check("http://127.0.0.1:9", timeout=2)[0]


def test_waits_until_healthy():
    answers = iter([(False, "starting"), (False, "starting"), (True, "healthy")])
    sleeps = []

    assert wait_until_healthy("http://app", timeout=60, interval=5,
                              probe=lambda url, version: next(answers),
                              sleep=sleeps.append, clock=lambda: 0)
    assert sleeps == [5, 5]


def test_gives_up_after_timeout():
    now = [0.0]

    def sleep(seconds):
        now[0] += seconds

    assert not wait_until_healthy("http://app", timeout=30, interval=10,
                                  probe=lambda url, version: (False, "down"),
                                  sleep=sleep, clock=lambda: now[0])
    assert now[0] == 30


def test_command_exit_codes(healthy_app):
    assert main([healthy_app, "--version", "abc123"]) == 0
    assert main([healthy_app, "--version", "def456", "--timeout", "0"]) == 1
