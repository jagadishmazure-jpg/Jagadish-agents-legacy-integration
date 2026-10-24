# Mainframe primer for everyone else

You do not need mainframe experience to read this repo. These are the ideas it relies on.

## COBOL
A programming language from 1959 made for business records. Programs are split into
*divisions*: one names the program, one names the files, one declares the data and one holds the
logic. COBOL reads and writes files one fixed-size record at a time, and it is very good at exact
decimal arithmetic, which is why money still runs through it. Here, four small COBOL programs are
compiled with **GnuCOBOL**, a free compiler, and run as ordinary Linux executables.

## Fixed-width records
There are no commas or JSON. A record is a run of bytes and each field sits at a known offset with
a known length. Byte 0-9 is the account id, byte 10-39 the name, and so on. If you are off by one
byte, every field after it is garbage, which is why the layout must come from one trusted source.

## Copybooks
That trusted source is the *copybook*: a fragment of COBOL that declares a record layout and is
`COPY`-ed into every program that uses the file. `PIC X(10)` means ten characters. `PIC 9(8)` means
eight digits stored as text. `PIC S9(9)V99` means a signed number with nine digits before an
*implied* decimal point and two after; the point itself is not stored. This repo parses the same
copybooks the COBOL programs compile against, so the Python view and the COBOL view cannot drift.

## EBCDIC
Mainframes and IBM i encode text in EBCDIC, not ASCII. The letter "A" is byte 0xC1 instead of 0x41.
A file copied off a mainframe as raw bytes must be converted field by field: text fields are
translated, while binary and packed fields must be left alone, because translating them would
corrupt the numbers. The codec here uses code page 037 (US/Canada) and touches only text and zoned
fields.

## Packed decimal (COMP-3)
A space-saving number format: two decimal digits per byte, with the last half-byte holding the sign
(C positive, D negative, F unsigned). The balance -123.45 in `S9(9)V99 COMP-3` is six bytes:
`00 00 00 12 34 5D`. It is exact (no floating point), which is why money uses it. Readers that treat
these bytes as text produce nonsense, so the codec unpacks them explicitly and rejects invalid
nibbles instead of guessing.

## Zoned decimal and overpunch
`PIC S9(5)` without COMP-3 stores one digit per character, and the sign is folded into the last
character: `012L` means -123. The codec handles that too.

## AS/400 (IBM i)
IBM's midrange platform, renamed several times (AS/400, iSeries, System i, IBM i). It bundles the
operating system and a DB2 database. Applications are commonly written in RPG or COBOL. Data lives
in *libraries* (like schemas) holding *files* (tables), with names capped at ten characters, so you
see names like `BANKLIB/ACCTMST`. Users are *user profiles* with their own authorities.

## 5250 green screens
The IBM i terminal protocol. The host sends a whole 24 x 80 character screen with some positions
marked as input fields. The user types into those fields only, then presses an *attention key*
(Enter, F3, F10...), and the whole screen goes back to the host. Many business processes exist only
as a sequence of such screens, so screen automation ("screen scraping") is sometimes the only
programmatic path. It is fragile: if someone adds a line to a screen, every position below it moves.

## DB2 for i
The database built into IBM i. It can be queried with SQL using either `LIB.FILE` or the system
style `LIB/FILE`, and it uses `FETCH FIRST n ROWS ONLY` instead of `LIMIT`. Here it is simulated
with SQLite while keeping those conventions.

## Journals and change data capture
IBM i can *journal* a file: every change is written as an ordered entry with before and after
images. Replication tools read journals to stream changes elsewhere. That is change data capture
(CDC), and it is how an agent can learn about a change without polling the system.

## MQ
IBM MQ is message middleware. A caller puts a request on a queue with a *reply-to* queue and a
*correlation id*; a mainframe program picks it up, does the work, and puts the answer on the reply
queue with the same correlation id. The caller matches by that id. It decouples the two sides, so
the agent never blocks the mainframe and the mainframe never needs to know about the agent.

## Batch
Much mainframe work still happens in scheduled batch jobs that read an input file and write an
output file. For bulk questions it is often the cheapest and safest path: one job, thousands of
answers, no online load.
