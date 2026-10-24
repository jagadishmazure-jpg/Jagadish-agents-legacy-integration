# Guardrails and security controls

| Risk | Control | Where | Proof |
| --- | --- | --- | --- |
| Malformed input crashes or corrupts a COBOL program | Tool JSON schema, then copybook length/type/format checks before any call | `tools.validate_args`, `gateway.check_key`, `copybook.validate` | `test_bad_account_ids_rejected_before_cobol` asserts zero program calls |
| Agent floods a fragile host | Token bucket per gateway | `guards.TokenBucket` | Burst of 30 against 10: 20 rejected, only 10 reached COBOL |
| Host is down; agent keeps hammering or guesses | Circuit breaker, then a fixed safe answer | `guards.CircuitBreaker`, `agent.SAFE_DOWN` | 40 questions in outage: 5 calls reached the host, 0 wrong answers |
| Retried write applied twice | Idempotency key per write; key reuse with a different payload refused | `guards.IdempotencyStore` | 210 attempts, 51 applied, 159 prevented, incl. 10 concurrent |
| Unapproved change | Writes need a named approver; screen writes need a matching single-use `Approval` | `gateway.update_status`, `screen_agent` | 0 writes without approval |
| Screen layout changed, wrong field read | Anchor checks on screen id and labels; writes refused on drift | `screen_agent.check_anchors` | 20/20 drift detected, 0 wrong values |
| SQL used to change data | Read-only profile, read-only file mode, SQLite authorizer, single SELECT only | `sql.Db2iConnection` | 8 write/escape statements refused |
| PII in logs and errors | Masking of emails, Luhn-valid cards, SSNs and phones in audit, trace and tool output; email fields masked by name; errors never echo values | `guards.mask`, `mask_obj` | 0 of 4 planted values found |
| Audit tampering | SHA-256 hash chain over audit lines | `AuditLog.verify_chain` | `test_audit_chain_detects_tamper` |
| Unsupported copybook syntax misread silently | Parser refuses OCCURS, REDEFINES, level-88, COMP on text | `copybook.parse_copybook` | 6 refusal tests |
| Facade reachable from elsewhere | Binds 127.0.0.1; client refuses other hosts | `facade.py` | `test_facade_client_refuses_remote_hosts` |

Repository controls: CI with ruff, pytest, demo, deterministic benchmark check, docs drift check,
hashed brand blocklist and gitleaks over full history; CodeQL; Dependabot; secret scanning with push
protection; `main` rulesets blocking force-push and deletion and requiring CI on pull requests.
