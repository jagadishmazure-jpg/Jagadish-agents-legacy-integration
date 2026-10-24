# How each pattern works

## 1. COBOL programs and the copybook codec
`ACCTINQ` takes an account id on the command line, scans `ACCOUNTS.DAT` sequentially and writes the
96-byte match to `OUTFILE` (return code 0 found, 4 not found, 8 file error). The Python side never
parses the bytes by hand: `copybook.load("ACCTREC.cpy")` builds a layout with offsets, and
`decode()` turns the record into a dict, unpacking the COMP-3 balance into an exact decimal string.
`encode()` is the inverse and validates first: wrong length, too many digits, too many decimals,
negative into unsigned, non-ASCII text, unknown or missing keys all raise `FieldError`, and the
message names the field but never the value.

Measured: 10,000 random records survive dict, byte and EBCDIC round trips with zero differences,
and all 200 records read back through the compiled COBOL program equal their source.

## 2. API facade
`Facade` wraps the gateway in a stdlib HTTP server bound to 127.0.0.1. `GET /accounts/{id}` calls
`ACCTINQ` and returns masked JSON. Errors map to HTTP the way a client expects: 400 for a bad id,
404 not found, 429 with `Retry-After` when throttled, 503 with `Retry-After: 30` when the COBOL side
is down or the breaker is open. A real deployment would put this behind z/OS Connect or a similar
gateway; the contract the agent sees would be the same.

## 3. Batch file drop
The agent writes `batch/inbox/<id>.REQ`, one 18-byte line per account (encoded with `BATREQ.cpy`).
`ACCTBAT` loads the master file into a table, answers every line and writes `batch/outbox/<id>.RES`
(33 bytes per line, `BATRES.cpy`) with a return code per request: `00`, `NF` not found, `CL` closed.
The agent parses results with the same codec. One job answered 100 accounts in about 3 ms here,
under 0.03 ms per account, far cheaper per record than any online path.

## 4. MQ request/reply
`MQClient.request()` puts a message on `LEGACY.POLICY.REQ` with a fresh correlation id, a private
reply queue and an expiry. The `Responder` (the mainframe side) calls `POLINQ` and replies with the
same correlation id. The client:
- waits up to `timeout`, then retries with exponential backoff, reusing the correlation id so a late
  reply to the first attempt still counts;
- discards replies with someone else's correlation id (counted as `stray`);
- raises `MQTimeout` after the last retry, which the agent turns into a safe answer.

With 30% of requests dropped by the region, 50 of 50 requests were still answered correctly, using
76 attempts in total.

## 5. Green screen (5250-style)
`GreenScreen` renders 24 x 80 screens: sign-on, main menu, account inquiry (`ACI010`) and account
detail (`ACI020`). Only input fields accept typing; typing anywhere else raises `ProtectedField`.
`ScreenTool` drives it like an emulator script: type the user, press Enter, pick option 1, type the
account, press Enter. Before trusting any value it checks **anchors**: the screen id in row 1 and
the label text at the expected row and column. If any anchor is off, it raises `LayoutDrift` and
returns nothing.

Layout v2 inserts a banner, moving every field two rows down and three columns right. A naive
positional reader returned wrong data on 20 of 20 reads, silently. The guarded tool detected drift
on 20 of 20 and returned no wrong values. With `relocate=True` it finds each label on the screen,
reads relative to it and flags the result as `_relocated`; that recovered 20 of 20. Layout v3 renames
one label: the data is in the same place, but the tool cannot prove it, so it stops (20 of 20
detected, 0 relocated). That is the intended conservative behaviour.

Writes: the tool is read-only unless created with `read_only=False`; even then, an update without a
matching `Approval` (approver, account, status, ticket) only returns `pending_approval`. The host
also checks authority: the read-only profile `AGENTRO` gets `CPF2189 Not authorized` on F10. A write
on a drifted screen is refused before any key is pressed.

## 6. DB2-for-i style SQL
`build_library()` loads the master file into `BANKLIB.ACCTMST` with IBM i style short names. The
agent connects as `AGENTRO`; any other profile is refused. The database is opened with SQLite's
read-only URI mode and an authorizer that permits only reads, so `UPDATE`, `DELETE`, `DROP`,
`ATTACH`, `PRAGMA`, stacked statements and `WITH ... DELETE` are all refused (tested). System naming
`BANKLIB/ACCTMST` and `FETCH FIRST n ROWS ONLY` are translated, and rows are capped at 500.

## 7. Change data capture
Each applied write appends a journal entry (sequence, file, key, before and after images). A
`CdcReader` follows the journal from a checkpoint file, emits masked events in order, and on
restart resumes after the last sequence it saved, so nothing is delivered twice. Replayed
idempotent writes create no journal entry and therefore no event. Median lag from write to agent
was well under a millisecond in-process.

## The agent
`ScriptedModel.plan()` maps a question to a tool and arguments: a policy id goes to MQ, several
account ids to batch, "freeze/close/reactivate" to the approval-gated screen update, "how many /
list / report" to SQL, "what changed" to CDC, a single account to the REST facade. `LegacyAgent`
calls the tool and phrases the answer. Any `LegacyUnavailable`, `CircuitOpen`, `MQTimeout`,
`RateLimited`, `LayoutDrift` or `NavigationError` becomes a fixed safe answer that says nothing was
changed. It never makes up a number.
