#!/usr/bin/env python3
"""Convert captured metrics snapshots into an OpenMetrics file promtool can load.

Each snapshot in the log starts with a header line written by the capture loop:

    # ==== 1787122159 2026-08-19T06:49:19+00:00 ====

Everything until the next header is one scrape. Samples get an `instance` label
so prefill and decode stay distinguishable, and are emitted sorted by timestamp
because promtool requires them non-decreasing.
"""

import re
import sys

HEADER = re.compile(r"^#\s*====\s*(\d+)\s")
TAIL_TS = re.compile(r"\s(\d{10})\s*$")
SAMPLE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)"
    r"(?P<labels>\{.*\})?"
    r"[ \t]+(?P<value>[-+]?(?:[0-9.]+(?:[eE][-+]?[0-9]+)?|Inf|NaN))[ \t]*$"
)


def _with_instance(labels: str | None, instance: str) -> str:
    tag = f'instance="{instance}"'
    if not labels or labels == "{}":
        return "{" + tag + "}"
    return labels[:-1] + "," + tag + "}"


def _parse(path, instance: str, rows: dict) -> None:
    ts = None
    samples = snapshots = junk = 0
    with open(path, errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\r\n")
            header = HEADER.match(line)
            if header:
                ts = int(header.group(1))
                snapshots += 1
            elif not line or line.startswith("#") or ts is None:
                continue                      # HELP/TYPE lines and pre-header noise
            elif m := SAMPLE.match(line):
                # Keyed by (series, ts): a stray second capture loop against the
                # same port yields duplicate timestamps, which promtool rejects.
                # Last value wins, same as Prometheus would do.
                series = m.group("name") + _with_instance(m.group("labels"), instance)
                rows[(series, ts)] = m.group("value")
                samples += 1
            else:
                junk += 1                     # 404 pages, proxy errors, curl output
    print(f"  {path.name:24s} instance={instance:8s} "
          f"snapshots={snapshots:5d} samples={samples:8d} junk={junk}")


def bounds(path) -> tuple[int, int]:
    """First and last timestamp of an existing OpenMetrics file, in ms."""
    stamps = [int(m.group(1)) for line in open(path, errors="replace")
              if not line.startswith("#") and (m := TAIL_TS.search(line))]
    if not stamps:
        sys.exit(f"{path} has no timestamped samples")
    return min(stamps) * 1000, max(stamps) * 1000


def convert(inputs, output) -> tuple[int, int]:
    """Write `inputs` [(path, instance), ...] to `output`. Returns (start, end) ms."""
    rows: dict = {}
    for path, instance in inputs:
        _parse(path, instance, rows)
    if not rows:
        sys.exit("no samples parsed - are the logs full of 404s? "
                 "The server needs --enable-metrics.")

    # promtool requires timestamps to be non-decreasing.
    ordered = sorted(rows.items(), key=lambda kv: kv[0][1])

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as fh:
        for (series, ts), value in ordered:
            fh.write(f"{series} {value} {ts}\n")
        fh.write("# EOF\n")

    start, end = ordered[0][0][1], ordered[-1][0][1]
    print(f"  -> {output.name}  {len(ordered)} samples  "
          f"spanning {(end - start) / 60:.1f} min")
    return start * 1000, end * 1000


if __name__ == "__main__":
    from pathlib import Path
    if len(sys.argv) != 4:
        sys.exit("usage: prom2openmetrics.py <prefill.log> <decode.log> <out.txt>")
    prefill, decode, out = (Path(a) for a in sys.argv[1:])
    convert([(prefill, "prefill"), (decode, "decode")], out)
