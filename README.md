# PTD: Prefill-Transfer-Decode Profiler Tool

Copyright (c) 2026 BAAI. All rights reserved.

Grafana dashboards for SGLang/vLLM P/D throughput, queues, latency and transfer
metrics. Requires Docker Compose. Run commands from the repository root.

## Live View: Existing Prometheus

Forward the server's Prometheus port to local `127.0.0.1:9090`, then start Grafana:

```bash
docker compose up -d grafana-external
```

Open <http://localhost:3000> and keep the tunnel running. Override
`PROMETHEUS_URL` if needed (default: `http://host.docker.internal:9090`).
Stop with `docker compose stop grafana-external`.

The SGLang live dashboard includes Mooncake/Starbridge engine, batch and request
KV metrics. Enable `--enable-metrics --enable-metrics-for-all-schedulers` on the
servers. Engine/batch panels require the corresponding SGLang instrumentation;
missing metrics appear as no data. Batch bandwidth is per-call throughput;
request KV speed uses all chunks' payload but only the last chunk's transfer time.

## Offline Replay

Provide both prefill and decode captures; separate multiple files with commas:

```bash
PREFILL=log/my-run/prefill.prom.log \
DECODE=log/my-run/decode-1.prom.log,log/my-run/decode-2.prom.log \
DASH=ptd-sglang docker compose up -d
```

Or replay an existing OpenMetrics file:

```bash
OPENMETRICS=log/my-run/openmetrics.txt DASH=ptd-sglang docker compose up -d
```

Grafana: <http://localhost:3000>. Prometheus: <http://localhost:9090>.
Use `GF_PORT` / `PROM_PORT` to avoid port conflicts. Unchanged inputs reuse the
TSDB cache. Stop with `docker compose down`.

Captures must contain `/metrics` output with timestamp headers:

```text
# ==== 1787818207 2026-08-27T16:10:07+08:00 ====
```

## Dashboard Selection

| `DASH` | Dashboard |
|---|---|
| `ptd-sglang` (default) | SGLang P/D |
| `ptd-vllm` | vLLM P/D |
| `sglang` | Native SGLang live stack (Linux) |
| `vllm` | Native vLLM live stack (Linux) |

See [examples](examples/) for live scraping and
[the converter](src/prom2openmetrics.py) for capture-to-OpenMetrics conversion.
