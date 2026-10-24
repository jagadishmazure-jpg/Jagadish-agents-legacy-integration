import threading
from pathlib import Path

import pytest

from legacyagents.cdc import CdcReader
from legacyagents.facade import Facade, get_json
from legacyagents.mq import Broker, Message, MQClient, MQTimeout, Responder
from legacyagents.sql import Db2iConnection, SqlRefused, build_library

# ---- REST facade ----


def test_facade_get_account(gw):
    with Facade(gw) as f:
        code, body = get_json(f"{f.url}/accounts/HR00100003")
    assert code == 200 and body["ACCT-ID"] == "HR00100003" and body["ACCT-EMAIL"] == "[EMAIL]"


@pytest.mark.parametrize(
    "path,code",
    [("/accounts/HR00999999", 404), ("/accounts/BAD", 400), ("/nope", 404), ("/policies/LM-002000001", 200), ("/health", 200)],
)
def test_facade_codes(gw, path, code):
    with Facade(gw) as f:
        assert get_json(f.url + path)[0] == code


def test_facade_503_when_down(gw):
    gw.runtime.down = True
    with Facade(gw) as f:
        code, body = get_json(f"{f.url}/accounts/HR00100003")
    assert code == 503 and "unavailable" in body["error"]


def test_facade_429_when_rate_limited(tmp_path):
    from legacyagents.gateway import LegacyGateway

    g = LegacyGateway(tmp_path, rate=0.001, burst=1)
    with Facade(g) as f:
        codes = [get_json(f"{f.url}/accounts/HR00100003")[0] for _ in range(3)]
    assert codes == [200, 429, 429]


def test_facade_client_refuses_remote_hosts():
    with pytest.raises(ValueError):
        get_json("http://example.test/accounts/x")


# ---- MQ ----


def test_mq_request_reply(gw):
    b = Broker()
    with Responder(b, gw):
        r = MQClient(b).request({"policy_id": "LM-002000004"})
    assert r["ok"] and r["record"]["POL-ID"] == "LM-002000004" and r["attempts"] == 1


def test_mq_retries_through_drops(gw):
    b = Broker()
    with Responder(b, gw, drop_rate=0.5, seed=1) as resp:
        c = MQClient(b, timeout=0.1, retries=5, backoff=0.0)
        results = [c.request({"policy_id": f"LM-{2000000 + i:09d}"}) for i in range(10)]
    assert all(r["ok"] for r in results) and resp.dropped > 0 and c.attempts > 10


def test_mq_timeout_without_listener():
    with pytest.raises(MQTimeout):
        MQClient(Broker(), timeout=0.02, retries=1, backoff=0.0).request({"policy_id": "LM-002000004"})


def test_mq_discards_stray_correlation(gw):
    b = Broker()
    c = MQClient(b)
    b.put(c.reply_q, Message({"ok": True, "record": "stale"}, "not-mine"))
    with Responder(b, gw):
        r = c.request({"policy_id": "LM-002000004"})
    assert r["record"] != "stale" and c.stray == 1


def test_mq_expired_message_dropped():
    b = Broker()
    b.put("Q", Message({}, "c", expiry=1.0))
    assert b.get("Q", 0.01) is None and b.expired == 1


def test_mq_safe_error_reply(gw):
    b = Broker()
    with Responder(b, gw):
        r = MQClient(b).request({"policy_id": "bad"})
    assert r == {"ok": False, "error": "ValidationError", "attempts": 1}


# ---- SQL (DB2 for i style) ----


@pytest.fixture
def db(gw):
    lib = build_library(gw.files["accounts"], Path(gw.workdir) / "BANKLIB.db")
    return Db2iConnection(lib, "AGENTRO", "demo-ro")


def test_sql_system_naming_and_fetch_first(db):
    rows = db.query("SELECT ACCTID FROM BANKLIB/ACCTMST ORDER BY ACCTID FETCH FIRST 3 ROWS ONLY")
    assert [r["ACCTID"] for r in rows] == ["HR00100000", "HR00100001", "HR00100002"]


def test_sql_translate():
    assert Db2iConnection.translate("SELECT * FROM BANKLIB/ACCTMST FETCH FIRST 9999 ROWS ONLY") == (
        "SELECT * FROM BANKLIB.ACCTMST LIMIT 500"
    )


def test_sql_parameterized_count(db):
    n = db.query("SELECT COUNT(*) AS N FROM BANKLIB.ACCTMST WHERE ACCTST = ?", ("C",))[0]["N"]
    assert n == sum(1 for i in range(200) if i % 17 == 5)


@pytest.mark.parametrize(
    "stmt",
    [
        "UPDATE BANKLIB.ACCTMST SET ACCTST='C'",
        "DELETE FROM BANKLIB.ACCTMST",
        "DROP TABLE BANKLIB.ACCTMST",
        "SELECT 1; DELETE FROM BANKLIB.ACCTMST",
        "INSERT INTO BANKLIB.ACCTMST (ACCTID) VALUES ('X')",
        "WITH x AS (SELECT 1) DELETE FROM BANKLIB.ACCTMST",
        "ATTACH DATABASE 'x' AS y",
        "PRAGMA writable_schema=1",
    ],
)
def test_sql_writes_refused(db, stmt):
    with pytest.raises(SqlRefused):
        db.query(stmt)
    assert db.query("SELECT COUNT(*) AS N FROM BANKLIB.ACCTMST")[0]["N"] == 200


@pytest.mark.parametrize("user,pw", [("AGENTRW", "demo-ro"), ("QSECOFR", "x"), ("AGENTRO", "wrong")])
def test_sql_credentials(gw, user, pw):
    lib = build_library(gw.files["accounts"], Path(gw.workdir) / "L.db")
    with pytest.raises(SqlRefused):
        Db2iConnection(lib, user, pw)


# ---- CDC ----


def test_cdc_events_ordered_and_masked(gw, tmp_path):
    r = CdcReader(gw.journal, tmp_path / "cp")
    gw.update_status("HR00100001", "F", "a", "x@example.test", "s")
    gw.update_status("HR00100002", "C", "b", "agent", "s")
    ev = r.poll()
    assert [e["seq"] for e in ev] == [1, 2] and ev[0]["after"] == {"ACCT-STATUS": "F"}
    assert "example.test" not in str(ev)
    assert r.poll() == []


def test_cdc_resume_from_checkpoint_no_duplicates(gw, tmp_path):
    r = CdcReader(gw.journal, tmp_path / "cp")
    gw.update_status("HR00100001", "F", "a", "agent", "s")
    r.poll()
    gw.update_status("HR00100002", "F", "b", "agent", "s")
    r2 = CdcReader(gw.journal, tmp_path / "cp")  # restart
    assert [e["key"] for e in r2.poll()] == ["HR00100002"]


def test_cdc_replayed_write_emits_no_event(gw, tmp_path):
    r = CdcReader(gw.journal, tmp_path / "cp")
    for _ in range(3):
        gw.update_status("HR00100001", "F", "same", "agent", "s")
    assert len(r.poll()) == 1


def test_cdc_stream(gw, tmp_path):
    r = CdcReader(gw.journal, tmp_path / "cp")
    got, stop = [], threading.Event()
    t = threading.Thread(target=r.stream, args=(stop, lambda e, now: got.append(e)), daemon=True)
    t.start()
    gw.update_status("HR00100001", "F", "a", "agent", "s")
    for _ in range(50):
        if got:
            break
        threading.Event().wait(0.02)
    stop.set()
    t.join(1)
    assert got and got[0]["key"] == "HR00100001"
