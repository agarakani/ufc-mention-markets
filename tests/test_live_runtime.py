import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from urllib.error import HTTPError

from scripts.live.dashboard_server import make_handler


def status_response(runtime=None, error=""):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lambda: runtime, lambda: error))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        try:
            response = urlopen(f"http://127.0.0.1:{server.server_port}/api/status")
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, json.load(response)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_status_does_not_claim_ready_while_models_are_loading():
    code, body = status_response()
    assert code == 503 and body["ok"] is False
    assert body["live_status"]["state"] == "starting"
    assert body["live_status"]["paper_enabled"] is False


def test_status_reports_startup_failure():
    code, body = status_response(error="corpus unavailable")
    assert code == 503 and body["live_status"]["state"] == "error"
    assert body["live_status"]["error"] == "corpus unavailable"


def test_status_uses_collector_state_not_saved_payload():
    class Runtime:
        def status(self):
            return {"state": "ready", "paper_enabled": True, "source": "local", "checked_at": "2099-01-01T00:00:00Z"}

    code, body = status_response(Runtime())
    assert code == 200 and body["ok"] is True
    assert body["live_status"]["checked_at"] == "2099-01-01T00:00:00Z"
