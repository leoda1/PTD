# log/

Offline replay needs exactly two files here:

```
log/prefill.prom.log
log/decode.prom.log
```

Capture them on the server with one loop per instance:

```bash
while true; do
  echo "# ==== $(date +%s) $(date -Is) ===="
  curl -s --max-time 1 http://127.0.0.1:8000/metrics
  echo
  sleep 2
done >> prefill.prom.log &

while true; do
  echo "# ==== $(date +%s) $(date -Is) ===="
  curl -s --max-time 1 http://127.0.0.1:8001/metrics
  echo
  sleep 2
done >> decode.prom.log &
```

The `# ====` header carries the timestamp — it is what makes replay possible, so keep
it. `--max-time` stops a stalled server from swallowing a whole sample.

Both servers must be started with `--enable-metrics`, otherwise `/metrics` returns 404
and the file fills with `{"detail":"Not Found"}`. Those lines are counted as junk and
dropped during conversion, so a partially bad capture still works.

Start only one loop per port: two loops produce duplicate timestamps. They are
deduplicated during conversion, but you gain nothing and the file doubles in size.

These files are large and one-off, so they are gitignored; only this README is tracked.
