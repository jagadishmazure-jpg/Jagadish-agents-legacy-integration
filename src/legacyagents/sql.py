"""DB2-for-i style SQL access, simulated with SQLite.

IBM i conventions kept: a library (schema) per application (BANKLIB), short upper-case file and
column names (ACCTMST, ACCTID, ACCTNM ...), DECIMAL(p,s) money, dates as 8-digit numbers, and both
naming styles (SQL `BANKLIB.ACCTMST` and system `BANKLIB/ACCTMST`). The agent connects as a
read-only user profile: the database file is opened read-only and an authorizer refuses anything
but reads, so even a crafted statement cannot change data."""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

from . import copybook
from .data import layout

READ_ONLY_USERS = {"AGENTRO"}
MAX_ROWS = 500


class SqlRefused(PermissionError):
    pass


def build_library(accounts_dat: Path, dest: Path) -> Path:
    """Load the COBOL master file into a BANKLIB library file (like a DDS physical file)."""
    rows = copybook.read_records(accounts_dat, layout("ACCTREC"))
    dest.unlink(missing_ok=True)
    db = sqlite3.connect(dest)
    db.execute(
        "CREATE TABLE ACCTMST (ACCTID CHAR(10) PRIMARY KEY, ACCTNM CHAR(30), ACCTTP CHAR(1),"
        " ACCTBL DECIMAL(11,2), OPNDTE NUMERIC(8,0), ACCTST CHAR(1), EMAIL CHAR(40))"
    )
    db.executemany(
        "INSERT INTO ACCTMST VALUES (?,?,?,?,?,?,?)",
        [
            (
                r["ACCT-ID"],
                r["ACCT-NAME"],
                r["ACCT-TYPE"],
                r["ACCT-BALANCE"],
                r["ACCT-OPEN-DATE"],
                r["ACCT-STATUS"],
                r["ACCT-EMAIL"],
            )
            for r in rows
        ],
    )
    db.commit()
    db.close()
    return dest


_ALLOWED = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}


def _authorizer(action, *_):
    return sqlite3.SQLITE_OK if action in _ALLOWED else sqlite3.SQLITE_DENY


class Db2iConnection:
    def __init__(self, library_file: Path, user: str, password: str, expected_password: str | None = None):
        expected_password = expected_password or os.environ.get("LEGACY_DEMO_RO_PASSWORD", "demo-ro")
        if user not in READ_ONLY_USERS:
            raise SqlRefused("only read-only user profiles may connect")
        if password != expected_password:
            raise SqlRefused("CPF2204 user profile or password not valid")
        uri = f"file:{Path(library_file).as_posix()}?mode=ro"
        self.db = sqlite3.connect(uri, uri=True, check_same_thread=False)
        self.db.execute("ATTACH DATABASE ? AS BANKLIB", (uri,))
        self.db.set_authorizer(_authorizer)

    @staticmethod
    def translate(sql: str) -> str:
        s = re.sub(r"\b([A-Z][A-Z0-9_]{0,9})/([A-Z][A-Z0-9_]{0,9})\b", r"\1.\2", sql.strip().rstrip(";"))
        m = re.search(r"\s+FETCH\s+FIRST\s+(\d+)\s+ROWS?\s+ONLY\s*$", s, re.I)
        if m:
            s = s[: m.start()] + f" LIMIT {min(int(m.group(1)), MAX_ROWS)}"
        return s

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        s = self.translate(sql)
        if not re.match(r"^\s*(SELECT|WITH)\b", s, re.I) or ";" in s:
            raise SqlRefused("only a single SELECT is allowed")
        try:
            cur = self.db.execute(s, params)
        except sqlite3.DatabaseError as exc:
            raise SqlRefused(f"statement refused: {type(exc).__name__}") from exc
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r, strict=True)) for r in cur.fetchmany(MAX_ROWS)]
