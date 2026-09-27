# Evidence

`docs/evidence/v1.12-dev/` contains the retained machine-readable evidence
packets from the v1.12 development line.

The current production claim boundary is defined by the Stage-10C integrated
production adjudication. Timing values in those packets are telemetry unless a
test explicitly declared a threshold before execution.

Important non-claims include:

- no distributed/multi-host locking guarantee;
- no authenticated tamper-resistance claim;
- no universal engine/studio benchmark claim;
- no latency SLO for the private synchronous shadow persistence path.
