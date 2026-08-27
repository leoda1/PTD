# Offline replay

Capture `/metrics` separately for each instance:

```bash
while true; do
  echo "# ==== $(date +%s) $(date -Is) ===="
  curl -s --max-time 1 http://127.0.0.1:8000/metrics
  sleep 2
done >> prefill.prom.log
```

Put the logs under PTD's `log/` directory and run from the repository root:

```bash
PREFILL='log/run/prefill.prom.log' \
DECODE='log/run/decode-1.prom.log,log/run/decode-2.prom.log' \
DASH=ptd-sglang \
docker compose up -d
```

Check the conversion result:

```bash
docker compose logs prepare
```
