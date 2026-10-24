# ADR 0002: The copybook is the schema

**Status:** accepted

**Context.** Field lengths and types exist in the copybooks the COBOL compiles against. A second,
hand-written schema would drift.

**Decision.** Parse the same `.cpy` files at runtime for encoding, decoding and input validation;
refuse unsupported syntax instead of approximating it.

**Consequences.** Python and COBOL cannot disagree on a layout. Parser coverage is limited and grows
only with tests.
