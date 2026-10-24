"""A 5250-style green-screen simulator (24 x 80, 1-based rows and columns) in front of the gateway.

Like a real block-mode terminal, the host sends a full screen, the user types only into input
fields, and nothing happens until an attention key (Enter, F3, F10) is pressed. Typing into a
protected position is refused. `layout` "v1" is the original; "v2" moves the detail screen two rows
down and three columns right (a banner was added); "v3" renames one label."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .gateway import LegacyGateway

ROWS, COLS = 24, 80


@dataclass
class InputField:
    row: int
    col: int
    length: int
    hidden: bool = False
    value: str = ""


class ProtectedField(RuntimeError):
    pass


class GreenScreen:
    def __init__(self, gw: LegacyGateway, layout: str = "v1", users: dict[str, str] | None = None):
        self.gw, self.layout = gw, layout
        self.users = users or {"AGENTRO": "demo-ro", "AGENTRW": "demo-rw"}
        self.user = ""
        self.state = "SIGNON"
        self.message = ""
        self.account: dict | None = None
        self.update_mode = False
        self.write_count = 0
        self.fields: dict[str, InputField] = {}
        self._render()

    # ---- drawing ----
    def _blank(self):
        self.buf = [[" "] * COLS for _ in range(ROWS)]

    def _at(self, row: int, col: int, text: str):
        for i, ch in enumerate(text):
            if col - 1 + i < COLS:
                self.buf[row - 1][col - 1 + i] = ch

    def _render(self):
        self._blank()
        self.fields = {}
        getattr(self, f"_draw_{self.state.lower()}")()
        for f in self.fields.values():
            self._at(f.row, f.col, ("*" * len(f.value) if f.hidden else f.value).ljust(f.length, "_"))
        if self.message:
            self._at(24, 2, self.message[:78])

    def _draw_signon(self):
        self._at(1, 2, "SIGNON")
        self._at(1, 33, "Sign On")
        self._at(6, 17, "User  . . . . . . . . . :")
        self._at(7, 17, "Password  . . . . . . . :")
        self.fields = {"user": InputField(6, 44, 10), "password": InputField(7, 44, 10, hidden=True)}

    def _draw_menu(self):
        self._at(1, 2, "MAIN01")
        self._at(1, 25, "Harbor Ridge Savings - Main Menu")
        self._at(4, 5, "1. Account inquiry")
        self._at(5, 5, "90. Sign off")
        self._at(20, 2, "Selection ===>")
        self.fields = {"option": InputField(20, 17, 2)}

    def _draw_inquiry(self):
        self._at(1, 2, "ACI010")
        self._at(1, 30, "Account Inquiry")
        self._at(5, 2, "Account number . :")
        self._at(22, 2, "F3=Exit")
        self.fields = {"account": InputField(5, 22, 10)}

    def _draw_detail(self):
        dr, dc = (2, 3) if self.layout == "v2" else (0, 0)
        name_label = "Customer . . . :" if self.layout == "v3" else "Name . . . . . :"
        a = self.account or {}
        self._at(1, 2, "ACI020")
        self._at(1, 30, "Account Detail")
        if self.layout == "v2":
            self._at(3, 2, "** Notice: branch hours change next month **")
        rows = [
            ("Account  . . . :", a.get("ACCT-ID", "")),
            (name_label, a.get("ACCT-NAME", "")),
            ("Type . . . . . :", a.get("ACCT-TYPE", "")),
            ("Balance  . . . :", a.get("ACCT-BALANCE", "")),
            ("Status . . . . :", a.get("ACCT-STATUS", "")),
        ]
        for i, (label, value) in enumerate(rows):
            self._at(6 + i + dr, 2 + dc, label)
            self._at(6 + i + dr, 20 + dc, str(value))
        self._at(22, 2, "F3=Exit  F10=Change status")
        if self.update_mode:
            self._at(12 + dr, 2 + dc, "New status . . :")
            self.fields = {"new_status": InputField(12 + dr, 20 + dc, 1)}

    # ---- terminal API ----
    def text(self) -> list[str]:
        return ["".join(r) for r in self.buf]

    def screen_hash(self) -> str:
        return hashlib.sha256("\n".join(self.text()).encode()).hexdigest()[:12]

    def type_at(self, row: int, col: int, text: str):
        for f in self.fields.values():
            if f.row == row and f.col <= col < f.col + f.length:
                start = col - f.col
                if start + len(text) > f.length:
                    raise ProtectedField("text runs past the end of the input field")
                f.value = (f.value.ljust(start)[:start] + text)[: f.length]
                self._redraw_fields()
                return
        raise ProtectedField(f"row {row} col {col} is not an input field")

    def _redraw_fields(self):
        values = {k: f.value for k, f in self.fields.items()}
        self._render()
        for k, v in values.items():
            if k in self.fields:
                self.fields[k].value = v
        for f in self.fields.values():
            self._at(f.row, f.col, ("*" * len(f.value) if f.hidden else f.value).ljust(f.length, "_"))

    def press(self, key: str):
        vals = {k: f.value.strip() for k, f in self.fields.items()}
        self.message = ""
        if key == "F3":
            self.state, self.update_mode = ("MENU" if self.state != "SIGNON" else "SIGNON"), False
        elif self.state == "SIGNON" and key == "ENTER":
            if self.users.get(vals.get("user", "")) == vals.get("password"):
                self.user, self.state = vals["user"], "MENU"
            else:
                self.message = "CPF1120 User or password not correct."
        elif self.state == "MENU" and key == "ENTER":
            if vals.get("option") == "1":
                self.state = "INQUIRY"
            elif vals.get("option") == "90":
                self.state, self.user = "SIGNON", ""
            else:
                self.message = "Option not valid."
        elif self.state == "INQUIRY" and key == "ENTER":
            try:
                rec = self.gw.get_account(vals.get("account", ""))
            except Exception:
                rec, self.message = None, "Account number not valid or system busy."
            if rec:
                self.account, self.state = rec, "DETAIL"
            elif not self.message:
                self.message = "Account not found."
        elif self.state == "DETAIL" and key == "F10":
            if self.user != "AGENTRW":
                self.message = "CPF2189 Not authorized to change status."
            else:
                self.update_mode = True
        elif self.state == "DETAIL" and key == "ENTER" and self.update_mode:
            new = vals.get("new_status", "")
            key_id = getattr(self, "pending_idem_key", "") or f"screen-{self.account['ACCT-ID']}-{new}"
            try:
                r = self.gw.update_status(self.account["ACCT-ID"], new, key_id, self.user, getattr(self, "pending_approver", ""))
                self.write_count += 0 if r.get("replayed") else 1
                self.account = self.gw.get_account(self.account["ACCT-ID"])
                self.message = "Status changed." if not r.get("replayed") else "Already applied."
            except Exception as exc:
                self.message = f"Change refused: {type(exc).__name__}"
            self.update_mode = False
        self._render()
