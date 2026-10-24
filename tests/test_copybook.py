import pytest

from legacyagents import copybook as cb
from legacyagents.data import accounts, layout


@pytest.fixture
def acct():
    return layout("ACCTREC")


def test_account_layout_offsets(acct):
    assert acct.length == 96
    assert [(f.name, f.offset, f.length) for f in acct.fields][3] == ("ACCT-BALANCE", 41, 6)


def test_policy_and_batch_lengths():
    assert layout("POLREC").length == 65
    assert layout("BATREQ").length == 18
    assert layout("BATRES").length == 33


@pytest.mark.parametrize(
    "value,digits,signed,hexv",
    [
        (12345, 5, True, "12345c"),
        (-12345, 5, True, "12345d"),
        (0, 3, True, "000c"),
        (7, 3, False, "007f"),
        (-1, 11, True, "00000000001d"),
        (99999999999, 11, True, "99999999999c"),
    ],
)
def test_pack_known_values(value, digits, signed, hexv):
    assert cb.pack(value, digits, signed).hex() == hexv
    assert cb.unpack(bytes.fromhex(hexv)) == value


def test_unpack_rejects_bad_nibble():
    with pytest.raises(cb.FieldError):
        cb.unpack(bytes.fromhex("1a3c"))


def test_unpack_rejects_missing_sign():
    with pytest.raises(cb.FieldError):
        cb.unpack(bytes.fromhex("1234"))


@pytest.mark.parametrize("v", [0, 5, -5, 123, -123, 9999])
def test_zoned_overpunch_roundtrip(v):
    s = cb._zone_encode(v, 4, True)
    assert len(s) == 4 and cb._zone_decode(s, True) == v


def test_zoned_negative_uses_overpunch():
    assert cb._zone_encode(-123, 4, True) == "012L"


def test_record_roundtrip(acct):
    for r in accounts(50):
        raw = cb.encode(acct, r)
        assert len(raw) == 96
        assert cb.decode(acct, raw) == r


def test_ebcdic_roundtrip(acct):
    r = accounts(1)[0]
    raw = cb.encode(acct, r)
    e = cb.transcode(raw, acct, cb.ASCII, cb.EBCDIC)
    assert e[:2] == "HR".encode("cp037") and e != raw
    assert e[41:47] == raw[41:47]  # packed bytes untouched
    assert cb.decode(acct, e, cb.EBCDIC) == r
    assert cb.transcode(e, acct, cb.EBCDIC, cb.ASCII) == raw


def test_ebcdic_direct_encode(acct):
    r = accounts(1)[0]
    assert cb.decode(acct, cb.encode(acct, r, cb.EBCDIC), cb.EBCDIC) == r


def test_comp_binary_field():
    lay = cb.parse_copybook("01 R. 05 N PIC S9(4) COMP. 05 M PIC 9(9) BINARY.")
    assert lay.length == 6
    raw = cb.encode(lay, {"N": -300, "M": 123456789})
    assert cb.decode(lay, raw) == {"N": -300, "M": 123456789}


def test_signed_display_field():
    lay = cb.parse_copybook("01 R. 05 AMT PIC S9(5)V99.")
    assert cb.decode(lay, cb.encode(lay, {"AMT": "-12.34"})) == {"AMT": "-12.34"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("ACCT-ID", "X" * 11),
        ("ACCT-NAME", 5),
        ("ACCT-BALANCE", "1000000000.00"),
        ("ACCT-BALANCE", "1.001"),
        ("ACCT-BALANCE", "abc"),
        ("ACCT-BALANCE", "NaN"),
        ("ACCT-OPEN-DATE", -1),
        ("ACCT-NAME", "Zoë"),
        ("ACCT-BALANCE", True),
    ],
)
def test_validation_rejects(acct, field, value):
    r = dict(accounts(1)[0])
    r[field] = value
    with pytest.raises(cb.FieldError):
        cb.encode(acct, r)


def test_validation_rejects_extra_and_missing(acct):
    r = dict(accounts(1)[0])
    with pytest.raises(cb.FieldError):
        cb.encode(acct, {**r, "EXTRA": 1})
    del r["ACCT-ID"]
    with pytest.raises(cb.FieldError):
        cb.encode(acct, r)


def test_error_messages_never_echo_value(acct):
    r = dict(accounts(1)[0])
    r["ACCT-EMAIL"] = "someone.long.address@example.test" * 2
    with pytest.raises(cb.FieldError) as e:
        cb.encode(acct, r)
    assert "@" not in str(e.value)


def test_decode_wrong_length(acct):
    with pytest.raises(cb.FieldError):
        cb.decode(acct, b"x" * 95)


@pytest.mark.parametrize(
    "text",
    [
        "01 R. 05 A PIC X(3) OCCURS 2 TIMES.",
        "01 R. 05 A PIC X. 05 B REDEFINES A PIC 9.",
        "01 R. 05 A PIC X. 88 YES VALUE 'Y'.",
        "01 R. 05 A PIC Z(5).",
        "01 R.",
        "01 R. 05 A PIC X(2) COMP-3.",
    ],
)
def test_unsupported_syntax_fails_loudly(text):
    with pytest.raises(cb.CopybookError):
        cb.parse_copybook(text)


def test_file_read_write(tmp_path, acct):
    rows = accounts(10)
    cb.write_records(tmp_path / "A.DAT", acct, rows)
    assert cb.read_records(tmp_path / "A.DAT", acct) == rows


def test_file_bad_size(tmp_path, acct):
    (tmp_path / "B.DAT").write_bytes(b"x" * 100)
    with pytest.raises(cb.FieldError):
        cb.read_records(tmp_path / "B.DAT", acct)
