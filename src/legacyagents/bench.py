"""Measure every pattern for real on this machine. Writes results.json.

Latencies are wall-clock and vary by machine; every other number is deterministic (fixed seeds)
and CI checks it against the committed results.json."""

from __future__ import annotations

import json
import random
import statistics
import tempfile
import threading
import time
from decimal import Decimal
from pathlib import Path

from . import copybook
from .agent import ROUTING_CASES, LegacyAgent, ScriptedModel
from .cdc import CdcReader
from .data import accounts, layout, policies
from .facade import get_json
from .gateway import LegacyGateway
from .mq import Broker, MQClient, Responder
from .screen import GreenScreen
from .screen_agent import Approval, LayoutDrift, ScreenTool, naive_read
from .tools import LegacyTools


def _lat(fn, n: int) -> dict:
    xs = []
    for i in range(n):
        t = time.perf_counter()
        fn(i)
        xs.append((time.perf_counter() - t) * 1000)
    xs.sort()
    return {"n": n, "p50_ms": round(statistics.median(xs), 2), "p95_ms": round(xs[int(0.95 * (n - 1))], 2)}


def latency(tools: LegacyTools, n: int = 40) -> dict:
    gw = tools.gw
    ids = [f"HR{100000 + i:08d}" for i in range(200)]
    out = {
        "cobol_direct": _lat(lambda i: gw.get_account(ids[i % 200]), n),
        "rest_facade": _lat(lambda i: get_json(f"{tools.facade.url}/accounts/{ids[i % 200]}"), n),
        "mq_request_reply": _lat(lambda i: tools.mq.request({"policy_id": f"LM-{2000000 + i % 100:09d}"}), n),
        "screen_scrape": _lat(lambda i: tools.call_tool("screen_read_account", {"account_id": ids[i % 200]}), n),
        "sql_db2i": _lat(lambda i: tools.call_tool("query_accounts_sql", {"status": "A"}), n),
        "batch_100_accounts": _lat(lambda i: gw.batch_lookup(ids[:100], f"B{i:07d}"), max(5, n // 4)),
    }
    out["batch_per_account_ms"] = round(out["batch_100_accounts"]["p50_ms"] / 100, 3)
    # CDC lag: journal write -> event delivered to the streaming consumer
    reader = CdcReader(gw.journal, Path(gw.workdir) / "lag.checkpoint")
    reader.last = len(gw.journal.entries)
    lags, stop = [], threading.Event()
    th = threading.Thread(target=reader.stream, args=(stop, lambda ev, now: lags.append((now - ev["ts"]) * 1000)), daemon=True)
    th.start()
    for i in range(20):
        gw.update_status(ids[20 + i], "F", f"lag-{i}", "bench", "bench-approver")
    time.sleep(0.3)
    stop.set()
    th.join(1)
    lags.sort()
    out["cdc_event_lag"] = {"n": len(lags), "p50_ms": round(statistics.median(lags), 2), "max_ms": round(lags[-1], 2)}
    return out


def roundtrip(n_random: int = 10000) -> dict:
    acct, pol = layout("ACCTREC"), layout("POLREC")
    rng = random.Random(42)
    edge = ["0.00", "-0.01", "999999999.99", "-999999999.99", "0.10"]
    rows = []
    for i in range(n_random):
        r = dict(accounts(1, seed=i)[0])
        r["ACCT-BALANCE"] = edge[i] if i < len(edge) else str(Decimal(rng.randint(-(10**11) + 1, 10**11 - 1)).scaleb(-2))
        rows.append(r)
    ascii_ok = ebcdic_ok = bytes_ok = 0
    for r in rows:
        raw = copybook.encode(acct, r)
        ascii_ok += copybook.decode(acct, raw) == r
        bytes_ok += copybook.encode(acct, copybook.decode(acct, raw)) == raw
        e = copybook.transcode(raw, acct, copybook.ASCII, copybook.EBCDIC)
        ebcdic_ok += (
            copybook.decode(acct, e, copybook.EBCDIC) == r and copybook.transcode(e, acct, copybook.EBCDIC, copybook.ASCII) == raw
        )
    pol_rows = policies(100)
    pol_ok = sum(copybook.decode(pol, copybook.encode(pol, r)) == r for r in pol_rows)
    # COBOL-verified: what the compiled program hands back decodes to the source record
    with tempfile.TemporaryDirectory() as d:
        gw = LegacyGateway(Path(d), rate=10000, burst=10000)
        src = accounts(200)
        cobol_ok = sum(gw.get_account(r["ACCT-ID"]) == r for r in src)
    return {
        "random_records": n_random,
        "ascii_dict_roundtrip": ascii_ok,
        "byte_roundtrip": bytes_ok,
        "ebcdic_roundtrip": ebcdic_ok,
        "policy_roundtrip": f"{pol_ok}/100",
        "cobol_read_matches": f"{cobol_ok}/200",
        "accuracy_pct": round(100 * min(ascii_ok, bytes_ok, ebcdic_ok) / n_random, 2),
    }


def outage() -> dict:
    with tempfile.TemporaryDirectory() as d:
        gw = LegacyGateway(Path(d), breaker_threshold=5, cooldown=0.3)
        with LegacyTools(gw) as tools:
            agent = LegacyAgent(tools)
            gw.runtime.down = True
            before = gw.runtime.calls
            answers = [agent.answer(f"What's the balance on HR{100000 + i:08d}?") for i in range(40)]
            reached = gw.runtime.calls - before
            safe = sum(a["answer"].startswith("The account system is not answering") for a in answers)
            wrong = sum("$" in a["answer"] for a in answers)
            state_during = gw.breaker.state
            gw.runtime.down = False
            time.sleep(0.35)
            rec = agent.answer("What's the balance on HR00100003?")
            return {
                "requests_during_outage": 40,
                "calls_that_reached_legacy": reached,
                "short_circuited": gw.breaker.short_circuited,
                "safe_answers": safe,
                "wrong_answers": wrong,
                "breaker_during": state_during,
                "recovered_after_cooldown": "$" in rec["answer"],
                "breaker_after": gw.breaker.state,
            }


def idempotency() -> dict:
    with tempfile.TemporaryDirectory() as d:
        gw = LegacyGateway(Path(d), rate=10000, burst=10000)
        attempts = 0
        for i in range(50):
            for _ in range(4):  # original + 3 retries (client timeouts, double clicks, MQ redelivery)
                gw.update_status(f"HR{100100 + i:08d}", "F", f"write-{i}", "bench", "bench-approver")
                attempts += 1

        # concurrent duplicates of the same write
        def hit():
            gw.update_status("HR00100199", "C", "race-1", "bench", "bench-approver")

        ths = [threading.Thread(target=hit) for _ in range(10)]
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        return {
            "write_attempts": attempts + 10,
            "unique_writes": 51,
            "applied": gw.applied_writes,
            "duplicates_prevented": gw.idem.prevented,
            "journal_entries": len(gw.journal.entries),
        }


def screen_drift(n: int = 20) -> dict:
    with tempfile.TemporaryDirectory() as d:
        gw = LegacyGateway(Path(d), rate=10000, burst=10000)
        truth = {r["ACCT-ID"]: r for r in accounts(200)}
        ids = list(truth)[:n]
        out = {}
        for lay in ("v1", "v2", "v3"):
            naive_wrong = guarded_detected = guarded_wrong = reloc_ok = 0
            for a in ids:
                s = GreenScreen(gw, lay)
                tool = ScreenTool(s, "AGENTRO", "demo-ro")
                try:
                    got = tool.read_account(a)
                    guarded_wrong += any(got[k] != truth[a][k] for k in got)
                except LayoutDrift:
                    guarded_detected += 1
                naive = naive_read(s)
                naive_wrong += any(naive[k] != truth[a][k] for k in naive)
                try:
                    got = ScreenTool(GreenScreen(gw, lay), "AGENTRO", "demo-ro", relocate=True).read_account(a)
                    reloc_ok += all(got[k] == truth[a][k] for k in got if not k.startswith("_"))
                except LayoutDrift:
                    pass
            out[lay] = {
                "reads": n,
                "naive_silently_wrong": naive_wrong,
                "guarded_detected_drift": guarded_detected,
                "guarded_wrong": guarded_wrong,
                "relocated_correct": reloc_ok,
            }
        # guardrails on writes
        s = GreenScreen(gw)
        ro = ScreenTool(s, "AGENTRO", "demo-ro")
        try:
            ro.update_status("HR00100001", "F", Approval("x", "HR00100001", "F", "t"))
            ro_blocked = False
        except PermissionError:
            ro_blocked = True
        rw = ScreenTool(GreenScreen(gw), "AGENTRW", "demo-rw", read_only=False)
        pending = rw.update_status("HR00100001", "F").get("pending_approval", False)
        drift_rw = ScreenTool(GreenScreen(gw, "v2"), "AGENTRW", "demo-rw", read_only=False)
        try:
            drift_rw.update_status("HR00100002", "F", Approval("jm", "HR00100002", "F", "t2"))
            drift_write_blocked = False
        except LayoutDrift:
            drift_write_blocked = True
        out["writes"] = {
            "read_only_refused": ro_blocked,
            "no_approval_pending": pending,
            "write_on_drifted_screen_refused": drift_write_blocked,
            "applied_without_approval": gw.applied_writes,
        }
        return out


def mq_faults(n: int = 50) -> dict:
    with tempfile.TemporaryDirectory() as d:
        gw = LegacyGateway(Path(d), rate=10000, burst=10000)
        broker = Broker()
        with Responder(broker, gw, drop_rate=0.3, seed=5) as resp:
            client = MQClient(broker, timeout=0.15, retries=3, backoff=0.01)
            ok = fail = 0
            for i in range(n):
                try:
                    r = client.request({"policy_id": f"LM-{2000000 + i:09d}"})
                    ok += r["ok"] and r["record"]["POL-ID"] == f"LM-{2000000 + i:09d}"
                except Exception:
                    fail += 1
            dropped = resp.dropped
        # no-responder case: must time out cleanly
        lonely = MQClient(Broker(), timeout=0.05, retries=2, backoff=0.0)
        try:
            lonely.request({"policy_id": "LM-002000001"})
            timed_out = False
        except Exception:
            timed_out = True
        return {
            "requests": n,
            "drop_rate": 0.3,
            "dropped_by_region": dropped,
            "answered_correctly": ok,
            "gave_up": fail,
            "attempts": client.attempts,
            "stray_replies_discarded": client.stray,
            "no_listener_times_out": timed_out,
        }


def rate_limit() -> dict:
    with tempfile.TemporaryDirectory() as d:
        gw = LegacyGateway(Path(d), rate=20, burst=10)
        ok = rejected = 0
        for i in range(30):
            try:
                gw.get_account(f"HR{100000 + i:08d}")
                ok += 1
            except Exception:
                rejected += 1
        return {"burst_requests": 30, "burst_size": 10, "allowed": ok, "rejected": rejected, "legacy_calls": gw.runtime.calls}


def agent_eval() -> dict:
    m = ScriptedModel()
    correct = sum((m.plan(q) or (None,))[0] == want for q, want in ROUTING_CASES)
    with tempfile.TemporaryDirectory() as d, LegacyTools(LegacyGateway(Path(d))) as tools:
        agent = LegacyAgent(tools)
        for q, _ in ROUTING_CASES:
            agent.answer(q)
        planted = ["pat.doe@example.test", "4111 1111 1111 1111", "123-45-6789", "(555) 123-4567"]
        agent.answer(f"I'm {planted[0]}, card {planted[1]}, SSN {planted[2]}, call {planted[3]}: balance HR00100003?")
        writes = tools.gw.applied_writes
        log = (Path(d) / "audit.jsonl").read_text() + json.dumps(agent.trace)
        leaks = sum(x in log for x in planted) + log.count("@example.test")
        sample = agent.answer("What's the balance on HR00100003?")["answer"]
    return {
        "cases": len(ROUTING_CASES),
        "routed_correctly": correct,
        "writes_without_approval": writes,
        "planted_pii_values": len(planted),
        "pii_leaks_in_logs": leaks,
        "sample_answer": sample,
    }


def run() -> dict:
    with tempfile.TemporaryDirectory() as d, LegacyTools(LegacyGateway(Path(d), rate=10000, burst=10000)) as tools:
        lat = latency(tools)
    return {
        "latency": lat,
        "copybook_roundtrip": roundtrip(),
        "outage": outage(),
        "idempotency": idempotency(),
        "screen_drift": screen_drift(),
        "mq_faults": mq_faults(),
        "rate_limit": rate_limit(),
        "agent": agent_eval(),
    }


def deterministic(r: dict) -> dict:
    return {k: v for k, v in r.items() if k != "latency"}
