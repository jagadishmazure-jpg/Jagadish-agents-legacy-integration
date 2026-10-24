"""Synthetic data for two fictional companies: Harbor Ridge Savings (accounts) and Lakeshore Mutual
(insurance policies). Deterministic from a seed; every email uses the reserved .test domain."""

from __future__ import annotations

import random
from pathlib import Path

from . import copybook

ROOT = Path(__file__).resolve().parents[2]
COPYBOOKS = ROOT / "cobol" / "copybooks"
FIRST = ["Avery", "Blake", "Casey", "Devon", "Emery", "Finley", "Gray", "Harper", "Indy", "Jordan", "Kai", "Logan"]
LAST = ["Alder", "Brook", "Cedar", "Dale", "Elm", "Fern", "Glen", "Heath", "Ivy", "Juniper", "Knoll", "Laurel"]


def layout(name: str) -> copybook.Layout:
    return copybook.load(COPYBOOKS / f"{name}.cpy")


def accounts(n: int = 200, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        cents = rng.randint(-50_000, 25_000_000)
        rows.append(
            {
                "ACCT-ID": f"HR{100000 + i:08d}",
                "ACCT-NAME": f"{first} {last}",
                "ACCT-TYPE": rng.choice("CSL"),
                "ACCT-BALANCE": f"{cents / 100:.2f}",
                "ACCT-OPEN-DATE": int(f"{rng.randint(1985, 2024)}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"),
                "ACCT-STATUS": "C" if i % 17 == 5 else "A",
                "ACCT-EMAIL": f"{first.lower()}.{last.lower()}{i}@example.test",
            }
        )
    return rows


def policies(n: int = 100, seed: int = 11) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        rows.append(
            {
                "POL-ID": f"LM-{2000000 + i:09d}",
                "POL-HOLDER": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
                "POL-PREMIUM": f"{rng.randint(20_000, 900_000) / 100:.2f}",
                "POL-COVER": rng.randint(10, 2000) * 1000,
                "POL-STATUS": rng.choice("AAAL"),
                "POL-RENEW-DATE": int(f"2027{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"),
            }
        )
    return rows


def seed_files(workdir: Path, n_accounts: int = 200, n_policies: int = 100) -> dict[str, Path]:
    workdir.mkdir(parents=True, exist_ok=True)
    acct, pol = workdir / "ACCOUNTS.DAT", workdir / "POLICIES.DAT"
    copybook.write_records(acct, layout("ACCTREC"), accounts(n_accounts))
    copybook.write_records(pol, layout("POLREC"), policies(n_policies))
    return {"accounts": acct, "policies": pol}
