# Threat model

Scope: the agent, the tool layer and the gateway in front of legacy programs. Assets: account and
policy records (money, personal data), the integrity of the master files, and the availability of
the legacy host.

## STRIDE
| Threat | Example | Mitigation |
| --- | --- | --- |
| Spoofing | Agent signs on to the screen as a privileged profile | Tool is configured with a named profile; read-only by default; host checks authority (CPF2189) |
| Tampering | Crafted id like `HR00100000;rm` or an oversized field shifts the record | Pattern and length checks before the program is called; programs run without a shell |
| Repudiation | "The agent froze my account and nobody knows who approved it" | Approver and ticket recorded in the hash-chained audit log and journal |
| Information disclosure | Email or card number in a log line or error | Masking on every audit entry, trace and tool output; errors name fields only |
| Denial of service | Agent loop floods the region | Token bucket and circuit breaker; batch for bulk work |
| Elevation of privilege | SQL path used to write | Read-only profile, read-only open, authorizer |

## OWASP LLM Top 10 (relevant items)
| Item | How it applies | Mitigation |
| --- | --- | --- |
| LLM01 Prompt injection | A question asks the agent to "close every account" | Tools take one validated id; writes need a matching human approval for that exact change |
| LLM02 Sensitive information disclosure | Model output repeats PII | Tool results are masked before the model sees them |
| LLM06 Excessive agency | Agent writes when it only needed to read | Read tools and write tools are separate; write tools default to pending |
| LLM09 Misinformation | Agent invents a balance when the host is down | Fixed safe answer; never a number without a successful read |

## Out of scope
Network transport security to a real host (TLS for TN5250, MQ channel auth), mainframe RACF or IBM i
object authority design, and model-side jailbreak testing against a real LLM.
