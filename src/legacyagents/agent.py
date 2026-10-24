"""A customer-service agent that picks the right legacy path for a question.

The "model" is scripted (deterministic rules), so results are reproducible offline and in CI. It
stands in for an LLM's tool choice; swapping in a real model would only replace ScriptedModel.plan."""

from __future__ import annotations

import re

from .cobol import LegacyUnavailable
from .guards import CircuitOpen, RateLimited, mask
from .mq import MQTimeout
from .screen_agent import LayoutDrift, NavigationError
from .tools import LegacyTools, SchemaError

ACCT_RE = re.compile(r"\bHR\d{8}\b")
POL_RE = re.compile(r"\bLM-\d{9}\b")
STATUS_WORDS = {"freeze": "F", "frozen": "F", "close": "C", "closed": "C", "reactivate": "A", "active": "A"}

SAFE_DOWN = "The account system is not answering right now, so I can't check that. Nothing was changed. Please try again later."


class ScriptedModel:
    def plan(self, q: str) -> tuple[str, dict] | None:
        low = q.lower()
        accts, pols = ACCT_RE.findall(q), POL_RE.findall(q)
        if any(w in low for w in ("changed", "changes", "what happened", "recent activity")):
            return "recent_changes", {}
        if pols:
            return "get_policy", {"policy_id": pols[0]}
        if accts and any(w in low for w in ("freeze", "close ", "close my", "reactivate", "change status")):
            status = next(v for k, v in STATUS_WORDS.items() if k in low)
            return "screen_update_status", {"account_id": accts[0], "status": status}
        if len(accts) > 1:
            return "batch_account_lookup", {"account_ids": accts}
        if accts and any(w in low for w in ("screen", "type", "opened as")):
            return "screen_read_account", {"account_id": accts[0]}
        if accts:
            return "get_account_balance", {"account_id": accts[0]}
        if any(w in low for w in ("how many", "list", "report", "which accounts")):
            status = "C" if "closed" in low else "F" if "frozen" in low else "A"
            m = re.search(r"(?:over|above|more than)\s*\$?([\d,]+)", low)
            args = {"status": status}
            if m:
                args["min_balance"] = float(m.group(1).replace(",", ""))
            return "query_accounts_sql", args
        return None


class LegacyAgent:
    def __init__(self, tools: LegacyTools, model: ScriptedModel | None = None):
        self.tools, self.model = tools, model or ScriptedModel()
        self.trace: list[dict] = []

    def answer(self, question: str) -> dict:
        plan = self.model.plan(question)
        if plan is None:
            return self._done(question, None, "I can help with balances, policies, account reports and status changes.")
        tool, args = plan
        try:
            out = self.tools.call_tool(tool, args)
        except SchemaError as exc:
            return self._done(question, tool, f"That id doesn't look right ({exc}).")
        except (LegacyUnavailable, CircuitOpen, MQTimeout, RateLimited):
            return self._done(question, tool, SAFE_DOWN, safe_fail=True)
        except NavigationError:
            return self._done(
                question, tool, "I couldn't open that account on the terminal. Nothing was changed.", safe_fail=True
            )
        except LayoutDrift:
            return self._done(
                question, tool, "The terminal screen changed layout, so I stopped instead of guessing.", safe_fail=True
            )
        return self._done(question, tool, self._say(tool, args, out))

    def _say(self, tool, args, out) -> str:
        if tool == "get_account_balance":
            if out.get("http") == 503:
                return SAFE_DOWN
            if out.get("http") != 200:
                return "I couldn't find that account."
            return f"Account {out['ACCT-ID']} has a balance of ${out['ACCT-BALANCE']}."
        if tool == "get_policy":
            if not out.get("ok"):
                return SAFE_DOWN
            r = out["record"]
            return (
                "I couldn't find that policy."
                if r is None
                else (
                    f"Policy {r['POL-ID']} is {'active' if r['POL-STATUS'] == 'A' else 'lapsed'}, premium ${r['POL-PREMIUM']},"
                    f" renews {r['POL-RENEW-DATE']}."
                )
            )
        if tool == "batch_account_lookup":
            ok = [r for r in out["results"] if r["rc"] == "00"]
            return f"Checked {len(out['results'])} accounts; {len(ok)} are open: " + ", ".join(
                f"{r['account']} ${r['balance']}" for r in ok
            )
        if tool == "query_accounts_sql":
            return f"{out['count']} accounts match."
        if tool == "screen_read_account":
            return f"The terminal shows account {out['ACCT-ID']} with status {out['ACCT-STATUS']}."
        if tool == "screen_update_status":
            if out.get("pending_approval"):
                return "That change needs approval from a staff member before I can make it."
            return f"Done: {out['message']}"
        if tool == "recent_changes":
            return f"{len(out['events'])} account changes since I last looked."
        return "Done."

    def _done(self, q, tool, text, safe_fail=False) -> dict:
        r = {"question": mask(q), "tool": tool, "answer": text, "safe_fail": safe_fail}
        self.trace.append(r)
        return r


# Labelled routing checks (self-written, small: a regression check, not a quality claim).
ROUTING_CASES = [
    ("What's the balance on HR00100003?", "get_account_balance"),
    ("How much money is in HR00100010", "get_account_balance"),
    ("balance for HR00100042 please", "get_account_balance"),
    ("Is policy LM-002000004 still active?", "get_policy"),
    ("When does LM-002000017 renew?", "get_policy"),
    ("What is the premium on LM-002000050", "get_policy"),
    ("Compare HR00100001 and HR00100002", "batch_account_lookup"),
    ("Check HR00100001, HR00100002, HR00100003 and HR00100004", "batch_account_lookup"),
    ("Please freeze HR00100007, my card was stolen", "screen_update_status"),
    ("Close my account HR00100008", "screen_update_status"),
    ("Reactivate HR00100009", "screen_update_status"),
    ("What does the screen show for HR00100011?", "screen_read_account"),
    ("What type was HR00100012 opened as?", "screen_read_account"),
    ("How many accounts are closed?", "query_accounts_sql"),
    ("List active accounts over $100,000", "query_accounts_sql"),
    ("Report of frozen accounts", "query_accounts_sql"),
    ("Which accounts have more than 200000?", "query_accounts_sql"),
    ("What changed on accounts today?", "recent_changes"),
    ("Show me recent activity", "recent_changes"),
    ("Any changes since this morning?", "recent_changes"),
    ("Tell me a joke", None),
    ("What's the balance on HR123?", None),
]
