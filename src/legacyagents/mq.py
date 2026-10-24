"""MQ-style request/reply over an in-process broker (stand-in for IBM MQ).

Requests go to a named request queue with a correlation id and a reply-to queue. A responder on the
"mainframe side" calls the COBOL program and replies with the same correlation id. The client waits
with a timeout, retries with backoff, and discards replies whose correlation id it is not waiting
for (late or stray messages). Faults can be injected: dropped requests and slow replies."""

from __future__ import annotations

import queue
import random
import threading
import time
import uuid
from dataclasses import dataclass, field

from .gateway import LegacyGateway


@dataclass
class Message:
    body: dict
    correlation_id: str
    reply_to: str = ""
    expiry: float = 0.0
    msg_id: str = field(default_factory=lambda: uuid.uuid4().hex)


class Broker:
    def __init__(self):
        self.queues: dict[str, queue.Queue] = {}
        self.lock = threading.Lock()
        self.expired = 0

    def q(self, name: str) -> queue.Queue:
        with self.lock:
            return self.queues.setdefault(name, queue.Queue())

    def put(self, name: str, msg: Message) -> None:
        self.q(name).put(msg)

    def get(self, name: str, timeout: float) -> Message | None:
        try:
            m = self.q(name).get(timeout=timeout)
        except queue.Empty:
            return None
        if m.expiry and time.time() > m.expiry:
            self.expired += 1
            return None
        return m


class Responder:
    """Mainframe-side listener. drop_rate and delay simulate a struggling region."""

    def __init__(
        self,
        broker: Broker,
        gw: LegacyGateway,
        request_q: str = "LEGACY.POLICY.REQ",
        drop_rate: float = 0.0,
        delay: float = 0.0,
        seed: int = 3,
    ):
        self.broker, self.gw, self.request_q = broker, gw, request_q
        self.drop_rate, self.delay = drop_rate, delay
        self.rng = random.Random(seed)
        self.stop = threading.Event()
        self.handled = self.dropped = 0
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join(2)

    def _loop(self):
        while not self.stop.is_set():
            m = self.broker.get(self.request_q, 0.05)
            if m is None:
                continue
            if self.rng.random() < self.drop_rate:
                self.dropped += 1
                continue
            if self.delay:
                time.sleep(self.delay)
            try:
                rec = self.gw.get_policy(m.body["policy_id"])
                body = {"ok": True, "record": rec}
            except Exception as exc:  # reply with a safe error, never the stack or data
                body = {"ok": False, "error": type(exc).__name__}
            self.handled += 1
            self.broker.put(m.reply_to, Message(body, m.correlation_id, expiry=time.time() + 30))


class MQTimeout(RuntimeError):
    pass


class MQClient:
    def __init__(
        self, broker: Broker, request_q: str = "LEGACY.POLICY.REQ", timeout: float = 0.5, retries: int = 3, backoff: float = 0.05
    ):
        self.broker, self.request_q = broker, request_q
        self.timeout, self.retries, self.backoff = timeout, retries, backoff
        self.reply_q = f"AGENT.REPLY.{uuid.uuid4().hex[:8]}"
        self.attempts = self.stray = 0

    def request(self, body: dict) -> dict:
        corr = uuid.uuid4().hex
        for attempt in range(self.retries + 1):
            self.attempts += 1
            self.broker.put(self.request_q, Message(body, corr, self.reply_q, expiry=time.time() + self.timeout * 4))
            deadline = time.time() + self.timeout
            while (left := deadline - time.time()) > 0:
                m = self.broker.get(self.reply_q, left)
                if m is None:
                    break
                if m.correlation_id != corr:
                    self.stray += 1
                    continue
                return {**m.body, "attempts": attempt + 1}
            time.sleep(self.backoff * (2**attempt))
        raise MQTimeout("no reply from legacy queue")
