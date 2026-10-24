import pytest

from legacyagents.screen import GreenScreen, ProtectedField
from legacyagents.screen_agent import Approval, LayoutDrift, NavigationError, ScreenTool, naive_read


def test_screen_is_24x80(gw):
    s = GreenScreen(gw)
    assert len(s.text()) == 24 and all(len(r) == 80 for r in s.text())


def test_protected_field_refused(gw):
    with pytest.raises(ProtectedField):
        GreenScreen(gw).type_at(1, 2, "X")


def test_field_overflow_refused(gw):
    with pytest.raises(ProtectedField):
        GreenScreen(gw).type_at(6, 44, "X" * 11)


def test_password_hidden(gw):
    s = GreenScreen(gw)
    s.type_at(7, 44, "demo-ro")
    assert "demo-ro" not in "\n".join(s.text())


def test_bad_signon(gw):
    with pytest.raises(NavigationError):
        ScreenTool(GreenScreen(gw), "AGENTRO", "nope").read_account("HR00100003")


def test_read_v1(gw):
    r = ScreenTool(GreenScreen(gw), "AGENTRO", "demo-ro").read_account("HR00100003")
    assert r["ACCT-ID"] == "HR00100003" and r["ACCT-STATUS"] == "A"


def test_not_found_is_navigation_error(gw):
    with pytest.raises(NavigationError):
        ScreenTool(GreenScreen(gw), "AGENTRO", "demo-ro").read_account("HR00999999")


@pytest.mark.parametrize("layout", ["v2", "v3"])
def test_drift_detected(gw, layout):
    with pytest.raises(LayoutDrift):
        ScreenTool(GreenScreen(gw, layout), "AGENTRO", "demo-ro").read_account("HR00100003")


def test_naive_reader_silently_wrong_on_v2(gw):
    s = GreenScreen(gw, "v2")
    try:
        ScreenTool(s, "AGENTRO", "demo-ro").read_account("HR00100003")
    except LayoutDrift:
        pass
    assert naive_read(s)["ACCT-ID"] != "HR00100003"


def test_relocate_handles_shift_but_flags_it(gw):
    t = ScreenTool(GreenScreen(gw, "v2"), "AGENTRO", "demo-ro", relocate=True)
    r = t.read_account("HR00100003")
    assert r["ACCT-ID"] == "HR00100003" and r["_relocated"] and t.drift_events


def test_relocate_refuses_renamed_label(gw):
    with pytest.raises(LayoutDrift):
        ScreenTool(GreenScreen(gw, "v3"), "AGENTRO", "demo-ro", relocate=True).read_account("HR00100003")


def test_read_only_default_refuses_update(gw):
    with pytest.raises(PermissionError):
        ScreenTool(GreenScreen(gw), "AGENTRW", "demo-rw").update_status("HR00100003", "F", Approval("s", "HR00100003", "F", "t"))


def test_update_without_approval_is_pending(gw):
    r = ScreenTool(GreenScreen(gw), "AGENTRW", "demo-rw", read_only=False).update_status("HR00100003", "F")
    assert r["pending_approval"] and gw.applied_writes == 0


def test_mismatched_approval_refused(gw):
    with pytest.raises(PermissionError):
        ScreenTool(GreenScreen(gw), "AGENTRW", "demo-rw", read_only=False).update_status(
            "HR00100003", "C", Approval("s", "HR00100003", "F", "t")
        )


def test_approved_update(gw):
    r = ScreenTool(GreenScreen(gw), "AGENTRW", "demo-rw", read_only=False).update_status(
        "HR00100003", "F", Approval("supervisor", "HR00100003", "F", "CHG-1")
    )
    assert r["status"] == "F" and gw.applied_writes == 1


def test_approved_update_replay_not_reapplied(gw):
    for _ in range(2):
        ScreenTool(GreenScreen(gw), "AGENTRW", "demo-rw", read_only=False).update_status(
            "HR00100003", "F", Approval("supervisor", "HR00100003", "F", "CHG-1")
        )
    assert gw.applied_writes == 1


def test_read_only_profile_cannot_enter_update_mode(gw):
    with pytest.raises(PermissionError):
        ScreenTool(GreenScreen(gw), "AGENTRO", "demo-ro", read_only=False).update_status(
            "HR00100003", "F", Approval("s", "HR00100003", "F", "t")
        )


def test_update_refused_on_drifted_screen(gw):
    with pytest.raises(LayoutDrift):
        ScreenTool(GreenScreen(gw, "v2"), "AGENTRW", "demo-rw", read_only=False).update_status(
            "HR00100003", "F", Approval("s", "HR00100003", "F", "t")
        )
    assert gw.applied_writes == 0
