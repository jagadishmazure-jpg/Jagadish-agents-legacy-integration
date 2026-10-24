# Choosing a pattern

Start from the question the agent has to answer, then pick the least invasive path that answers it.

| Need | First choice | Why | Avoid |
| --- | --- | --- | --- |
| One record, interactive, many users | REST facade | Fast, cacheable, standard errors | Screen scraping (slow, brittle) |
| The shop already runs MQ | MQ request/reply | Decoupled, survives restarts, existing ops | Opening new direct connections |
| Hundreds to millions of records | Batch file drop | Cheapest per record, no online load | Looping over the facade |
| Ad hoc reporting, aggregates | Read-only SQL on a replica | Set-based, no program needed | SQL against the production OLTP files |
| React to changes | CDC from the journal | No polling, ordered, resumable | Polling every few seconds |
| Nothing else exists | Guarded screen scraping | Works with only a terminal | Unguarded positional scripts |
| Any write | Program call behind the gateway, idempotent, with human approval | One audited path | Writes over SQL or unapproved screens |

Decision steps:
1. **Is there already an API, queue or batch interface?** Use it. Each added integration is
   something the mainframe team must support.
2. **How fresh must the answer be?** Seconds: facade or MQ. Hours: batch or SQL replica.
3. **How many records?** One: online. Many: batch or SQL.
4. **Is it a write?** Only through the gateway with an idempotency key and a named approver. Never
   through SQL, and on screens only after anchor checks pass.
5. **What happens when it is down?** Every path here fails to a safe answer; if yours cannot, it is
   not ready for an agent.

Speed measured here (local, so the gaps between paths are what matter, not the absolute values):
SQL about 0.2 ms, COBOL call / screen / MQ about 2 ms, facade about 3 ms, and a batch of 100 about
3 ms total. On a real system the online paths add network and region time and screens add one round
trip per screen, so the ranking usually gets steeper, not flatter.
