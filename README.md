# PTD — Offline Metrics Replay for vLLM / SGLang

Replay metrics snapshots captured in production locally with Prometheus + Grafana.
Nothing is scraped: metrics are collected elsewhere as periodic text snapshots,
converted to OpenMetrics, bulk-loaded into a Prometheus TSDB, and viewed in Grafana
with the dashboard's time range pinned to the data's actual span.

## Usage

```bash
# 0. Install the prometheus plugin (once; the Homebrew grafana bottle omits it)
bash examples/install-plugin.sh

# 1. Convert logs to OpenMetrics (first time, or when replacing the data)
python3 src/prom2openmetrics.py prefill.prom.log=prefill decode.prom.log=decode \
        -o log/om-0825.txt

# 2. Start everything, then open the Dashboard URL the script prints
bash examples/run.sh                     # PTD's own P/D dashboard (default)
bash examples/run.sh vllm                # vLLM upstream performance dashboard
bash examples/run.sh query               # vLLM upstream query dashboard
bash examples/run.sh sglang              # SGLang dashboard
bash examples/run.sh ptd om-0824.txt     # pick a specific log file

# 3. Wipe generated state before replaying a different batch
bash examples/clean.sh
```

Ctrl+C stops Prometheus and Grafana together.

Optional env vars: `PROM_PORT` (default 9090), `GF_PORT` (default 3000),
`KV_BYTES` (default 167772160 — KV cache bytes per request, ptd dashboard only).

## Layout

```
dashboard/          dashboard sources, kept permanently
  ptd/              own P/D dashboard + Prometheus config
  vllm/             vLLM upstream originals, do not hand-edit
  sglang/           SGLang upstream originals, do not hand-edit
src/
  prom2openmetrics.py   snapshot logs -> OpenMetrics
  render_dashboard.py   template -> loadable dashboard
examples/
  install-plugin.sh install the prometheus plugin (one-time)
  run.sh            start Prometheus + Grafana
  clean.sh          delete build/
log/                raw logs and om-*.txt (*.txt is gitignored)
docs/               observability research notes
build/              * every generated artifact, safe to delete
```

## Data flow

```
*.prom.log  --prom2openmetrics.py-->  log/om-*.txt
            --promtool create-blocks-->  build/tsdb/
            --prometheus :9090-->  Grafana :3000
                                     ^ dashboard rendered by render_dashboard.py
```

## Adapting upstream dashboards

`dashboard/vllm/` and `dashboard/sglang/` are upstream originals written for live
environments; offline replay needs three fixes. **Do not hand-edit the JSON** (every
upstream bump would undo it) — `src/render_dashboard.py` handles all of it:

| Problem | Symptom | Fix |
|---|---|---|
| datasource is `${DS_PROMETHEUS}` or some foreign uid | all panels blank, log says `Could not find plugin definition for data source` | rebind recursively to the local `promoffline` |
| uses `$__interval` / `$__rate_interval`, which resolves to ~1s on a few-minute span, below the 2s scrape interval | `rate()` has fewer than two points in its window, timeseries blank | inject a per-panel `interval` floor (default 30s) |
| time range is `now-6h` | opens on an empty screen | pin to the data's real span ±15s |

## Dependencies

```bash
brew install prometheus grafana
bash examples/install-plugin.sh
```

The Homebrew grafana bottle **does not ship the prometheus datasource plugin**
(official tarball/deb do). Without it every panel is blank and the log says
`plugin.notRegistered`.

`install-plugin.sh` installs it once into `$(brew --prefix)/var/lib/grafana/plugins`
— the same directory brew's own service uses, so it survives `brew upgrade` and is out
of reach of `clean.sh`.

`run.sh` also clears Grafana's default preinstall list of 18 plugins (pyroscope / loki /
tempo / mysql / elasticsearch / ...) so nothing is downloaded on startup. Startup takes
about 8 seconds.

## Notes

- Delete `build/` only; never `dashboard/` (that is the source).
- `build/tsdb/` is not rebuilt while it holds blocks. Run `bash examples/clean.sh`
  before switching data.
- Scrape interval is 2s (`om-0824.txt` measured: 272s span, 134730 samples, 998 series).
  The ptd dashboard hardcodes `[30s]` / `[5s]` rate windows — check the scrape interval
  of new data before swapping it in.
