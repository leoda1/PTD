# PTD — Prometheus + Grafana for vLLM / SGLang

PTD ships two P/D dashboards with FlagCX KV transfer panels, in two modes.

## Offline

Replay snapshots captured earlier. Nothing is scraped, works anywhere including macOS.

```bash
cd dashboard/ptd
PREFILL=log/prefill.prom.log DECODE=log/decode.prom.log DASH=ptd-vllm docker compose up -d   # PTD vLLM dashboard
PREFILL=log/prefill.prom.log DECODE=log/decode.prom.log DASH=ptd-sglang docker compose up -d # PTD SGLang dashboard
OPENMETRICS=log/om-0824.txt DASH=ptd-vllm docker compose up -d                               # already-converted input
```

Prometheus is on <http://localhost:9090> and grafana is on <http://localgihost:3000>

## Online

Scrape running servers. Uses host networking, so **Linux only**.

```bash
cd dashboard/ptd
DASH=ptd-vllm TARGETS=127.0.0.1:8000,127.0.0.1:8001 docker compose --profile online up -d
DASH=ptd-sglang TARGETS=127.0.0.1:8000,127.0.0.1:8001 docker compose --profile online up -d
```

One `TARGETS` entry per instance. Servers need `--enable-metrics`.


Prometheus is on <http://localhost:9090>. Without `-d` the terminal fills with the
containers' own logs, which is why the examples use it.

The upstream dashboards live in `dashboard/vllm/` and `dashboard/sglang/`, each with
its own compose stack.

## Dashboards

| `DASH` | Dashboard |
|---|---|
| `ptd-vllm` | vLLM P/D dashboard, includes FlagCX KV transfer panels |
| `ptd-sglang` | SGLang P/D dashboard, includes FlagCX KV transfer panels |

The FlagCX panels need the metrics from `sglang-plugin-fl`
(`sglang_fl/disaggregation/stats.py`) or the equivalent vLLM connector. Engine-side
panels work without them; the FlagCX ones stay empty.

`KV_BYTES` (default 167772160, i.e. 160 MiB) is the KV cache size per request, used
to convert transferred bytes into an equivalent req/s. PTD dashboards only.

## Layout

```
dashboard/ptd/
  docker-compose.yml    both modes; online behind --profile online
  offline.yml           Prometheus config for replay (nothing is scraped)
  vllm-ptd.json         own vLLM P/D dashboard
  sglang-ptd.json       own SGLang P/D dashboard
dashboard/vllm/     vLLM upstream files, kept pristine
dashboard/sglang/   SGLang upstream files, kept pristine
src/
  prepare.py            convert logs + render dashboard
  prom2openmetrics.py   snapshot logs -> OpenMetrics
  render_dashboard.py   template -> dashboard Grafana can load
log/                the two capture files
build/              everything generated; delete it freely
```
