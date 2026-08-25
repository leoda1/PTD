#!/usr/bin/env python3
"""Convert snapshot logs captured by metrics.sh into an OpenMetrics file promtool can
bulk-load.

Usage:
    python3 prom2openmetrics.py prefill.prom.log=prefill decode.prom.log=decode -o om.txt

Each argument is <file>=<instance>; the instance is injected as a label so prefill and
decode samples stay distinguishable.
"""
import re
import sys
import argparse

# Snapshot separator line: # ==== 1787122159 2026-08-19T06:49:19+00:00 ====
HDR = re.compile(r"^#\s*====\s*(\d+)\s")

# A valid Prometheus sample line: name{labels} value  /  name value
SAMPLE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)"
    r"(?P<labels>\{.*\})?"
    r"[ \t]+(?P<value>[-+]?(?:[0-9.]+(?:[eE][-+]?[0-9]+)?|Inf|NaN))[ \t]*$"
)


def inject(labels: str | None, instance: str) -> str:
    """Inject instance=... into the label set."""
    add = f'instance="{instance}"'
    if not labels or labels == "{}":
        return "{" + add + "}"
    return labels[:-1] + "," + add + "}"


def parse_file(path: str, instance: str, out: list) -> tuple[int, int, int]:
    ts = None
    n_sample = n_snap = n_junk = 0
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n").rstrip("\r")
            m = HDR.match(line)
            if m:
                ts = int(m.group(1))
                n_snap += 1
                continue
            if not line or line.startswith("#"):
                continue          # drop HELP/TYPE lines
            if ts is None:
                continue
            m = SAMPLE.match(line)
            if not m:
                n_junk += 1       # squid HTML, curl error pages, etc.
                continue
            out.append((
                ts,
                m.group("name") + inject(m.group("labels"), instance)
                + " " + m.group("value") + " " + str(ts),
            ))
            n_sample += 1
    return n_snap, n_sample, n_junk


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="<file>=<instance>")
    ap.add_argument("-o", "--output", default="om.txt")
    args = ap.parse_args()

    rows: list = []
    for spec in args.inputs:
        if "=" not in spec:
            sys.exit(f"expected <file>=<instance>, got: {spec}")
        path, instance = spec.rsplit("=", 1)
        snap, sample, junk = parse_file(path, instance, rows)
        print(f"{path:24s} instance={instance:8s} "
              f"snapshots={snap:6d} samples={sample:8d} junk_dropped={junk}")

    # promtool requires non-decreasing timestamps; interleaved files must be re-sorted
    rows.sort(key=lambda r: r[0])

    with open(args.output, "w") as fh:
        for _, line in rows:
            fh.write(line + "\n")
        fh.write("# EOF\n")

    if rows:
        print(f"\n-> {args.output}  {len(rows)} samples  "
              f"span {rows[0][0]} ~ {rows[-1][0]} "
              f"({(rows[-1][0] - rows[0][0]) / 60:.1f} min)")
    else:
        print("\nno samples parsed - check whether the logs are all proxy error pages")


if __name__ == "__main__":
    main()
