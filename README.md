# PTD

Run all commands from the PTD repository root. Grafana: <http://localhost:3000>. Prometheus: <http://localhost:9090>.

## Offline replay

`PREFILL` and `DECODE` accept paths relative to the PTD root or absolute paths inside PTD. Separate multiple instances with commas:

```bash
PREFILL='log/my-run/prefill.prom.log' \
DECODE='log/my-run/decode-1.prom.log,log/my-run/decode-2.prom.log' \
DASH=ptd-sglang \
docker compose up -d
```

Using absolute paths:

```bash
PREFILL="$PWD/log/prefill.prom.log" \
DECODE="$PWD/log/decode.prom.log" \
DASH=ptd-sglang \
docker compose up -d
```

### Convert logs to OpenMetrics

Convert one Prefill and one Decode log to a `.txt` file:

```bash
python3 src/prom2openmetrics.py \
  'log/my-run/prefill.prom.log' \
  'log/my-run/decode.prom.log' \
  -o 'log/my-run/openmetrics.txt'
```

For multiple P/D instances, assign a unique instance name to every log:

```bash
python3 src/prom2openmetrics.py \
  'prefill-1=log/my-run/prefill-1.prom.log' \
  'prefill-2=log/my-run/prefill-2.prom.log' \
  'decode-1=log/my-run/decode-1.prom.log' \
  'decode-2=log/my-run/decode-2.prom.log' \
  -o 'log/my-run/openmetrics.txt'
```

Replay the converted file:

```bash
OPENMETRICS="$PWD/log/my-run/openmetrics.txt" \
DASH=ptd-sglang \
docker compose up -d
```

After one successful replay, `docker compose up -d` reuses the latest data.

## DASH

| Value | Dashboard |
|---|---|
| `ptd-sglang` | SGLang P/D offline/online dashboard |
| `ptd-vllm` | vLLM P/D offline/online dashboard |
| `sglang` | Native SGLang live dashboard |
| `vllm` | Native vLLM live dashboard |

```bash
DASH=sglang docker compose up -d
DASH=vllm docker compose up -d
```

See [examples](examples/) for metric capture and online monitoring.
