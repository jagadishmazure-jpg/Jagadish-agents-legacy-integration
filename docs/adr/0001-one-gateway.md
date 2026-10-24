# ADR 0001: One gateway for every transport

**Status:** accepted

**Context.** Seven transports reach the same fragile programs. Duplicating validation, throttling
and auditing in each would drift.

**Decision.** All program-backed paths (facade, MQ, batch, screen, writes) call `LegacyGateway`,
which owns validation, the token bucket, the circuit breaker, idempotency, the journal and the audit
log.

**Consequences.** New transports inherit the guards. The gateway is a single point to scale; in a
multi-instance setup its state moves to a shared store.
