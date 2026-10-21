"""Receiver tests: auth, replay window, payload shape, and size."""

import json
import os
import time
from pathlib import Path

import pytest

import app as app_module
from replay_guard import nonce_cache, sign
from sign_request import post_webhook

SECRET = "yourvalue"
PAYLOAD = {"action": "run", "bot_name": "demo", "data": {"ping": True}}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("WEBHOOK_LOG", str(tmp_path / "webhook.log"))
    monkeypatch.delenv("WEBHOOK_DRY_RUN", raising=False)
    nonce_cache.clear()


@pytest.fixture
def client():
    return app_module.app.test_client()


def _post(client, body, headers):
    return client.post("/webhook", data=body, headers=headers)


def test_valid_request(client):
    body = json.dumps(PAYLOAD).encode()
    response = _post(client, body, sign(SECRET, body))
    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "received": True}
    log = Path(os.environ["WEBHOOK_LOG"]).read_text(encoding="utf-8")
    record = json.loads(log.strip())
    assert record["status"] == 200
    assert record["detail"] == "run demo"
    assert SECRET not in log
    assert "ping" not in log


def test_bad_signature(client):
    body = json.dumps(PAYLOAD).encode()
    headers = sign(SECRET, body)
    bad = dict(headers)
    bad["X-Webhook-Signature"] = "0" * 64
    assert _post(client, body, bad).status_code == 401
    assert _post(client, body, headers).status_code == 200


def test_stale_and_future_timestamps(client):
    body = json.dumps(PAYLOAD).encode()
    now = int(time.time())
    stale = sign(SECRET, body, timestamp=now - 301)
    future = sign(SECRET, body, timestamp=now + 61)
    assert _post(client, body, stale).status_code == 401
    assert _post(client, body, future).status_code == 401


def test_replayed_nonce(client):
    body = json.dumps(PAYLOAD).encode()
    headers = sign(SECRET, body)
    assert _post(client, body, headers).status_code == 200
    assert _post(client, body, headers).status_code == 401


def test_malformed_json(client):
    body = b"not-json"
    assert _post(client, body, sign(SECRET, body)).status_code == 400


def test_missing_fields(client):
    payloads = (
        {"bot_name": "demo", "data": {}},
        {"action": "run", "data": {}},
        {"action": "run", "bot_name": "demo"},
        {"action": 1, "bot_name": "demo", "data": {}},
    )
    for payload in payloads:
        body = json.dumps(payload).encode()
        assert _post(client, body, sign(SECRET, body)).status_code == 400


def test_oversize(client):
    body = b"x" * (app_module.MAX_CONTENT_LENGTH + 1)
    response = _post(client, body, sign(SECRET, body))
    assert response.status_code == 413


def test_dry_run_prints_signed_request(capsys, monkeypatch):
    monkeypatch.setenv("WEBHOOK_DRY_RUN", "1")
    response = post_webhook(
        "http://127.0.0.1:5000/webhook",
        SECRET,
        {"action": "test", "bot_name": "sender-test", "data": {"ping": True}},
    )
    assert response.status == 200
    assert response.getcode() == 200
    printed = capsys.readouterr().out
    assert "http://127.0.0.1:5000/webhook" in printed
    assert "X-Webhook-Signature:" in printed
    assert "sender-test" in printed
    assert SECRET not in printed


def test_post_webhook_sends_exact_signed_bytes(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=10):
        captured["data"] = request.data
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout

        class _Ok:
            status = 200

            def read(self):
                return b'{"ok": true, "received": true}'

            def getcode(self):
                return 200

        return _Ok()

    monkeypatch.setattr("sign_request.urllib.request.urlopen", fake_urlopen)
    payload = {"action": "test", "bot_name": "sender-test", "data": {"ping": True}}
    response = post_webhook("http://example.test/webhook", SECRET, payload, timeout=7)
    assert response.status == 200
    assert json.loads(captured["data"]) == payload
    assert captured["timeout"] == 7
    from replay_guard import verify

    verify(captured["headers"], captured["data"], SECRET)
