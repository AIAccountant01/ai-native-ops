"""Timestamped HMAC signatures and a nonce cache for webhook replay protection.

The signature is hex HMAC-SHA256(secret, f"{timestamp}.{nonce}.".encode() + raw_body).
A valid signature proves the caller knows the secret.
"""

import hashlib
import hmac
import secrets
import threading
import time
from collections import OrderedDict

HEADER_TIMESTAMP = "X-Webhook-Timestamp"
HEADER_NONCE = "X-Webhook-Nonce"
HEADER_SIGNATURE = "X-Webhook-Signature"

MAX_AGE_SECONDS = 300
MAX_FUTURE_SECONDS = 60
NONCE_CACHE_MAX = 10_000


class ReplayError(Exception):
    """Raised when a webhook fails the timestamp, signature, or nonce check."""

    status = 401

    def __init__(self, detail):
        super().__init__(detail)
        self.detail = detail
        self.status = 401


class NonceCache:
    """Thread-safe LRU of nonces that have already been accepted."""

    def __init__(self, max_size=NONCE_CACHE_MAX):
        self.max_size = max_size
        self._lock = threading.Lock()
        self._items = OrderedDict()

    def add(self, nonce):
        """Record nonce. Return False if it was already present."""
        with self._lock:
            if nonce in self._items:
                return False
            self._items[nonce] = None
            while len(self._items) > self.max_size:
                self._items.popitem(last=False)
            return True

    def clear(self):
        with self._lock:
            self._items.clear()


nonce_cache = NonceCache()


def _header(headers, name):
    if not headers:
        return None
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() == wanted and value not in (None, ""):
            return value
    return None


def _as_bytes(body):
    if body is None:
        return b""
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8")
    return bytes(body)


def _key(secret):
    return secret.encode("utf-8") if isinstance(secret, str) else secret


def _signature(secret, timestamp, nonce, body):
    message = f"{timestamp}.{nonce}.".encode("utf-8") + body
    return hmac.new(_key(secret), message, hashlib.sha256).hexdigest()


def sign(secret, body, timestamp=None, nonce=None):
    """Return the three webhook headers for this raw body."""
    body = _as_bytes(body)
    ts = int(time.time()) if timestamp is None else int(timestamp)
    nonce = secrets.token_hex(16) if nonce is None else str(nonce)
    return {
        HEADER_TIMESTAMP: str(ts),
        HEADER_NONCE: nonce,
        HEADER_SIGNATURE: _signature(secret, ts, nonce, body),
    }


def verify(headers, body, secret):
    """Raise ReplayError if headers do not authenticate this raw body.

    The nonce is stored only after the signature matches.
    """
    body = _as_bytes(body)
    ts_raw = _header(headers, HEADER_TIMESTAMP)
    nonce = _header(headers, HEADER_NONCE)
    provided = _header(headers, HEADER_SIGNATURE)
    if ts_raw is None or nonce is None or provided is None:
        raise ReplayError("missing signature headers")
    try:
        timestamp = int(str(ts_raw).strip())
    except (TypeError, ValueError):
        raise ReplayError("bad timestamp") from None
    nonce = str(nonce)
    now = time.time()
    if timestamp < now - MAX_AGE_SECONDS:
        raise ReplayError("stale timestamp")
    if timestamp > now + MAX_FUTURE_SECONDS:
        raise ReplayError("timestamp too far in the future")
    expected = _signature(secret, timestamp, nonce, body)
    provided = str(provided).strip()
    try:
        matches = hmac.compare_digest(expected, provided)
    except (TypeError, ValueError):
        matches = False
    if not matches:
        raise ReplayError("bad signature")
    if not nonce_cache.add(nonce):
        raise ReplayError("replayed nonce")


def check_replay(request, secret):
    """Flask adapter. Raise ReplayError with status 401."""
    verify(request.headers, request.get_data(cache=True), secret)
