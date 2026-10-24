"""The single door to the legacy estate. Every pattern goes through here so the same guards apply:
input validation against the copybook, rate limit, circuit breaker, idempotent writes, journal (for
CDC) and a PII-masked audit log."""

from __future__ import annotations

import re
import tempfile
import threading
import time
from pathlib import Path

from . import copybook
from .cobol import CobolRuntime, LegacyUnavailable, build
from .data import layout, seed_files
from .guards import AuditLog, CircuitBreaker, IdempotencyStore, TokenBucket

ACCT_ID = re.compile(r"^HR\d{8}$")
POL_ID = re.compile(r"^LM-\d{9}$")
STATUSES = {"A", "F", "C"}


class ValidationError(ValueError):
    pass


def check_key(value, field: copybook.Field, pattern: re.Pattern) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field.name}: expected text")
    if len(value) > field.digits:
        raise ValidationError(f"{field.name}: longer than {field.digits} characters")
    if not pattern.match(value):
        raise ValidationError(f"{field.name}: wrong format")
    return value


class Journal:
    """IBM i style journal: ordered entries with a sequence number and before/after images."""

    def __init__(self):
        self.entries: list[dict] = []
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)

    def append(self, **e) -> dict:
        with self.cond:
            e = {"seq": len(self.entries) + 1, "ts": time.time(), **e}
            self.entries.append(e)
            self.cond.notify_all()
            return e


class LegacyGateway:
    def __init__(
        self,
        workdir: Path | None = None,
        n_accounts: int = 200,
        rate: float = 500,
        burst: int = 100,
        breaker_threshold: int = 5,
        cooldown: float = 30.0,
    ):
        build()
        self._tmp = None
        if workdir is None:
            self._tmp = tempfile.TemporaryDirectory()
            workdir = Path(self._tmp.name)
        self.workdir = Path(workdir)
        self.files = seed_files(self.workdir, n_accounts)
        self.acct = layout("ACCTREC")
        self.pol = layout("POLREC")
        self.req = layout("BATREQ")
        self.res = layout("BATRES")
        self.runtime = CobolRuntime(self.workdir)
        self.limiter = TokenBucket(rate, burst)
        self.breaker = CircuitBreaker(breaker_threshold, cooldown)
        self.audit = AuditLog(self.workdir / "audit.jsonl")
        self.idem = IdempotencyStore()
        self.journal = Journal()
        self.write_lock = threading.Lock()
        self.applied_writes = 0

    # -- plumbing --
    def _guarded(self, op: str, fn, **ctx):
        self.limiter.acquire()
        try:
            out = self.breaker.call(fn)
        except Exception as exc:
            self.audit.write(op=op, outcome="error", error=type(exc).__name__, **ctx)
            raise
        self.audit.write(op=op, outcome="ok", **ctx)
        return out

    # -- reads --
    def get_account(self, acct_id: str) -> dict | None:
        check_key(acct_id, self.acct.field("ACCT-ID"), ACCT_ID)

        def call():
            raw = self.runtime.inquire("ACCTINQ", "ACCTFILE", self.files["accounts"], acct_id)
            return None if raw is None else copybook.decode(self.acct, raw)

        return self._guarded("get_account", call, key=acct_id)

    def get_policy(self, pol_id: str) -> dict | None:
        check_key(pol_id, self.pol.field("POL-ID"), POL_ID)

        def call():
            raw = self.runtime.inquire("POLINQ", "POLFILE", self.files["policies"], pol_id)
            return None if raw is None else copybook.decode(self.pol, raw)

        return self._guarded("get_policy", call, key=pol_id)

    # -- batch (file drop) --
    def batch_lookup(self, acct_ids: list[str], batch_id: str = "B0000001") -> list[dict]:
        if not acct_ids or len(acct_ids) > 5000:
            raise ValidationError("1-5000 account ids per batch")
        for a in acct_ids:
            check_key(a, self.acct.field("ACCT-ID"), ACCT_ID)
        inbox, outbox = self.workdir / "batch" / "inbox", self.workdir / "batch" / "outbox"
        inbox.mkdir(parents=True, exist_ok=True)
        outbox.mkdir(parents=True, exist_ok=True)
        req = inbox / f"{batch_id}.REQ"
        lines = [copybook.encode(self.req, {"REQ-ID": f"R{i:07d}", "REQ-ACCT-ID": a}).decode() for i, a in enumerate(acct_ids)]
        req.write_text("\n".join(lines) + "\n")
        res = outbox / f"{batch_id}.RES"

        def call():
            self.runtime.run("ACCTBAT", "", {"ACCTFILE": self.files["accounts"], "REQFILE": req, "RESFILE": res})
            out = []
            for line in res.read_text().splitlines():
                r = copybook.decode(self.res, line.ljust(self.res.length).encode())
                bal = r["RES-BALANCE"]
                out.append(
                    {
                        "request": r["RES-REQ-ID"],
                        "account": r["RES-ACCT-ID"],
                        "rc": r["RES-RC"],
                        "balance": ("-" + bal) if r["RES-SIGN"] == "-" else bal,
                        "status": r["RES-STATUS"],
                    }
                )
            return out

        return self._guarded("batch_lookup", call, key=batch_id, count=len(acct_ids))

    # -- write (idempotent, journaled) --
    def update_status(self, acct_id: str, status: str, idem_key: str, actor: str, approved_by: str) -> dict:
        check_key(acct_id, self.acct.field("ACCT-ID"), ACCT_ID)
        if status not in STATUSES:
            raise ValidationError("ACCT-STATUS: must be one of A, F, C")
        if not approved_by:
            raise PermissionError("writes need a named human approver")

        def apply() -> dict:
            with self.write_lock:
                before = self.get_account(acct_id)
                if before is None:
                    return {"rc": "NF"}

                def call():
                    return self.runtime.run("ACCTUPD", f"{acct_id}{status}", {"ACCTFILE": self.files["accounts"]})

                rc = self._guarded("update_status", call, key=acct_id, actor=actor, approved_by=approved_by)
                self.applied_writes += 1
                self.journal.append(
                    file="ACCTMST",
                    entry="UP",
                    key=acct_id,
                    before={"ACCT-STATUS": before["ACCT-STATUS"]},
                    after={"ACCT-STATUS": status},
                    actor=actor,
                )
                return {"rc": "00" if rc == 0 else f"RC{rc}", "before": before["ACCT-STATUS"], "after": status}

        return self.idem.run(idem_key, {"acct": acct_id, "status": status}, apply)


__all__ = ["LegacyGateway", "LegacyUnavailable", "ValidationError"]
