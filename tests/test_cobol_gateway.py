import pytest

from legacyagents.cobol import LegacyUnavailable
from legacyagents.data import accounts
from legacyagents.gateway import ValidationError


def test_real_cobol_inquiry_matches_source(gw):
    src = {r["ACCT-ID"]: r for r in accounts(200)}
    for a in ["HR00100000", "HR00100003", "HR00100199"]:
        assert gw.get_account(a) == src[a]


def test_inquiry_not_found(gw):
    assert gw.get_account("HR00999999") is None


def test_policy_inquiry(gw):
    r = gw.get_policy("LM-002000004")
    assert r["POL-ID"] == "LM-002000004" and r["POL-STATUS"] in "AL"


@pytest.mark.parametrize("bad", ["HR001", "HR0010000X", "XX00100000", "HR001000000", 12, "HR00100000;rm"])
def test_bad_account_ids_rejected_before_cobol(gw, bad):
    calls = gw.runtime.calls
    with pytest.raises(ValidationError):
        gw.get_account(bad)
    assert gw.runtime.calls == calls


def test_batch_file_drop(gw):
    out = gw.batch_lookup(["HR00100003", "HR00100005", "HR00999999"])
    assert [r["rc"] for r in out] == ["00", "CL", "NF"]
    assert out[0]["balance"] == accounts(200)[3]["ACCT-BALANCE"]
    assert (gw.workdir / "batch" / "outbox" / "B0000001.RES").exists()


def test_batch_negative_balance_sign(gw):
    neg = next(r for r in accounts(200) if r["ACCT-BALANCE"].startswith("-"))
    assert gw.batch_lookup([neg["ACCT-ID"]])[0]["balance"] == neg["ACCT-BALANCE"]


def test_batch_limits(gw):
    with pytest.raises(ValidationError):
        gw.batch_lookup([])
    with pytest.raises(ValidationError):
        gw.batch_lookup(["bad"])


def test_update_is_applied_by_cobol(gw):
    r = gw.update_status("HR00100010", "F", "k1", "agent", "supervisor")
    assert r["rc"] == "00" and r["replayed"] is False
    assert gw.get_account("HR00100010")["ACCT-STATUS"] == "F"


def test_update_idempotent_replay(gw):
    gw.update_status("HR00100010", "F", "k1", "agent", "supervisor")
    r = gw.update_status("HR00100010", "F", "k1", "agent", "supervisor")
    assert r["replayed"] and gw.applied_writes == 1 and len(gw.journal.entries) == 1


def test_idempotency_key_reuse_with_other_payload(gw):
    gw.update_status("HR00100010", "F", "k1", "agent", "supervisor")
    with pytest.raises(ValueError):
        gw.update_status("HR00100011", "F", "k1", "agent", "supervisor")


def test_update_needs_approver(gw):
    with pytest.raises(PermissionError):
        gw.update_status("HR00100010", "F", "k1", "agent", "")


def test_update_bad_status(gw):
    with pytest.raises(ValidationError):
        gw.update_status("HR00100010", "X", "k1", "agent", "s")


def test_update_not_found(gw):
    assert gw.update_status("HR00999999", "F", "k9", "agent", "s")["rc"] == "NF"


def test_cobol_rejects_bad_status_itself(gw):
    assert gw.runtime.run("ACCTUPD", "HR00100010Z", {"ACCTFILE": gw.files["accounts"]}) == 6


def test_missing_file_is_unavailable(gw, tmp_path):
    with pytest.raises(LegacyUnavailable):
        gw.runtime.run("ACCTINQ", "HR00100000", {"ACCTFILE": tmp_path / "nope.dat", "OUTFILE": tmp_path / "o"})


def test_unknown_program_refused(gw):
    with pytest.raises(ValueError):
        gw.runtime.run("RMRF", "", {})


def test_outage_raises_unavailable(gw):
    gw.runtime.down = True
    with pytest.raises(LegacyUnavailable):
        gw.get_account("HR00100000")


def test_audit_log_chain_and_masking(gw):
    gw.get_account("HR00100003")
    gw.update_status("HR00100003", "F", "k", "agent", "boss@example.test")
    text = gw.audit.path.read_text()
    assert "example.test" not in text
    assert gw.audit.verify_chain()


def test_audit_chain_detects_tamper(gw):
    gw.get_account("HR00100003")
    gw.get_account("HR00100004")
    lines = gw.audit.path.read_text().splitlines()
    gw.audit.path.write_text("\n".join([lines[0].replace("ok", "xx"), lines[1]]) + "\n")
    assert not gw.audit.verify_chain()
