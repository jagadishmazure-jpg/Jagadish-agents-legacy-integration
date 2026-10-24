"""A small COBOL copybook parser and codec.

Supports level-numbered elementary items with PIC X(n), 9(n), S9(n)V9(m) in DISPLAY (zoned, with
trailing overpunch sign when signed), COMP-3 (packed decimal) and COMP/BINARY. Records convert to
JSON-friendly dicts and back, in ASCII or EBCDIC (code page 037). OCCURS, REDEFINES and level-88
items are not supported and raise CopybookError so nothing is silently misread.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

ASCII = "ascii"
EBCDIC = "cp037"


class CopybookError(ValueError):
    """Unsupported copybook syntax."""


class FieldError(ValueError):
    """A value does not fit its copybook field. Messages name the field, never the value."""


@dataclass(frozen=True)
class Field:
    name: str
    kind: str  # "X", "9"
    digits: int  # total digits (numeric) or length (alphanumeric)
    scale: int
    signed: bool
    usage: str  # DISPLAY, COMP-3, COMP
    offset: int = 0

    @property
    def length(self) -> int:
        if self.kind == "X" or self.usage == "DISPLAY":
            return self.digits
        if self.usage == "COMP-3":
            return self.digits // 2 + 1
        if self.digits <= 4:
            return 2
        if self.digits <= 9:
            return 4
        return 8


@dataclass(frozen=True)
class Layout:
    name: str
    fields: tuple[Field, ...]

    @property
    def length(self) -> int:
        return sum(f.length for f in self.fields)

    def field(self, name: str) -> Field:
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(name)


_PIC = re.compile(r"^(S)?([X9])(?:\((\d+)\))?((?:9|\(\d+\))*)(?:V(9(?:\((\d+)\))?(?:9)*))?$")


def _count(spec: str) -> int:
    total = 0
    for m in re.finditer(r"([X9])(?:\((\d+)\))?", spec):
        total += int(m.group(2)) if m.group(2) else 1
    return total


def _parse_pic(pic: str) -> tuple[str, int, int, bool]:
    pic = pic.upper()
    signed = pic.startswith("S")
    body = pic[1:] if signed else pic
    if body.startswith("X"):
        if signed or not re.fullmatch(r"X(\(\d+\))?X*", body):
            raise CopybookError(f"unsupported PIC {pic}")
        return "X", _count(body), 0, False
    if not re.fullmatch(r"(9(\(\d+\))?)+(V(9(\(\d+\))?)+)?", body):
        raise CopybookError(f"unsupported PIC {pic}")
    whole, _, frac = body.partition("V")
    scale = _count(frac) if frac else 0
    return "9", _count(whole) + scale, scale, signed


def parse_copybook(text: str, name: str = "") -> Layout:
    lines = []
    for raw in text.splitlines():
        line = raw.split("*>", 1)[0].strip()
        if line:
            lines.append(line)
    stmts = " ".join(lines).split(".")
    fields: list[Field] = []
    offset = 0
    for stmt in stmts:
        toks = stmt.split()
        if not toks:
            continue
        if not toks[0].isdigit():
            raise CopybookError(f"expected level number in: {stmt.strip()[:40]}")
        upper = [t.upper() for t in toks]
        for bad in ("OCCURS", "REDEFINES"):
            if bad in upper:
                raise CopybookError(f"{bad} is not supported")
        if toks[0] == "88":
            raise CopybookError("level-88 condition names are not supported")
        if "PIC" not in upper and "PICTURE" not in upper:
            name = name or toks[1]
            continue  # group item
        i = upper.index("PIC") if "PIC" in upper else upper.index("PICTURE")
        kind, digits, scale, signed = _parse_pic(toks[i + 1])
        rest = " ".join(upper[i + 2 :])
        if "COMP-3" in rest or "PACKED-DECIMAL" in rest:
            usage = "COMP-3"
        elif re.search(r"\b(COMP|BINARY|COMP-4)\b", rest):
            usage = "COMP"
        else:
            usage = "DISPLAY"
        if kind == "X" and usage != "DISPLAY":
            raise CopybookError("alphanumeric field cannot be COMP")
        f = Field(toks[1].upper(), kind, digits, scale, signed, usage, offset)
        fields.append(f)
        offset += f.length
    if not fields:
        raise CopybookError("no elementary fields")
    return Layout(name.upper(), tuple(fields))


def load(path: str | Path) -> Layout:
    p = Path(path)
    return parse_copybook(p.read_text(), p.stem)


# ---- packed decimal -------------------------------------------------------------------------


def pack(value: int, digits: int, signed: bool) -> bytes:
    sign = 0xD if value < 0 else (0xC if signed else 0xF)
    s = str(abs(value)).rjust(digits | 1, "0")  # odd digit count fills whole bytes
    nibbles = [int(c) for c in s] + [sign]
    return bytes((nibbles[i] << 4) | nibbles[i + 1] for i in range(0, len(nibbles), 2))


def unpack(data: bytes) -> int:
    nibbles = []
    for b in data:
        nibbles += [b >> 4, b & 0xF]
    sign = nibbles.pop()
    if any(n > 9 for n in nibbles) or sign < 0xA:
        raise FieldError("invalid packed decimal")
    v = int("".join(map(str, nibbles)) or "0")
    return -v if sign == 0xD else v


# ---- zoned decimal (DISPLAY) with trailing overpunch -------------------------------------------

_POS = "{ABCDEFGHI"
_NEG = "}JKLMNOPQR"


def _zone_encode(value: int, digits: int, signed: bool) -> str:
    s = str(abs(value)).rjust(digits, "0")
    if not signed:
        return s
    last = int(s[-1])
    return s[:-1] + (_NEG[last] if value < 0 else _POS[last])


def _zone_decode(s: str, signed: bool) -> int:
    if signed and s and s[-1] in _POS + _NEG:
        last = s[-1]
        neg = last in _NEG
        s = s[:-1] + str((_NEG if neg else _POS).index(last))
        v = int(s)
        return -v if neg else v
    if not s.isdigit():
        raise FieldError("non-numeric data in DISPLAY numeric field")
    return int(s)


# ---- record codec ---------------------------------------------------------------------------


def _to_int(f: Field, value) -> int:
    try:
        d = Decimal(str(value))
    except Exception as exc:
        raise FieldError(f"{f.name}: not a number") from exc
    if not d.is_finite():
        raise FieldError(f"{f.name}: not a finite number")
    scaled = d.scaleb(f.scale)
    if scaled != scaled.to_integral_value():
        raise FieldError(f"{f.name}: more than {f.scale} decimal places")
    n = int(scaled)
    if n < 0 and not f.signed:
        raise FieldError(f"{f.name}: negative value in unsigned field")
    if abs(n) >= 10**f.digits:
        raise FieldError(f"{f.name}: exceeds {f.digits} digits")
    return n


def validate(layout: Layout, data: dict) -> None:
    """Raise FieldError if data would not fit the copybook exactly. Extra or missing keys fail."""
    names = {f.name for f in layout.fields}
    extra = set(data) - names
    if extra:
        raise FieldError(f"unknown fields: {sorted(extra)}")
    missing = names - set(data)
    if missing:
        raise FieldError(f"missing fields: {sorted(missing)}")
    for f in layout.fields:
        v = data[f.name]
        if f.kind == "X":
            if not isinstance(v, str):
                raise FieldError(f"{f.name}: expected text")
            if len(v) > f.digits:
                raise FieldError(f"{f.name}: longer than {f.digits} characters")
            try:
                v.encode(ASCII)
            except UnicodeEncodeError as exc:
                raise FieldError(f"{f.name}: non-ASCII characters") from exc
        else:
            if isinstance(v, bool):
                raise FieldError(f"{f.name}: expected a number")
            _to_int(f, v)


def encode(layout: Layout, data: dict, codepage: str = ASCII) -> bytes:
    validate(layout, data)
    out = bytearray()
    for f in layout.fields:
        v = data[f.name]
        if f.kind == "X":
            out += v.ljust(f.digits).encode(codepage)
        elif f.usage == "COMP-3":
            out += pack(_to_int(f, v), f.digits, f.signed)
        elif f.usage == "COMP":
            out += _to_int(f, v).to_bytes(f.length, "big", signed=f.signed)
        else:
            out += _zone_encode(_to_int(f, v), f.digits, f.signed).encode(codepage)
    return bytes(out)


def decode(layout: Layout, raw: bytes, codepage: str = ASCII) -> dict:
    if len(raw) != layout.length:
        raise FieldError(f"record is {len(raw)} bytes, copybook {layout.name} expects {layout.length}")
    out: dict = {}
    for f in layout.fields:
        chunk = raw[f.offset : f.offset + f.length]
        if f.kind == "X":
            out[f.name] = chunk.decode(codepage).rstrip(" ")
            continue
        if f.usage == "COMP-3":
            n = unpack(chunk)
        elif f.usage == "COMP":
            n = int.from_bytes(chunk, "big", signed=f.signed)
        else:
            n = _zone_decode(chunk.decode(codepage), f.signed)
        out[f.name] = n if f.scale == 0 else str(Decimal(n).scaleb(-f.scale))
    return out


def transcode(raw: bytes, layout: Layout, src: str, dst: str) -> bytes:
    """Convert a record between code pages, touching only text and zoned fields (never packed bytes)."""
    out = bytearray(raw)
    for f in layout.fields:
        if f.kind == "X" or f.usage == "DISPLAY":
            chunk = raw[f.offset : f.offset + f.length].decode(src).encode(dst)
            out[f.offset : f.offset + f.length] = chunk
    return bytes(out)


def read_records(path: str | Path, layout: Layout, codepage: str = ASCII) -> list[dict]:
    data = Path(path).read_bytes()
    n = layout.length
    if len(data) % n:
        raise FieldError("file size is not a multiple of the record length")
    return [decode(layout, data[i : i + n], codepage) for i in range(0, len(data), n)]


def write_records(path: str | Path, layout: Layout, rows: list[dict], codepage: str = ASCII) -> None:
    Path(path).write_bytes(b"".join(encode(layout, r, codepage) for r in rows))
