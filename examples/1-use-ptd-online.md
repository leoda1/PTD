# Online monitoring

Scrape running servers. **Linux only** — this uses `network_mode: host`, which does
not reach the host on Docker Desktop for Mac. On macOS use
[offline replay](0-use-ptd-offline.md).

```bash
cd dashboard/ptd
DASH=ptd-sglang TARGETS=127.0.0.1:8000,127.0.0.1:8001 docker compose --profile online up -d
docker compose logs prepare-online
```

That last line prints the dashboard URL.

One `TARGETS` entry per instance — prefill and decode are separate servers, so P/D
deployments list both. Every server needs `--enable-metrics`, otherwise `/metrics`
returns 404 and Prometheus shows the target as down.

| Variable | Default | Meaning |
|---|---|---|
| `DASH` | `ptd-vllm` | `ptd-vllm` or `ptd-sglang` |
| `TARGETS` | required | comma-separated `host:port` list |
| `PROM_PORT` | `9090` | Prometheus port |
| `GF_PORT` | `3000` | Grafana port |

Check a target by hand first, then confirm at <http://localhost:9090/targets>:

```bash
curl -s http://127.0.0.1:8000/metrics | head -5
```

Stop with `docker compose --profile online down`.

For the upstream dashboards instead, use their own stacks in `dashboard/vllm/` and
`dashboard/sglang/`.
