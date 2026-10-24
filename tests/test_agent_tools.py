import pytest

from legacyagents.agent import ROUTING_CASES, SAFE_DOWN, LegacyAgent, ScriptedModel
from legacyagents.tools import TOOLS, SchemaError, validate_args


@pytest.mark.parametrize("q,want", ROUTING_CASES)
def test_routing(q, want):
    assert (ScriptedModel().plan(q) or (None,))[0] == want


def test_list_tools_schema(tools):
    listed = tools.list_tools()
    assert {t["name"] for t in listed} == set(TOOLS)
    assert all(t["inputSchema"]["additionalProperties"] is False for t in listed)


@pytest.mark.parametrize(
    "tool,args",
    [
        ("get_account_balance", {}),
        ("get_account_balance", {"account_id": "HR001"}),
        ("get_account_balance", {"account_id": "HR00100003", "x": 1}),
        ("get_policy", {"policy_id": "LM-1"}),
        ("query_accounts_sql", {"status": "Z"}),
        ("query_accounts_sql", {"status": "A", "min_balance": float("nan")}),
        ("query_accounts_sql", {"status": "A", "min_balance": -1e12}),
        ("batch_account_lookup", {"account_ids": []}),
        ("batch_account_lookup", {"account_ids": ["HR00100003", "bad"]}),
        ("nope", {}),
    ],
)
def test_schema_rejects(tool, args):
    with pytest.raises(SchemaError):
        validate_args(tool, args)


def test_every_tool_end_to_end(tools):
    assert tools.call_tool("get_account_balance", {"account_id": "HR00100003"})["http"] == 200
    assert tools.call_tool("get_policy", {"policy_id": "LM-002000004"})["ok"]
    assert len(tools.call_tool("batch_account_lookup", {"account_ids": ["HR00100001", "HR00100002"]})["results"]) == 2
    assert tools.call_tool("query_accounts_sql", {"status": "C"})["count"] > 0
    assert tools.call_tool("screen_read_account", {"account_id": "HR00100003"})["ACCT-ID"] == "HR00100003"
    assert tools.call_tool("screen_update_status", {"account_id": "HR00100003", "status": "F"})["pending_approval"]
    assert tools.call_tool("recent_changes", {}) == {"events": []}


def test_agent_answers(tools):
    a = LegacyAgent(tools)
    assert "$19334.19" in a.answer("What's the balance on HR00100003?")["answer"]
    assert "Policy LM-002000004" in a.answer("Is policy LM-002000004 still active?")["answer"]
    assert "couldn't find" in a.answer("balance for HR00999999")["answer"]


def test_agent_write_needs_approval_then_applies(tools):
    a = LegacyAgent(tools)
    q = "Please freeze HR00100007, my card was stolen"
    assert "needs approval" in a.answer(q)["answer"] and tools.gw.applied_writes == 0
    tools.approve("HR00100007", "F", "supervisor", "CHG-9")
    assert "Status changed" in a.answer(q)["answer"] and tools.gw.applied_writes == 1
    assert "1 account changes" in a.answer("What changed on accounts today?")["answer"]
    assert "needs approval" in a.answer(q)["answer"]  # approval is single-use


def test_agent_safe_failure_when_down(tools):
    tools.gw.runtime.down = True
    a = LegacyAgent(tools)
    for q in [
        "What's the balance on HR00100003?",
        "Compare HR00100001 and HR00100002",
        "What does the screen show for HR00100011?",
    ]:
        r = a.answer(q)
        assert "$" not in r["answer"]
    assert a.answer("Compare HR00100001 and HR00100002")["answer"] == SAFE_DOWN


def test_agent_policy_safe_when_down(tools):
    tools.gw.runtime.down = True
    assert LegacyAgent(tools).answer("Is policy LM-002000004 still active?")["answer"] == SAFE_DOWN


def test_agent_drift_stops(gw):
    from legacyagents.tools import LegacyTools

    with LegacyTools(gw, screen_layout="v2") as t:
        r = LegacyAgent(t).answer("What does the screen show for HR00100011?")
    assert r["safe_fail"] and "changed layout" in r["answer"]


def test_agent_masks_pii_in_trace(tools):
    a = LegacyAgent(tools)
    a.answer("I'm pat@example.test card 4111 1111 1111 1111 ssn 123-45-6789, balance HR00100003?")
    t = str(a.trace)
    assert "pat@example.test" not in t and "4111 1111" not in t and "123-45-6789" not in t


def test_agent_unknown_question(tools):
    assert LegacyAgent(tools).answer("Tell me a joke")["tool"] is None
