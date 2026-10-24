import json
from pathlib import Path

from legacyagents import bench

ROOT = Path(__file__).resolve().parents[1]


def test_committed_results_have_every_section():
    r = json.loads((ROOT / "results.json").read_text())
    assert set(r) == {
        "latency",
        "copybook_roundtrip",
        "outage",
        "idempotency",
        "screen_drift",
        "mq_faults",
        "rate_limit",
        "agent",
    }


def test_outage_numbers():
    r = bench.outage()
    assert r["calls_that_reached_legacy"] == 5 and r["wrong_answers"] == 0 and r["recovered_after_cooldown"]


def test_idempotency_numbers():
    r = bench.idempotency()
    assert r["applied"] == r["unique_writes"] == r["journal_entries"] == 51
    assert r["duplicates_prevented"] == r["write_attempts"] - 51


def test_rate_limit_numbers():
    r = bench.rate_limit()
    assert r["allowed"] == r["legacy_calls"] == 10 and r["rejected"] == 20
