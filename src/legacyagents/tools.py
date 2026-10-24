"""MCP-style tool layer: each legacy path is a named tool with a JSON schema. Arguments are checked
against the schema (types, lengths and patterns taken from the copybooks) before anything reaches
the legacy system. Results are PII-masked."""

from __future__ import annotations

import re
from pathlib import Path

from .cdc import CdcReader
from .facade import Facade, get_json
from .gateway import LegacyGateway
from .guards import mask_obj
from .mq import Broker, MQClient, Responder
from .screen import GreenScreen
from .screen_agent import Approval, ScreenTool
from .sql import Db2iConnection, build_library

ACCT = {"type": "string", "maxLength": 10, "pattern": r"^HR\d{8}$"}
POL = {"type": "string", "maxLength": 12, "pattern": r"^LM-\d{9}$"}

TOOLS = {
    "get_account_balance": {
        "description": "Current balance of one account via the COBOL REST facade.",
        "schema": {"account_id": ACCT},
        "required": ["account_id"],
    },
    "get_policy": {
        "description": "One insurance policy via MQ request/reply to the policy program.",
        "schema": {"policy_id": POL},
        "required": ["policy_id"],
    },
    "batch_account_lookup": {
        "description": "Many accounts at once via the nightly-style COBOL batch job.",
        "schema": {"account_ids": {"type": "array", "items": ACCT, "maxItems": 5000}},
        "required": ["account_ids"],
    },
    "query_accounts_sql": {
        "description": "Read-only report over BANKLIB.ACCTMST (DB2 for i style).",
        "schema": {
            "status": {"type": "string", "enum": ["A", "F", "C"]},
            "min_balance": {"type": "number", "minimum": -999999999},
        },
        "required": ["status"],
    },
    "screen_read_account": {
        "description": "Read an account from the 5250 green screen (no API exists).",
        "schema": {"account_id": ACCT},
        "required": ["account_id"],
    },
    "screen_update_status": {
        "description": "Change account status on the green screen. Needs human approval.",
        "schema": {"account_id": ACCT, "status": {"type": "string", "enum": ["A", "F", "C"]}},
        "required": ["account_id", "status"],
        "risky": True,
    },
    "recent_changes": {
        "description": "Account changes since the last call, from change data capture.",
        "schema": {},
        "required": [],
    },
}


class SchemaError(ValueError):
    pass


def _check(name: str, spec: dict, v):
    t = spec["type"]
    if t == "string":
        if not isinstance(v, str):
            raise SchemaError(f"{name}: expected string")
        if "maxLength" in spec and len(v) > spec["maxLength"]:
            raise SchemaError(f"{name}: too long")
        if "pattern" in spec and not re.match(spec["pattern"], v):
            raise SchemaError(f"{name}: wrong format")
        if "enum" in spec and v not in spec["enum"]:
            raise SchemaError(f"{name}: not allowed")
    elif t == "number":
        if isinstance(v, bool) or not isinstance(v, int | float) or v != v or v in (float("inf"), float("-inf")):
            raise SchemaError(f"{name}: expected finite number")
        if v < spec.get("minimum", float("-inf")):
            raise SchemaError(f"{name}: below minimum")
    elif t == "array":
        if not isinstance(v, list) or not v or len(v) > spec["maxItems"]:
            raise SchemaError(f"{name}: expected 1-{spec['maxItems']} items")
        for i, item in enumerate(v):
            _check(f"{name}[{i}]", spec["items"], item)


def validate_args(tool: str, args: dict) -> None:
    if tool not in TOOLS:
        raise SchemaError("unknown tool")
    t = TOOLS[tool]
    extra = set(args) - set(t["schema"])
    if extra:
        raise SchemaError(f"unexpected arguments: {sorted(extra)}")
    for r in t["required"]:
        if r not in args:
            raise SchemaError(f"missing {r}")
    for k, v in args.items():
        _check(k, t["schema"][k], v)


class LegacyTools:
    """Owns one running instance of every pattern. Use as a context manager."""

    def __init__(self, gw: LegacyGateway | None = None, screen_layout: str = "v1"):
        self.gw = gw or LegacyGateway()
        self.facade = Facade(self.gw)
        self.broker = Broker()
        self.responder = Responder(self.broker, self.gw)
        self.mq = MQClient(self.broker)
        self.screen_layout = screen_layout
        lib = build_library(self.gw.files["accounts"], Path(self.gw.workdir) / "BANKLIB.db")
        self.sql = Db2iConnection(lib, "AGENTRO", "demo-ro")
        self.cdc = CdcReader(self.gw.journal, Path(self.gw.workdir) / "cdc.checkpoint")
        self.approvals: dict[tuple[str, str], Approval] = {}

    def __enter__(self):
        self.facade.__enter__()
        self.responder.__enter__()
        return self

    def __exit__(self, *exc):
        self.responder.__exit__()
        self.facade.__exit__()

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": n,
                "description": t["description"],
                "inputSchema": {
                    "type": "object",
                    "properties": t["schema"],
                    "required": t["required"],
                    "additionalProperties": False,
                },
            }
            for n, t in TOOLS.items()
        ]

    def approve(self, account_id: str, status: str, approver: str, ticket: str) -> None:
        self.approvals[(account_id, status)] = Approval(approver, account_id, status, ticket)

    def call_tool(self, name: str, args: dict) -> dict:
        validate_args(name, args)
        out = getattr(self, f"_t_{name}")(**args)
        return mask_obj(out)

    def _t_get_account_balance(self, account_id):
        code, body = get_json(f"{self.facade.url}/accounts/{account_id}")
        return {"http": code, **body}

    def _t_get_policy(self, policy_id):
        return self.mq.request({"policy_id": policy_id})

    def _t_batch_account_lookup(self, account_ids):
        return {"results": self.gw.batch_lookup(account_ids)}

    def _t_query_accounts_sql(self, status, min_balance=-999999999):
        rows = self.sql.query(
            "SELECT ACCTID, ACCTNM, ACCTBL FROM BANKLIB/ACCTMST WHERE ACCTST = ? AND ACCTBL >= ?"
            " ORDER BY ACCTBL DESC FETCH FIRST 50 ROWS ONLY",
            (status, min_balance),
        )
        return {"rows": rows, "count": len(rows)}

    def _screen(self, user, password, read_only=True):
        return ScreenTool(GreenScreen(self.gw, self.screen_layout), user, password, read_only=read_only)

    def _t_screen_read_account(self, account_id):
        return self._screen("AGENTRO", "demo-ro").read_account(account_id)

    def _t_screen_update_status(self, account_id, status):
        approval = self.approvals.pop((account_id, status), None)
        return self._screen("AGENTRW", "demo-rw", read_only=False).update_status(account_id, status, approval)

    def _t_recent_changes(self):
        return {"events": self.cdc.poll()}
