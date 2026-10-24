# Limitations and known failures

- **Everything legacy is simulated or substituted.** GnuCOBOL on Linux is real COBOL but not z/OS:
  no CICS, no VSAM, no JCL. The 5250 screens are a simulator, not the 5250 data stream. MQ is an
  in-process broker. DB2 for i is SQLite with the same naming conventions.
- **Latency numbers are local.** Starting a COBOL process on a laptop costs about 2 ms; a real
  region call adds network and queueing. Compare patterns with each other, not with production.
- **Sequential scan.** The COBOL programs scan the file; a real master file would be indexed (VSAM
  KSDS or a keyed physical file).
- **Copybook coverage.** OCCURS, REDEFINES, level-88, SIGN SEPARATE and COMP-1/COMP-2 are not
  supported; the parser refuses them rather than misreading. Only code page 037 is tested.
- **Screen relocation is narrow.** It survives a shift but not a renamed label (v3), by design.
  The cost is a false stop: on v3 the data was actually fine (the naive reader was right 20/20), but
  the tool stops because it cannot prove that. This is kept visible in the benchmark.
- **The model is scripted.** Routing is keyword rules evaluated on 22 self-written questions; that
  is a regression check, not a measure of how a real LLM would choose.
- **Single process.** Rate limits, the breaker and idempotency keys live in memory or in-memory
  SQLite; a multi-instance deployment would need them in a shared store.
- **CDC covers writes made through the gateway.** A real journal also sees changes made by other
  programs; here those would be missed.
- **Demo credentials** (`demo-ro`, `demo-rw`) are placeholders for a local simulator.
