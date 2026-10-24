"""Run the compiled GnuCOBOL programs as subprocesses (the 'legacy system')."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .data import ROOT

SRC = ROOT / "cobol"
BUILD = ROOT / "build"
PROGRAMS = ("ACCTINQ", "POLINQ", "ACCTBAT", "ACCTUPD")


class LegacyUnavailable(RuntimeError):
    """The legacy system could not be reached or did not answer in time."""


def build(force: bool = False) -> list[str]:
    if not shutil.which("cobc"):
        raise LegacyUnavailable("GnuCOBOL (cobc) is not installed")
    BUILD.mkdir(exist_ok=True)
    built = []
    for p in PROGRAMS:
        exe, src = BUILD / p, SRC / f"{p}.cbl"
        if force or not exe.exists() or exe.stat().st_mtime < src.stat().st_mtime:
            subprocess.run(  # noqa: S603 - fixed compiler command
                ["cobc", "-x", "-free", "-I", str(SRC / "copybooks"), "-o", str(exe), str(src)],  # noqa: S607
                check=True,
                capture_output=True,
            )
            built.append(p)
    return built


class CobolRuntime:
    """Calls one COBOL program at a time, with a timeout. `down=True` simulates an outage."""

    def __init__(self, workdir: Path, timeout: float = 5.0):
        self.workdir = Path(workdir)
        self.timeout = timeout
        self.down = False
        self.calls = 0

    def run(self, program: str, arg: str, files: dict[str, Path]) -> int:
        if program not in PROGRAMS:
            raise ValueError("unknown program")
        self.calls += 1
        if self.down:
            raise LegacyUnavailable("legacy region is down")
        env = {**os.environ, **{k: str(v) for k, v in files.items()}}
        try:
            r = subprocess.run(  # noqa: S603 - fixed program list, no shell
                [str(BUILD / program), arg], env=env, capture_output=True, timeout=self.timeout, check=False
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise LegacyUnavailable(f"{program} did not answer") from exc
        if r.returncode == 8:
            raise LegacyUnavailable(f"{program} could not open its files")
        return r.returncode

    def inquire(self, program: str, file_env: str, data_file: Path, key: str) -> bytes | None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "OUT.DAT"
            rc = self.run(program, key, {file_env: data_file, "OUTFILE": out})
            if rc == 4:
                return None
            return out.read_bytes()


def timed(fn, *a, **kw):
    t = time.perf_counter()
    r = fn(*a, **kw)
    return r, (time.perf_counter() - t) * 1000
