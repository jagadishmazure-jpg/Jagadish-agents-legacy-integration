# Implementation guide for adopters

1. **Inventory the interfaces that already exist.** Programs that can be called, queues, batch jobs,
   replicated tables, screens. Ask the mainframe team which ones they will support for a new
   consumer. Favour those over anything new.
2. **Get the copybooks from source control, not from a document.** Load them with
   `copybook.load()`. If the parser refuses one (OCCURS, REDEFINES), extend it with tests before
   using it. Round-trip a sample of real records (encode(decode(raw)) == raw) and confirm the code
   page with the team.
3. **Put one gateway in front of everything.** Copy the shape of `LegacyGateway`: validate against
   the copybook, rate limit to a budget the host team agrees to, breaker with a cooldown they agree
   to, audit every call with masking.
4. **Wrap each path as a narrow tool.** One purpose, a JSON schema with lengths and patterns from
   the copybook, `additionalProperties: false`. Keep read and write tools separate.
5. **Make writes idempotent and approved.** Idempotency key from the client (ticket id or request
   id), stored with the request body so reuse with a different body is refused. A named human
   approver per change; approvals single-use.
6. **If you must scrape screens,** record anchors (screen id plus label text and position) for every
   screen you touch, check them before every read and before every keystroke on a write, and treat
   drift as a stop and an alert, never as a guess.
7. **Prefer CDC over polling** when the agent needs to react; checkpoint after each batch of events.
8. **Rehearse the outage.** Run the equivalent of `bench.outage()` against your test region:
   the agent must answer safely and must not hammer the host.
9. **Swap the scripted model** for your LLM by replacing `ScriptedModel.plan`; keep the tool layer
   and gateway unchanged and rerun the routing checks plus your own labelled questions.
10. **Measure before go-live** with `legacyagents bench` adapted to your paths, and keep the
    deterministic numbers in CI.
