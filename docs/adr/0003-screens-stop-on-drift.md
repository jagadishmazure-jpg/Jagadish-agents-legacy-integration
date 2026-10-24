# ADR 0003: Screen tools stop on drift; SQL reads a copy

**Status:** accepted

**Context.** Screen positions move when a screen is edited; reading the wrong position returns
plausible but wrong data. Reporting queries over live files can load the host.

**Decision.** The screen tool checks anchors before every read and write and raises `LayoutDrift`
on mismatch. Optional relocation by label is allowed for reads only and is flagged. The SQL path
reads a loaded library copy through a read-only profile.

**Consequences.** Some safe screens are refused (the v3 rename case). SQL answers can be as stale as
the last load, which is acceptable for reporting.
