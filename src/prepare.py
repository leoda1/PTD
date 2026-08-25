#!/usr/bin/env python3
"""Prepare everything Prometheus and Grafana need, then exit.

Offline: convert the prefill/decode snapshot logs to OpenMetrics and pin the dashboard
time range to the data. Building the TSDB from that file is a separate compose step,
since promtool ships in the Prometheus image and this one only needs Python.
Online (TARGETS): write a scrape config. Nothing to convert.

docker-compose.yml runs this first; it writes into build/. All paths are relative to
the repo root, which is mounted at /ptd in the container.
"""

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from prom2openmetrics import bounds, convert
from render_dashboard import render

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"

DASHBOARDS = {
    "ptd-vllm":   "dashboard/ptd/vllm-ptd.json",
    "ptd-sglang": "dashboard/ptd/sglang-ptd.json",
}


def main() -> None:
    dash = os.environ.get("DASH", "ptd-vllm")
    if dash not in DASHBOARDS:
        sys.exit(f"unknown DASH={dash!r}, pick one of: {' | '.join(DASHBOARDS)}")

    gf = BUILD / "grafana"
    shutil.rmtree(gf, ignore_errors=True)
    for sub in ("dashboards", "provisioning/dashboards", "provisioning/datasources"):
        (gf / sub).mkdir(parents=True)

    targets = [t.strip() for t in os.environ.get("TARGETS", "").split(",") if t.strip()]
    time_range = None

    if targets:
        (BUILD / "prometheus.yml").write_text(
            "global:\n"
            "  scrape_interval: 5s\n"
            "scrape_configs:\n"
            "  - job_name: ptd\n"
            "    static_configs:\n"
            "      - targets:\n"
            + "".join(f"          - '{t}'\n" for t in targets)
        )
        print(f"scraping: {', '.join(targets)}")
    else:
        om = BUILD / "om.txt"
        om.parent.mkdir(parents=True, exist_ok=True)
        if ready := os.environ.get("OPENMETRICS"):
            src = ROOT / ready
            if not src.is_file():
                sys.exit(f"no such file: {src}")
            shutil.copyfile(src, om)
            time_range = bounds(src)
            print(f"using {ready}")
        else:
            prefill = ROOT / os.environ.get("PREFILL", "log/prefill.prom.log")
            decode = ROOT / os.environ.get("DECODE", "log/decode.prom.log")
            for f in (prefill, decode):
                if not f.is_file():
                    sys.exit(f"no such file: {f}\n"
                             "Replay needs both a prefill and a decode log, or set "
                             "OPENMETRICS to an already-converted file.")
            time_range = convert([(prefill, "prefill"), (decode, "decode")], om)
        shutil.rmtree(BUILD / "tsdb", ignore_errors=True)

    uid = render(
        template=ROOT / DASHBOARDS[dash],
        output=gf / "dashboards" / f"{dash}.json",
        datasource_uid="ptd",
        time_range=time_range,
        # Replayed spans are short, so $__interval can fall below the scrape
        # interval and leave rate() with fewer than two points per window.
        min_interval=None if targets else "30s",
        kv_bytes=int(os.environ.get("KV_BYTES", 167_772_160)),
    )

    # Online runs on the host network, offline on the compose network.
    url = "http://127.0.0.1:9090" if targets else "http://prometheus:9090"
    (gf / "provisioning/datasources/prom.yaml").write_text(
        "apiVersion: 1\n"
        "datasources:\n"
        "  - name: Prometheus\n"
        "    type: prometheus\n"
        "    uid: ptd\n"
        f"    url: {url}\n"
        "    isDefault: true\n"
    )
    (gf / "provisioning/dashboards/dash.yaml").write_text(
        "apiVersion: 1\n"
        "providers:\n"
        "  - name: ptd\n"
        "    type: file\n"
        "    options:\n"
        "      path: /var/lib/grafana/dashboards\n"
    )
    print()
    print(f"  Grafana     http://localhost:{os.environ.get('GF_PORT', '3000')}")
    print(f"  Prometheus  http://localhost:{os.environ.get('PROM_PORT', '9090')}")


if __name__ == "__main__":
    main()
