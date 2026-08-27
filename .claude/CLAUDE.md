# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## What this is

Prometheus + Grafana with the PTD P/D dashboards, plus pass-through to the native
upstream vLLM/SGLang dashboards. One `docker compose` command from the repo root,
nothing but Docker required — no `cd`, no wrapper script.

Root `compose.yaml` just does `include: [dashboard/routes/${DASH:-ptd-sglang}.yaml]`.
Each file in `dashboard/routes/` is a one-line include shim picking a real compose
file:

| `DASH` | includes | what it is |
|---|---|---|
| `ptd-sglang` (default) | `dashboard/ptd/docker-compose.yml` | own SGLang P/D dashboard, offline replay or `--profile online` scrape |
| `ptd-vllm` | `dashboard/ptd/docker-compose.yml` | own vLLM P/D dashboard, same modes |
| `sglang` | `dashboard/sglang/docker-compose.yaml` | native upstream SGLang dashboard, live scrape only |
| `vllm` | `dashboard/vllm/docker-compose.yaml` | native upstream vLLM dashboard, live scrape only |

- **Offline** (`ptd-vllm`/`ptd-sglang` only, default) — capture logs are converted to
  OpenMetrics, bulk-loaded into a TSDB, and the dashboard time range is pinned to the
  data. Nothing is scraped, so it works anywhere including macOS.
- **Online** (`--profile online`, or the native `sglang`/`vllm` routes) — scrape live
  servers via `network_mode: host`, so Linux only.

`dashboard/vllm/` and `dashboard/sglang/` hold the upstream dashboards and their own
compose stacks, kept pristine; PTD's own dashboards live in `dashboard/ptd/`.

## Commands

```bash
PREFILL=log/prefill.prom.log DECODE=log/decode.prom.log DASH=ptd-vllm docker compose up -d
OPENMETRICS=log/om-0824.txt DASH=ptd-vllm docker compose up -d
TARGETS=127.0.0.1:8000,127.0.0.1:8001 DASH=ptd-sglang docker compose --profile online up -d
DASH=vllm docker compose up -d               # native upstream dashboard, live only

docker compose logs prepare        # prints the dashboard URL
docker compose down

# just the conversion
python3 src/prom2openmetrics.py log/prefill.prom.log log/decode.prom.log -o log/om.txt
```

All of this runs from the repo root — `compose.yaml` there is the entrypoint.
`PREFILL`/`DECODE` accept comma-separated lists for multi-instance captures (e.g. a
1P2D run needs two decode logs) and paths relative to the repo root.

Always suggest `up -d`: in the foreground the containers' own logs bury everything.

There is no build/lint/test tooling — this is operational config, not a library.

## Architecture

`src/prepare.py` is the entrypoint compose runs first, on the stock
`python:3.12-slim`. It exits when `build/` is ready; each later service waits on
`condition: service_completed_successfully`. It prints the full dashboard URL as its
last line, which is the only place the user learns it — `docker compose logs prepare`.

Offline it converts (`prom2openmetrics.py`) and renders the dashboard
(`render_dashboard.py`) to `build/grafana/dashboards/current.json`; a separate `tsdb`
service then runs `promtool` from the Prometheus image, so no image has to be built.
Online (`TARGETS`) it writes a scrape config and skips the conversion. `DASH` picks
the template when replaying — `ptd-vllm` or `ptd-sglang` — or is auto-detected from
the OpenMetrics content (`sglang:`/`vllm:` prefixes) if unset. `OPENMETRICS` replays
an already-converted file.

**TSDB is cached, not always rebuilt.** `prepare.py` hashes the input paths
(size + mtime) into `build/replay-input.json`; an unchanged replay just reuses the
existing TSDB. On a real change it writes a `build/rebuild-tsdb` marker, calls
Prometheus's `/-/quit` to stop it, clears `build/tsdb`, reconverts, and Prometheus's
entrypoint loop (a shell `while true` around the `prometheus` binary) restarts once
the marker is gone.

**`HOST_PTD_ROOT`** lets `dashboard/ptd/docker-compose.yml` work whether it's
included from the root `compose.yaml` (cwd = repo root) or run directly from
`dashboard/ptd/` (cwd = that directory) — `prepare.py` maps a host-absolute
`PREFILL`/`DECODE`/`OPENMETRICS` path back onto the `/ptd` mount by trying both.

Images use `:latest`, matching the upstream compose files, so users who already ran
those do not pull a second copy.

**Directory roles:**
- `dashboard/ptd/` — own dashboards (`vllm-ptd.json`, `sglang-ptd.json`) plus
  `offline.yml`. Source of truth.
- `dashboard/routes/` — one-line `include:` shims; this is what `DASH` selects.
- `dashboard/vllm/`, `dashboard/sglang/` — upstream files, kept pristine. Never
  hand-edit; all adaptation to PTD's own dashboards happens in `render_dashboard.py`.
- `src/` — the only code: `prepare.py`, `prom2openmetrics.py`, `render_dashboard.py`.
- `log/` — capture logs, one subdirectory per run; filenames are free-form as long
  as `PREFILL`/`DECODE`/`OPENMETRICS` point at them.

## Things that will bite you

- **Both PREFILL and DECODE are required offline** (unless `OPENMETRICS` is set).
  P/D analysis with half the picture is not useful, so `prepare.py` fails fast
  rather than degrading.
- **Compose interpolates the whole file before selecting profiles**, so a `${VAR:?}`
  in an online-only service breaks offline runs too. Validate in `prepare.py`.
- **`network_mode: host` is Linux-only.** It silently fails to reach the host on
  Docker Desktop for Mac — hence offline being the macOS path, and the native
  `sglang`/`vllm` routes not working on Mac at all.
- **Duplicate timestamps** appear when two capture loops hit one port. promtool
  rejects them outright, so the converter keys samples by (series, timestamp) and
  keeps the last value, as Prometheus would.
- **Offline retention is 10y.** The default 15 days drops the replayed blocks the
  moment Prometheus starts.
- **`--enable-metrics` is not optional** on the servers captured or scraped. Without it
  `/metrics` is 404 and captures fill with `{"detail":"Not Found"}`.
- **A stale TSDB cache** looks like "nothing changed" after swapping in a new log with
  the same size/mtime by coincidence — delete `build/replay-input.json` (or `build/`)
  to force a rebuild.
- The FlagCX KV transfer panels need metrics from `sglang-plugin-fl`
  (`sglang_fl/disaggregation/stats.py`); engine panels work without them.

## Conventions

- Everything is written in English: code, comments, docs, output strings.
- Keep it short. Prefer one path over a fallback chain — if an input is wrong, fail
  with a clear message instead of guessing.
