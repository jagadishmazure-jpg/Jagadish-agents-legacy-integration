"""Screen-scraping agent tool for the green screen. Navigates by row/column like an emulator
script, but checks anchors (screen id + label text at known positions) before trusting any value,
so a layout shift is detected instead of returning the wrong data. Read-only unless explicitly
opened for writes, and every write needs a matching human approval."""

from __future__ import annotations

from dataclasses import dataclass

from .screen import GreenScreen

# value positions on the detail screen, v1 layout: name -> (row, col, length)
V1_VALUES = {
    "ACCT-ID": (6, 20, 10),
    "ACCT-NAME": (7, 20, 30),
    "ACCT-TYPE": (8, 20, 1),
    "ACCT-BALANCE": (9, 20, 14),
    "ACCT-STATUS": (10, 20, 1),
}
V1_ANCHORS = [
    (1, 2, "ACI020"),
    (6, 2, "Account  . . . :"),
    (7, 2, "Name . . . . . :"),
    (9, 2, "Balance  . . . :"),
    (10, 2, "Status . . . . :"),
]
LABEL_FOR = {
    "ACCT-ID": "Account  . . . :",
    "ACCT-NAME": "Name . . . . . :",
    "ACCT-TYPE": "Type . . . . . :",
    "ACCT-BALANCE": "Balance  . . . :",
    "ACCT-STATUS": "Status . . . . :",
}


class LayoutDrift(RuntimeError):
    def __init__(self, screen_id: str, mismatches: list[str]):
        super().__init__(f"screen {screen_id} layout changed: {', '.join(mismatches)}")
        self.mismatches = mismatches


class NavigationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Approval:
    approver: str
    account: str
    status: str
    ticket: str


def read_at(lines: list[str], row: int, col: int, length: int) -> str:
    return lines[row - 1][col - 1 : col - 1 + length].strip()


def check_anchors(lines: list[str], anchors) -> list[str]:
    return [f"'{t}' not at {r},{c}" for r, c, t in anchors if read_at(lines, r, c, len(t)) != t]


class ScreenTool:
    def __init__(self, screen: GreenScreen, user: str, password: str, read_only: bool = True, relocate: bool = False):
        self.s, self.user, self.password = screen, user, password
        self.read_only, self.relocate = read_only, relocate
        self.drift_events: list[str] = []

    def _expect(self, screen_id: str):
        lines = self.s.text()
        if read_at(lines, 1, 2, 6) != screen_id:
            raise NavigationError(f"expected {screen_id}, got {read_at(lines, 1, 2, 6)!r}: {self.s.message}")

    def _goto_detail(self, acct_id: str):
        if self.s.state == "SIGNON":
            self._expect("SIGNON")
            self.s.type_at(6, 44, self.user)
            self.s.type_at(7, 44, self.password)
            self.s.press("ENTER")
        if self.s.state != "MENU":
            self.s.press("F3")
        self._expect("MAIN01")
        self.s.type_at(20, 17, "1")
        self.s.press("ENTER")
        self._expect("ACI010")
        self.s.type_at(5, 22, acct_id)
        self.s.press("ENTER")
        self._expect("ACI020")

    def _extract(self) -> dict:
        lines = self.s.text()
        bad = check_anchors(lines, V1_ANCHORS)
        if not bad:
            return {k: read_at(lines, *pos) for k, pos in V1_VALUES.items()}
        self.drift_events.append("; ".join(bad))
        if not self.relocate:
            raise LayoutDrift("ACI020", bad)
        out = {}
        for k, label in LABEL_FOR.items():
            hit = [(i + 1, line.find(label) + 1) for i, line in enumerate(lines) if label in line]
            if len(hit) != 1:
                raise LayoutDrift("ACI020", bad + [f"label for {k} not found once"])
            r, c = hit[0]
            out[k] = read_at(lines, r, c + 18, V1_VALUES[k][2])
        out["_relocated"] = True
        return out

    def read_account(self, acct_id: str) -> dict:
        self._goto_detail(acct_id)
        return self._extract()

    def update_status(self, acct_id: str, status: str, approval: Approval | None = None) -> dict:
        if self.read_only:
            raise PermissionError("screen tool is read-only")
        if approval is None:
            return {"pending_approval": True, "account": acct_id, "status": status}
        if (approval.account, approval.status) != (acct_id, status) or not approval.approver:
            raise PermissionError("approval does not match this change")
        self._goto_detail(acct_id)
        self._extract()  # refuse to type into a screen whose layout we no longer trust
        self.s.pending_approver, self.s.pending_idem_key = approval.approver, approval.ticket
        self.s.press("F10")
        if "new_status" not in self.s.fields:
            raise PermissionError(self.s.message or "update not allowed")
        f = self.s.fields["new_status"]
        self.s.type_at(f.row, f.col, status)
        self.s.press("ENTER")
        return {"message": self.s.message, "status": read_at(self.s.text(), 10, 20, 1)}


def naive_read(screen: GreenScreen) -> dict:
    """What a brittle script does: read fixed positions with no checks. Used only to measure."""
    lines = screen.text()
    return {k: read_at(lines, *pos) for k, pos in V1_VALUES.items()}
