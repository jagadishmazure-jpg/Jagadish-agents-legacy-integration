# Architecture

```mermaid
flowchart TB
  subgraph Agent side
    Q[Question] --> AG[LegacyAgent]
    AG -->|plan: tool + args| SM[ScriptedModel]
    AG --> TL[LegacyTools: list_tools / call_tool]
    TL -->|validate against JSON schema| V{valid?}
  end
  V -->|no| R1[SchemaError, nothing sent]
  V -->|yes| P1[REST facade :127.0.0.1]
  V --> P2[MQClient -> Broker -> Responder]
  V --> P3[batch_lookup: REQ file -> ACCTBAT -> RES file]
  V --> P4[ScreenTool -> GreenScreen 24x80]
  V --> P5[Db2iConnection read-only]
  V --> P6[CdcReader]
  subgraph LegacyGateway
    G1[copybook-length validation] --> G2[token bucket] --> G3[circuit breaker] --> G4[CobolRuntime subprocess + timeout]
    G5[IdempotencyStore] --> G6[Journal] 
    G7[AuditLog: masked, hash-chained]
  end
  P1 & P2 & P3 & P4 --> G1
  G4 --> CB[(ACCTINQ / POLINQ / ACCTBAT / ACCTUPD)]
  CB --> DAT[(ACCOUNTS.DAT, POLICIES.DAT: fixed width, COMP-3)]
  DAT -.build_library.-> P5
  G6 -.-> P6
```

## Components

| Module | Role |
| --- | --- |
| `cobol/*.cbl`, `cobol/copybooks/*.cpy` | The "legacy system": four real COBOL programs and their record layouts |
| `copybook.py` | Parses copybooks; encodes and decodes records (ASCII or EBCDIC, COMP-3, COMP, zoned) |
| `cobol.py` | Compiles with `cobc`, runs a program with a timeout, maps files through environment variables (how GnuCOBOL resolves `ASSIGN TO` names) |
| `gateway.py` | The one door: validation, rate limit, breaker, idempotent writes, journal, audit |
| `facade.py` | Pattern 2, REST over the gateway |
| `mq.py` | Pattern 4, broker, mainframe-side responder, client with correlation ids |
| `screen.py`, `screen_agent.py` | Pattern 5, terminal simulator and guarded scraper |
| `sql.py` | Pattern 6, DB2-for-i conventions on SQLite, read-only |
| `cdc.py` | Pattern 7, journal follower with checkpoints |
| `tools.py` | MCP-style tool catalogue with JSON schemas |
| `agent.py` | Question to tool choice to plain answer, with safe failure |
| `bench.py` | Every number in the README |

## Why everything funnels through one gateway
Each pattern is a different *transport*, but the risks are the same: a fragile host, exact field
formats, money, personal data. Putting validation, throttling, the breaker and the audit trail in
one place means a new pattern inherits them for free and a reviewer has one file to read. The SQL
path is the exception because it reads a copy (see ADR 0003).
