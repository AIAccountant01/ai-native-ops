# Webhook trigger

An outside system can start a bot automation by POSTing a signed JSON body to `/webhook`. The receiver checks the signature, rejects replays, and appends one log line per request. The log stores a timestamp, the caller IP, the status, and a short detail. It leaves out the secret and the full `data` object.

## What gets checked

The sender signs the raw body. Three headers come with the request:

- `X-Webhook-Timestamp`: unix time in seconds
- `X-Webhook-Nonce`: a unique string
- `X-Webhook-Signature`: hex HMAC-SHA256 of the secret over `"{timestamp}.{nonce}."` plus the raw body

The HMAC proves the caller knows the secret, so there is no second shared-secret header. A request older than 300 seconds, or more than 60 seconds ahead, is rejected. A nonce is stored only after the signature matches, and a repeat of that nonce is rejected. The JSON body must include `action` (string), `bot_name` (string), and `data`. Bodies over 64 KB are refused.

## Run it

```bash
cd webhook-trigger
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export WEBHOOK_SECRET=yourvalue
python app.py
```

The receiver listens on `http://127.0.0.1:5000/webhook`. Log lines go to `webhook.log` in the working directory.

## End-to-end test with a dry run

Dry run builds a real signed request, prints the URL, the headers (signature included), and the body, and does not send it. The secret stays off the screen.

```bash
export WEBHOOK_URL=http://127.0.0.1:5000/webhook
export WEBHOOK_SECRET=yourvalue
WEBHOOK_DRY_RUN=1 python sign_request.py
```

The printed body defaults to `{"action": "test", "bot_name": "sender-test", "data": {"ping": true}}`. Pass a JSON file path to use another payload: `python sign_request.py path/to/event.json`.

With the receiver still running, drop the dry-run flag to deliver that same request:

```bash
python sign_request.py
```

Automated checks:

```bash
pytest
```

## Clock skew

A signature is accepted only when its timestamp is within the last 300 seconds and no more than 60 seconds in the future. A fresh request that comes back 401 usually means the two clocks disagree. Sync both with NTP and sign again.

## Several instances

Swap the in-process nonce cache for Redis (`SET NX` with an expiry of a few minutes) when you run more than one instance.
