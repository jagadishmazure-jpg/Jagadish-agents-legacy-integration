# Interview points

- **"How would your agent read mainframe data?"** Through existing interfaces first (API facade,
  MQ, batch), with the copybook as the single schema. Screens only when nothing else exists.
- **COMP-3 in one sentence:** two digits per byte, sign in the last half-byte; never run it through
  a text code-page conversion. Shown with 10,000/10,000 round trips including EBCDIC.
- **Fragile host:** token bucket plus circuit breaker. In the outage drill only 5 of 40 questions
  reached the host and every answer was a safe "try later", not a guess.
- **Duplicate writes:** client-supplied idempotency keys stored with the request body; 159 of 159
  duplicates blocked, including 10 concurrent retries.
- **Screen scraping without fear:** anchors on screen id and labels. A naive script was silently
  wrong 20/20 after a layout shift; the guarded one stopped 20/20. Relocation by label recovers a
  shift but deliberately not a rename.
- **Human in the loop:** writes need a matching, single-use approval naming the approver and ticket,
  and the host profile must have authority too (defence in depth).
- **MQ semantics:** correlation ids, reply-to queues, expiry, retries that reuse the correlation id
  so late replies still count, discarding strays.
- **Honesty:** everything IBM-specific is simulated; the repo says so in a built-vs-planned table.
