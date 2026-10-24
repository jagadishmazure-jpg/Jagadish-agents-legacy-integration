"""Cross-cutting protection for fragile legacy systems: rate limiting, circuit breaker, idempotency,
PII masking and an append-only audit log."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path


class RateLimited(RuntimeError):
    pass


class CircuitOpen(RuntimeError):
    pass


class TokenBucket:
    """Allows `rate` calls per second with bursts up to `burst`. Clock is injectable for tests."""

    def __init__(self, rate: float, burst: int, clock: Callable[[], float] = time.monotonic):
        if rate <= 0 or burst <= 0:
            raise ValueError("rate and burst must be positive")
        self.rate, self.burst, self.clock = rate, burst, clock
        self.tokens = float(burst)
        self.last = clock()
        self.lock = threading.Lock()
        self.rejected = 0

    def acquire(self) -> None:
        with self.lock:
            now = self.clock()
            self.tokens = min(self.burst, self.tokens + (now - self.last) * self.rate)
            self.last = now
            if self.tokens < 1:
                self.rejected += 1
                raise RateLimited("legacy call budget exhausted, retry later")
            self.tokens -= 1


class CircuitBreaker:
    """closed -> open after `threshold` consecutive failures; half-open after `cooldown` seconds lets
    one trial call through; success closes, failure re-opens."""

    def __init__(self, threshold: int = 5, cooldown: float = 30.0, clock: Callable[[], float] = time.monotonic):
        self.threshold, self.cooldown, self.clock = threshold, cooldown, clock
        self.state = "closed"
        self.failures = 0
        self.opened_at = 0.0
        self.short_circuited = 0

    def call(self, fn: Callable, *a, **kw):
        if self.state == "open":
            if self.clock() - self.opened_at >= self.cooldown:
                self.state = "half-open"
            else:
                self.short_circuited += 1
                raise CircuitOpen("legacy system marked unhealthy; not calling it")
        try:
            result = fn(*a, **kw)
        except Exception:
            self.failures += 1
            if self.state == "half-open" or self.failures >= self.threshold:
                self.state, self.opened_at = "open", self.clock()
            raise
        self.failures, self.state = 0, "closed"
        return result


# ---- PII masking ------------------------------------------------------------------------------


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PHONE = re.compile(r"(?:\+?1[ .-]?)?\(?\b\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}\b")


def mask(text: str) -> str:
    def card(m: re.Match) -> str:
        d = re.sub(r"\D", "", m.group())
        return "[CARD]" if 13 <= len(d) <= 19 and _luhn(d) else m.group()

    text = _EMAIL.sub("[EMAIL]", text)
    text = _SSN.sub("[SSN]", text)
    text = _CARD.sub(card, text)
    return _PHONE.sub("[PHONE]", text)


def mask_obj(obj):
    if isinstance(obj, str):
        return mask(obj)
    if isinstance(obj, dict):
        return {k: ("[EMAIL]" if "EMAIL" in k.upper() else mask_obj(v)) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [mask_obj(v) for v in obj]
    return obj


class AuditLog:
    """Append-only JSONL. Every entry passes through mask_obj and carries a hash chain."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.prev = "0" * 64
        self.lock = threading.Lock()

    def write(self, **entry) -> dict:
        with self.lock:
            e = {"ts": round(time.time(), 3), **mask_obj(entry), "prev": self.prev}
            line = json.dumps(e, sort_keys=True, default=str)
            self.prev = hashlib.sha256(line.encode()).hexdigest()
            with self.path.open("a") as fh:
                fh.write(line + "\n")
            return e

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text().splitlines()]

    def verify_chain(self) -> bool:
        prev = "0" * 64
        for line in self.path.read_text().splitlines():
            if json.loads(line)["prev"] != prev:
                return False
            prev = hashlib.sha256(line.encode()).hexdigest()
        return True


class IdempotencyStore:
    """Remembers the outcome of each write by idempotency key so a retried write is not applied twice.
    A key reused with a different payload is refused."""

    def __init__(self, path: Path | str = ":memory:"):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS idem (k TEXT PRIMARY KEY, payload TEXT, result TEXT)")
        self.lock = threading.Lock()
        self.prevented = 0

    def run(self, key: str, payload: dict, fn: Callable[[], dict]) -> dict:
        if not key or len(key) > 64:
            raise ValueError("idempotency key required (max 64 chars)")
        body = json.dumps(payload, sort_keys=True)
        with self.lock:
            row = self.db.execute("SELECT payload, result FROM idem WHERE k=?", (key,)).fetchone()
            if row:
                if row[0] != body:
                    raise ValueError("idempotency key reused with a different request")
                self.prevented += 1
                return {**json.loads(row[1]), "replayed": True}
            result = fn()
            self.db.execute("INSERT INTO idem VALUES (?,?,?)", (key, body, json.dumps(result)))
            self.db.commit()
            return {**result, "replayed": False}
