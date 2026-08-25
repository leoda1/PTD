# Offline replay

## 1. Capture

One loop per instance, on the machine running the servers. Both need
`--enable-metrics`, otherwise `/metrics` returns 404.

```bash
while true; do
  echo "# ==== $(date +%s) $(date -Is) ===="
  curl -s --max-time 1 http://127.0.0.1:8000/metrics; echo
  sleep 2
done >> prefill.prom.log &

while true; do
  echo "# ==== $(date +%s) $(date -Is) ===="
  curl -s --max-time 1 http://127.0.0.1:8001/metrics; echo
  sleep 2
done >> decode.prom.log &
```

Run the workload, then kill both loops.

## 2. Replay

```bash
cp prefill.prom.log decode.prom.log log/
cd dashboard/ptd
PREFILL="$(realpath ../../log/prefill.prom.log)" DECODE="$(realpath ../../log/decode.prom.log)" DASH=ptd-sglang docker compose up -d
docker compose logs prepare
```

That last line prints the dashboard URL. Open it — the time range is already set to
the captured window.

The conversion lands in `build/om.txt`, so a later replay can skip it:

```bash
OPENMETRICS="$(realpath ../../build/om.txt)" DASH=ptd-sglang docker compose up -d
```

Or convert the two logs yourself, with nothing but Python 3:

```bash
python3 src/prom2openmetrics.py log/prefill.prom.log log/decode.prom.log log/om.txt
```

## Troubleshooting

`docker compose logs prepare` shows what it read. Panels empty — check the capture has
samples and no 404s:

```bash
grep -c '^sglang:' log/prefill.prom.log
grep -c 'Not Found' log/prefill.prom.log
```

FlagCX panels empty but the rest work — those need the KV transfer metrics from
`sglang-plugin-fl` (`sglang_fl/disaggregation/stats.py`):

```bash
grep -c flagcx log/prefill.prom.log
```
