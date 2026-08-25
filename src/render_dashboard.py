#!/usr/bin/env python3
"""Render a dashboard template into a file Grafana can load directly.

Upstream templates (vllm/sglang) are written for live environments; offline replay
needs three fixes, all applied automatically here:
  1. datasource references point at ${DS_PROMETHEUS} or some foreign uid -> rebind
     everything to the local uid
  2. templates use $__interval / $__rate_interval, which on a few-minute offline span
     resolves below the scrape interval, leaving rate() with fewer than two points
     -> inject a per-panel interval floor
  3. the time range must be pinned to the data's real span, otherwise the dashboard
     opens at "last 6 hours" and shows nothing
"""
import argparse, json, re
from datetime import datetime, timezone
from pathlib import Path

TS = re.compile(r"\s(\d{10,13})\s*$")


def bounds_from_om(path):
    """Scan timestamps in an OpenMetrics file, return (earliest, latest) in ms."""
    vals = [int(m.group(1)) for line in path.open(errors="replace")
            if not line.startswith("#") and (m := TS.search(line))]
    if not vals:
        raise SystemExit(f"no timestamped samples in {path}")
    vals = [v if v >= 10**11 else v * 1000 for v in vals]
    return min(vals), max(vals)


def bounds_from_tsdb(path):
    metas = [json.loads(p.read_text()) for p in path.glob("*/meta.json")]
    return (min(m["minTime"] for m in metas),
            max(m["maxTime"] for m in metas)) if metas else None


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")


def panels(dash):
    """Walk every panel, including ones nested inside collapsed rows."""
    stack = list(dash.get("panels", []))
    while stack:
        p = stack.pop()
        stack += p.get("panels") or []
        yield p


def rebind(node, uid):
    """Repoint datasource references at the local uid (skip the built-in Grafana source)."""
    if isinstance(node, dict):
        ds = node.get("datasource")
        if isinstance(ds, dict) and ds.get("uid") not in (None, "-- Grafana --"):
            ds["uid"] = uid
        elif isinstance(ds, str) and ds != "-- Grafana --":
            node["datasource"] = {"type": "prometheus", "uid": uid}
        for v in node.values():
            rebind(v, uid)
    elif isinstance(node, list):
        for v in node:
            rebind(v, uid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--datasource-uid", default="promoffline")
    ap.add_argument("--min-interval", default="30s")
    ap.add_argument("--kv-bytes", type=int, default=167_772_160)
    ap.add_argument("--openmetrics", type=Path)
    ap.add_argument("--tsdb", type=Path)
    a = ap.parse_args()

    if a.openmetrics and a.openmetrics.exists():
        lo, hi = bounds_from_om(a.openmetrics)
        src = a.openmetrics
    else:
        b = a.tsdb and bounds_from_tsdb(a.tsdb)
        if not b:
            raise SystemExit("no om file and no TSDB block: cannot determine time range")
        lo, hi, src = *b, a.tsdb

    dash = json.loads(a.template.read_text())
    rebind(dash, a.datasource_uid)

    for v in dash.get("templating", {}).get("list", []):
        if v.get("type") == "datasource":
            v["current"] = {"text": "Prometheus Offline", "value": a.datasource_uid}
        # label_values() queries behind template variables need the local source too
        if isinstance(v.get("datasource"), dict):
            v["datasource"]["uid"] = a.datasource_uid
        # KV bytes: only the ptd dashboard declares this variable
        if v.get("name") == "kv_bytes_per_request":
            kv = str(a.kv_bytes)
            v.update(query=kv, current={"selected": True, "text": kv, "value": kv},
                     options=[{"selected": True, "text": kv, "value": kv}])

    for p in panels(dash):
        if p.get("type") != "row":
            p["interval"] = a.min_interval

    dash["time"] = {"from": iso(lo - 15_000), "to": iso(hi + 15_000)}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(dash, ensure_ascii=False, indent=1) + "\n")

    print(f"  template   : {a.template.name}")
    print(f"  time range : {dash['time']['from'][:19]} .. {dash['time']['to'][:19]}  (from {Path(src).name})")
    print(f"DASHBOARD_UID={dash.get('uid', '')}")   # read by run.sh to build the URL; keep last


if __name__ == "__main__":
    main()
