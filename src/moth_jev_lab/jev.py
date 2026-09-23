"""Minimal JEV client (stdlib only) + raw-response capture.

The fleet's Cloudflare proxy at ai-writings.pages.dev holds the upstream
key; this client adds nothing but transport and the receipt hook: every
raw response is returned verbatim so callers can seal it. Numbers are
re-derived from sealed bytes, never re-typed.
"""
from __future__ import annotations

import json
import urllib.request

ENDPOINT = "https://ai-writings.pages.dev/api/jev/decide"
MODEL = "jev-latest"
USER_AGENT = "moth-jev-lab/0.1.0"
TIMEOUT_S = 60


class JevTransportError(RuntimeError):
    pass


def decide(state: str, questions: dict, *, model: str = MODEL,
           endpoint: str = ENDPOINT) -> dict:
    """One decide call. Returns the UNWRAPPED body (answers + usage).

    The raw HTTP bytes are hashed by the caller via decide_raw; here we
    parse for convenience. Any caller sealing receipts must use
    decide_raw and seal `raw_bytes`, not this parsed view."""
    raw = decide_raw(state, questions, model=model, endpoint=endpoint)
    body = json.loads(raw)
    return body.get("body", body)


def decide_raw(state: str, questions: dict, *, model: str = MODEL,
               endpoint: str = ENDPOINT) -> str:
    """Raw response BYTES (str). Sealed into receipts; re-parsed by the
    experiment. A transport failure raises — refusals are booked by the
    caller, never fabricated here."""
    payload = json.dumps({"model": model, "state": state,
                          "questions": questions}).encode()
    req = urllib.request.Request(endpoint, data=payload, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return resp.read().decode()
    except Exception as exc:  # network truth becomes a refusal row upstream
        raise JevTransportError(f"{type(exc).__name__}: {exc}") from exc
