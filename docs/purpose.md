# Purpose

Banks, insurers, airlines and governments run their books on systems built decades ago: COBOL
programs on IBM mainframes and RPG or COBOL applications on IBM i (still widely called AS/400). Those
systems are reliable and heavily audited, which is exactly why nobody wants an AI agent poking at
them carelessly. Yet the facts a customer asks about ("what is my balance", "is my policy active")
live there and nowhere else.

This repo answers one practical question: **how should an agent talk to a system that was never
designed for it, without breaking it, leaking data from it, or acting on stale or misread data?**

It is for:
- **Forward-deployed and AI engineers** who land at a customer with a mainframe and a deadline.
- **Integration architects** choosing between an API facade, files, queues, screens and SQL.
- **Reviewers and recruiters** who want to see the trade-offs worked through with running code
  and measured numbers instead of slides.

What you get is seven integration patterns behind one guarded gateway and one tool layer, an
agent that picks between them, and a benchmark that measures speed, correctness and failure
behaviour. Everything is local and free; real IBM products are named only as the things the
simulations stand in for.
