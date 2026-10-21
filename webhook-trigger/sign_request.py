"""Sign a JSON body and POST it to a webhook receiver.

WEBHOOK_DRY_RUN=1 prints the URL, headers and body, and does not send anything.
The secret is never printed. The signature header is.
"""

import json
import os
import sys
import urllib.request

from replay_guard import sign

DEFAULT_PAYLOAD = {"action": "test", "bot_name": "sender-test", "data": {"ping": True}}


def build_headers(secret, body_bytes, extra_headers=None):
    headers = {"Content-Type": "application/json"}
    headers.update(sign(secret, body_bytes))
    if extra_headers:
        headers.update(extra_headers)
    return headers


class _Response:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def getcode(self):
        return self.status


def post_webhook(url, secret, payload_dict, timeout=10):
    """Encode payload_dict once and send those exact bytes."""
    body = json.dumps(payload_dict).encode("utf-8")
    headers = build_headers(secret, body)
    if os.environ.get("WEBHOOK_DRY_RUN") == "1":
        print(url)
        for key, value in headers.items():
            print(f"{key}: {value}")
        print(body.decode("utf-8"))
        return _Response(200, b'{"ok": true, "received": true}')
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    return urllib.request.urlopen(request, timeout=timeout)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    url = os.environ.get("WEBHOOK_URL")
    secret = os.environ.get("WEBHOOK_SECRET")
    if not url or not secret:
        print("Set WEBHOOK_URL and WEBHOOK_SECRET.", file=sys.stderr)
        return 1
    if args:
        with open(args[0], encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        payload = DEFAULT_PAYLOAD
    response = post_webhook(url, secret, payload)
    status = getattr(response, "status", None)
    if status is None:
        status = response.getcode()
    print(status)
    sys.stdout.write(response.read().decode("utf-8"))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
