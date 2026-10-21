"""POST /webhook receiver for bot automations.

Auth is the HMAC checked by replay_guard. The signature proves the secret,
so there is no separate shared-secret header.
"""

import json
import os
import threading
from datetime import datetime, timezone

from flask import Flask, request
from werkzeug.exceptions import RequestEntityTooLarge

from replay_guard import ReplayError, check_replay

MAX_CONTENT_LENGTH = 64 * 1024
_log_lock = threading.Lock()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH


def _log(status, detail):
    record = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ip": request.remote_addr or "",
        "status": status,
        "detail": " ".join(str(detail).split())[:120],
    }
    path = os.environ.get("WEBHOOK_LOG", "webhook.log")
    line = json.dumps(record) + "\n"
    with _log_lock:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line)


def _fail(status, detail):
    _log(status, detail)
    return {"ok": False, "error": detail}, status


def _payload_error(payload):
    if not isinstance(payload, dict):
        return "missing fields"
    if any(key not in payload for key in ("action", "bot_name", "data")):
        return "missing fields"
    if not isinstance(payload["action"], str) or not isinstance(payload["bot_name"], str):
        return "missing fields"
    return None


@app.post("/webhook")
def webhook():
    secret = os.environ.get("WEBHOOK_SECRET", "")
    if not secret:
        return _fail(401, "unauthorized")
    length = request.content_length
    if length is not None and length > MAX_CONTENT_LENGTH:
        return _fail(413, "payload too large")
    try:
        check_replay(request, secret)
    except ReplayError as exc:
        return _fail(exc.status, exc.detail)
    except RequestEntityTooLarge:
        return _fail(413, "payload too large")
    try:
        payload = json.loads(request.get_data(cache=True).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _fail(400, "malformed json")
    problem = _payload_error(payload)
    if problem:
        return _fail(400, problem)
    _log(200, f"{payload['action']} {payload['bot_name']}")
    return {"ok": True, "received": True}, 200


@app.errorhandler(RequestEntityTooLarge)
def too_large(_err):
    return _fail(413, "payload too large")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
