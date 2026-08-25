#!/bin/bash
# PTD offline replay: start Prometheus + Grafana and load the chosen dashboard.
#
#   bash examples/run.sh                       # ptd dashboard + newest log/om-*.txt
#   bash examples/run.sh vllm                  # vLLM upstream performance dashboard
#   bash examples/run.sh sglang om-0825.txt    # SGLang dashboard + explicit log
#
# Optional env: PROM_PORT=9090 GF_PORT=3000 KV_BYTES=167772160
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="$ROOT/build"
TSDB="$BUILD/tsdb"
# Plugins live in brew's shared dir: installed once, global, untouched by clean.sh
PLUGINS="${GF_PLUGINS:-$(brew --prefix)/var/lib/grafana/plugins}"
PROM_PORT="${PROM_PORT:-9090}"
GF_PORT="${GF_PORT:-3000}"

case "${1:-ptd}" in
  ptd)     TPL="$ROOT/dashboard/ptd/vllm-pd.json" ;;
  vllm)    TPL="$ROOT/dashboard/vllm/performance_statistics.json" ;;
  query)   TPL="$ROOT/dashboard/vllm/query_statistics.json" ;;
  sglang)  TPL="$ROOT/dashboard/sglang/sglang-dashboard.json" ;;
  *) echo "unknown dashboard '$1', pick one of: ptd | vllm | query | sglang" >&2; exit 1 ;;
esac
NAME="${1:-ptd}"

OM="${2:-$(find "$ROOT/log" -maxdepth 1 -name 'om-*.txt' -exec stat -f '%m %N' {} + 2>/dev/null |
           sort -rn | head -1 | cut -d' ' -f2-)}"
[[ -n "$OM" && "$OM" != /* ]] && OM="$ROOT/log/$OM"
[ -n "$OM" ] || { echo "no om-*.txt under log/; generate one with src/prom2openmetrics.py" >&2; exit 1; }

for p in "$PROM_PORT" "$GF_PORT"; do
  lsof -tiTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1 &&
    { echo ":$p is busy, stop the old process (or set PROM_PORT/GF_PORT)" >&2; exit 1; }
done

# --- TSDB: build blocks from the om file if there are none ---
if ! find "$TSDB" -mindepth 2 -maxdepth 2 -name meta.json -print -quit 2>/dev/null | grep -q .; then
  echo "building TSDB from $(basename "$OM")..."
  rm -rf "$TSDB"; mkdir -p "$BUILD"
  promtool tsdb create-blocks-from openmetrics "$OM" "$TSDB" >/dev/null
fi

prometheus --config.file="$ROOT/dashboard/ptd/prom-offline.yml" \
  --storage.tsdb.path="$TSDB" --storage.tsdb.retention.time=10y \
  --web.listen-address=":$PROM_PORT" >"$BUILD/prometheus.log" 2>&1 &
PROM_PID=$!

# --- render dashboard + write provisioning ---
GF="$BUILD/grafana-$NAME"
mkdir -p "$GF"/{data,logs,dashboards,provisioning/{dashboards,datasources,plugins,alerting}}

echo "rendering dashboard:"
RENDER="$(python3 "$ROOT/src/render_dashboard.py" \
  --template "$TPL" --output "$GF/dashboards/$NAME.json" \
  --openmetrics "$OM" --tsdb "$TSDB" --kv-bytes "${KV_BYTES:-167772160}")" || exit 1
echo "$RENDER" | grep -v '^DASHBOARD_UID='
DASH_UID="$(echo "$RENDER" | sed -n 's/^DASHBOARD_UID=//p')"

cat > "$GF/provisioning/datasources/prom.yaml" <<YAML
apiVersion: 1
datasources:
  - name: Prometheus Offline
    type: prometheus
    uid: promoffline
    url: http://127.0.0.1:$PROM_PORT
    isDefault: true
YAML

cat > "$GF/provisioning/dashboards/dash.yaml" <<YAML
apiVersion: 1
providers:
  - name: ptd
    type: file
    options: { path: $GF/dashboards }
YAML

# --- start Grafana ---
# The Homebrew grafana bottle does not ship the prometheus datasource plugin (official
# releases do), and by default Grafana downloads 18 plugins on startup. preinstall=
# clears that list; the plugin is read from $PLUGINS, installed once by install-plugin.sh.
[ -d "$PLUGINS/prometheus" ] || {
  echo "prometheus plugin missing, run once: bash examples/install-plugin.sh" >&2
  kill $PROM_PID 2>/dev/null; exit 1
}

grafana server --homepath "$(brew --prefix grafana)/share/grafana" \
  cfg:default.paths.data="$GF/data" \
  cfg:default.paths.logs="$GF/logs" \
  cfg:default.paths.plugins="$PLUGINS" \
  cfg:default.paths.provisioning="$GF/provisioning" \
  cfg:default.server.http_port="$GF_PORT" \
  cfg:default.dashboards.default_home_dashboard_path="$GF/dashboards/$NAME.json" \
  cfg:default.dashboards.min_refresh_interval=1s \
  cfg:default.plugins.preinstall= \
  cfg:default.auth.anonymous.enabled=true \
  cfg:default.auth.anonymous.org_role=Admin \
  cfg:default.date_formats.default_timezone=browser \
  cfg:default.analytics.reporting_enabled=false \
  cfg:default.analytics.check_for_updates=false >"$GF/logs/stdout.log" 2>&1 &
GF_PID=$!

trap 'echo; echo "stopping..."; kill $GF_PID $PROM_PID 2>/dev/null; wait 2>/dev/null; echo stopped' INT TERM

URL="http://127.0.0.1:$GF_PORT/d/$DASH_UID"
echo
echo "Prometheus : http://127.0.0.1:$PROM_PORT   (log: build/prometheus.log)"
echo "Grafana    : starting... (log: $GF/logs/stdout.log)"
for _ in $(seq 1 120); do
  curl -fsS --max-time 1 "http://127.0.0.1:$GF_PORT/api/health" >/dev/null 2>&1 && break
  kill -0 $GF_PID 2>/dev/null || { echo "Grafana failed to start, see $GF/logs/stdout.log" >&2; exit 1; }
  sleep 1
done
echo "Dashboard  : $URL"
echo "Ctrl+C to stop"
wait $GF_PID
