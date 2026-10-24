import pytest

from legacyagents.guards import CircuitBreaker, CircuitOpen, IdempotencyStore, RateLimited, TokenBucket, mask, mask_obj


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_token_bucket_burst_then_refill():
    c = Clock()
    b = TokenBucket(2, 3, c)
    for _ in range(3):
        b.acquire()
    with pytest.raises(RateLimited):
        b.acquire()
    c.t = 0.5
    b.acquire()
    assert b.rejected == 1


@pytest.mark.parametrize("rate,burst", [(0, 1), (-1, 1), (1, 0), (1, -5)])
def test_token_bucket_rejects_bad_config(rate, burst):
    with pytest.raises(ValueError):
        TokenBucket(rate, burst)


def boom():
    raise OSError("down")


def test_breaker_opens_and_short_circuits():
    c = Clock()
    br = CircuitBreaker(3, 10, c)
    for _ in range(3):
        with pytest.raises(OSError):
            br.call(boom)
    assert br.state == "open"
    with pytest.raises(CircuitOpen):
        br.call(lambda: 1)
    assert br.short_circuited == 1


def test_breaker_half_open_success_closes():
    c = Clock()
    br = CircuitBreaker(1, 10, c)
    with pytest.raises(OSError):
        br.call(boom)
    c.t = 11
    assert br.call(lambda: 42) == 42 and br.state == "closed"


def test_breaker_half_open_failure_reopens():
    c = Clock()
    br = CircuitBreaker(1, 10, c)
    with pytest.raises(OSError):
        br.call(boom)
    c.t = 11
    with pytest.raises(OSError):
        br.call(boom)
    assert br.state == "open"


def test_breaker_success_resets_count():
    br = CircuitBreaker(2, 10)
    with pytest.raises(OSError):
        br.call(boom)
    br.call(lambda: 1)
    with pytest.raises(OSError):
        br.call(boom)
    assert br.state == "closed"


@pytest.mark.parametrize(
    "text,token",
    [
        ("mail a.b@example.test now", "[EMAIL]"),
        ("card 4111 1111 1111 1111", "[CARD]"),
        ("card 4111-1111-1111-1111", "[CARD]"),
        ("ssn 123-45-6789", "[SSN]"),
        ("call (555) 123-4567", "[PHONE]"),
        ("call 555.123.4567", "[PHONE]"),
        ("call +1 555 123 4567", "[PHONE]"),
    ],
)
def test_mask_pii(text, token):
    out = mask(text)
    assert token in out


def test_mask_keeps_account_ids_and_non_luhn():
    assert mask("account HR00100003") == "account HR00100003"
    assert "[CARD]" not in mask("ref 4111 1111 1111 1112")


def test_mask_obj_email_key_and_nested():
    out = mask_obj({"ACCT-EMAIL": "x", "nested": [{"note": "ssn 123-45-6789"}], "n": 5})
    assert out == {"ACCT-EMAIL": "[EMAIL]", "nested": [{"note": "ssn [SSN]"}], "n": 5}


def test_idempotency_store():
    s = IdempotencyStore()
    calls = []
    r1 = s.run("k", {"a": 1}, lambda: calls.append(1) or {"ok": True})
    r2 = s.run("k", {"a": 1}, lambda: calls.append(1) or {"ok": True})
    assert calls == [1] and not r1["replayed"] and r2["replayed"] and s.prevented == 1


@pytest.mark.parametrize("key", ["", "x" * 65])
def test_idempotency_key_required(key):
    with pytest.raises(ValueError):
        IdempotencyStore().run(key, {}, dict)
