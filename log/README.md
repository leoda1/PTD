# log/

- `*.prom.log` — raw metrics snapshots captured in production, input to
  `src/prom2openmetrics.py`
- `om-*.txt` — converted OpenMetrics, input that `examples/run.sh` loads into the TSDB

When `run.sh` is called without a file argument it picks the newest `om-*.txt` here by
mtime.

These files are large (`om-0824.txt` is ~16M) and are one-off data, so they are
gitignored; only this README is tracked.
