"""Adapt the SGLang dashboard to Mooncake/Starbridge snapshot metrics."""

PREFIX = "sglang:transfer_engine_"


def adapt_transfer_panels(dashboard):
    dashboard["title"] = "SGLang P/D - Mooncake / Starbridge"
    dashboard["tags"] = ["sglang", "pd", "mooncake", "starbridge"]
    dashboard["refresh"] = "5s"
    dashboard["panels"] = []
    def rate(name, selector=""):
        return f"rate({PREFIX}{name}_total{selector}[1m])"

    def panel(title, unit, queries, description=""):
        dashboard["panels"].append({
            "id": 100 + len(dashboard["panels"]), "type": "timeseries",
            "title": title, "description": description,
            "datasource": {"type": "prometheus", "uid": "promoffline"},
            "fieldConfig": {"defaults": {"unit": unit, "min": 0}, "overrides": []},
            "options": {"legend": {"displayMode": "table", "placement": "bottom",
                                   "calcs": ["lastNotNull", "max", "mean"]}},
            "targets": [{"refId": chr(65+i), "expr": expr, "legendFormat": legend}
                        for i, (expr, legend) in enumerate(queries)],
        })

    def service_rate(metric, role="decode"):
        return f'rate(sglang:{metric}{{engine_type="{role}"}}[1m])'

    def average(metric):
        count = f"sum by (instance) ({service_rate(metric + '_count')})"
        return (f"(sum by (instance) ({service_rate(metric + '_sum')}) / {count}) "
                f"and ({count} > 0)")

    def scheduler_count(role):
        return ("count by (instance) "
                f'(sglang:num_running_reqs{{engine_type="{role}"}})')

    def running(role):
        # Queue values are replicated across TP/PP schedulers; retain max per DP replica.
        return ("sum by (instance) (max by (instance, dp_rank) "
                f'(sglang:num_running_reqs{{engine_type="{role}"}}))')

    def stat(title, unit, expr):
        panel(title, unit, [(expr, "{{instance}}")])
        p = dashboard["panels"][-1]
        p["type"] = "stat"
        p["options"] = {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "graphMode": "area", "colorMode": "value", "textMode": "auto",
            "orientation": "auto",
        }

    qps = f"sum by (instance) ({service_rate('num_requests_total')})"
    stat("Completion QPS (Decode)", "reqps", qps)
    stat("Scheduler Processes (Decode)", "none", scheduler_count("decode"))
    stat("Running Requests (Decode)", "none", running("decode"))
    stat("Avg First Token Time", "s", average("time_to_first_token_seconds"))
    stat("Avg Inter-token Time", "s", average("inter_token_latency_seconds"))

    panel("Aborted Requests per Second", "reqps", [
        (f"sum by (instance) ({service_rate('num_aborted_requests_total')})", "{{instance}}")
    ], "SGLang aborted requests, not gateway HTTP error rate or retry rate.")
    panel("Completion QPS by Instance", "reqps", [(qps, "{{instance}}")],
          "Decode completions per second, not gateway arrivals. A 1-minute rate window is used.")
    for role in ("prefill", "decode"):
        panel(f"Scheduler Processes ({role.title()})", "none",
              [(scheduler_count(role), "{{instance}} scheduler processes")],
              "Counts active SGLang scheduler metric series for this instance; TP/PP ranks are process labels, not extra replicas.")
        panel(f"Running Requests ({role.title()})", "none", [(running(role), "{{instance}}")],
              "Scheduler running requests, not process or connection count. Max across TP/PP workers per instance and DP replica, then sum DP replicas.")

    for title, metric in (("First Token Time", "time_to_first_token_seconds"),
                          ("Inter-token Time", "inter_token_latency_seconds"),
                          ("End-to-End Request Time", "e2e_request_latency_seconds")):
        panel(title + " Quantiles", "s", [
            (f"histogram_quantile({q}, sum by (le, instance) ({service_rate(metric + '_bucket')}))",
             "{{instance}} " + label)
            for q, label in ((0.5, "p50"), (0.75, "p75"), (0.99, "p99"))
        ], "Decode-side histogram quantiles over 1 minute; end-to-end time includes the whole request, not only generation.")
        panel("Avg " + title + " by Instance", "s", [(average(metric), "{{instance}}")])

    panel("Avg Prompt Length", "none", [(average("prompt_tokens_histogram"), "{{instance}} tokens")])
    panel("Token Throughput", "none", [
        (f"sum by (instance) ({service_rate(metric, role)})", "{{instance}} " + role + " tokens/s")
        for metric, role in (("prompt_tokens_total", "prefill"), ("generation_tokens_total", "decode"))
    ])
    for role in ("prefill", "decode"):
        metrics = ["num_queue_reqs"] + (
            ["num_prefill_bootstrap_queue_reqs", "num_prefill_inflight_queue_reqs"]
            if role == "prefill" else ["num_decode_prealloc_queue_reqs", "num_decode_transfer_queue_reqs"])
        names = {
            "num_queue_reqs": "Waiting Queue",
            "num_prefill_bootstrap_queue_reqs": "Bootstrap Queue",
            "num_prefill_inflight_queue_reqs": "Inflight Queue",
            "num_decode_prealloc_queue_reqs": "Pre-Allocation Queue",
            "num_decode_transfer_queue_reqs": "Transfer Queue",
        }
        for metric in metrics:
            panel(f"[{role.title()}] {names[metric]}", "none", [
                (f'sum by (instance) (max by (instance, dp_rank) (sglang:{metric}{{engine_type="{role}"}}))',
                 "{{instance}}")
            ])

    for title, stage in (("Bootstrap", "prefill_bootstrap"),
                         ("Waiting", None), ("Forward", "prefill_forward"),
                         ("Transfer KV Cache", "prefill_transfer_kv_cache")):
        metric = "per_stage_req_latency_seconds" if stage else "queue_time_seconds"
        selector = 'engine_type="prefill"' + (f',stage="{stage}"' if stage else "")

        def stage_rate(suffix):
            return f'rate(sglang:{metric}_{suffix}{{{selector}}}[1m])'

        count = f"sum by (instance) ({stage_rate('count')})"
        queries = [(f"(sum by (instance) ({stage_rate('sum')}) / {count}) and ({count} > 0)",
                    "{{instance}} avg")]
        queries.extend((f"histogram_quantile({q}, sum by (le, instance) ({stage_rate('bucket')}))",
                        "{{instance}} " + label)
                       for q, label in ((0.99, "p99"), (0.75, "p75"), (0.5, "p50")))
        panel(f"[Prefill] {title} Latency", "s", queries,
              "Request-stage histogram, not engine batch latency. Quantiles and mean use a 1-minute window.")

    for role in ("prefill", "decode"):
        panel(f"[{role.title()}] Aborted Requests (1m)", "none", [
            (f'sum by (instance) (increase(sglang:num_aborted_requests_total{{engine_type="{role}"}}[1m]))',
             "{{instance}}")
        ], "Estimated count over a rolling minute. No abort-reason breakdown is exported by this metric.")
    panel("[Prefill] Bootstrap Failures (1m)", "none", [
        ('sum by (instance) (increase(sglang:num_bootstrap_failed_reqs_total{engine_type="prefill"}[1m]))',
         "{{instance}}")
    ], "Bootstrap failures only; not all failed requests. Do not add to aborted requests without deduplication.")
    panel("KV Cache Usage", "percentunit", [
        ("max by (instance, engine_type) (sglang:kv_used_tokens) / max by (instance, engine_type) (sglang:max_total_num_tokens)",
         "{{instance}} {{engine_type}}")
    ])
    panel("Prefix Cache Hit Rate", "percentunit", [
        ("max by (instance, engine_type) (sglang:cache_hit_rate)", "{{instance}} {{engine_type}}")
    ])

    rank = "{{backend}} {{instance}} {{engine_type}} tp={{tp_rank}} pp={{pp_rank}}"
    panel("Engine Completed Throughput", "Bps", [
        (f"sum by (backend, engine_type) ({rate('completed_bytes')})", "{{backend}} {{engine_type}} total"),
        (rate("completed_bytes"), rank),
    ], "Completed engine bytes per wall-clock second; includes all engine transfers, not exclusively request KV payload. Rates use a 1-minute window.")
    panel("Engine Completed Bytes", "bytes", [(PREFIX + "completed_bytes_total", rank)])
    batches = rate("completed_batches")
    panel("Mean Successful Batch Latency", "ms", [
        (f"(1000 * {rate('duration_seconds')} / {batches}) and ({batches} > 0)", rank)
    ], "Submission-to-completion average per successful engine batch, not request latency or a percentile. No value when no successful batch completes.")
    panel("Batch Completion and Failure Rates", "ops", [
        (rate(name), rank + " " + name)
        for name in ("completed_batches", "failed_batches", "timed_out_batches")
    ])
    panel("Mean Successful Batch Size", "bytes", [
        (f"({rate('completed_bytes')} / {batches}) and ({batches} > 0)", rank)
    ])
    panel("Registered and Allocated Memory", "bytes", [
        (PREFIX + name, rank + " {{location}} " + name)
        for name in ("registered_bytes", "allocated_bytes")
    ], "Registered and allocated memory can overlap; do not add these values.")
    panel("Starbridge Route Bytes per Second", "Bps", [
        (rate(name, '{engine_type="prefill"}'), rank + " " + name)
        for name in ("route_bridge_bytes", "route_direct_bytes")
    ])
    panel("Starbridge Relay Stage Bytes per Second", "Bps", [
        (rate(name), rank + " " + name)
        for name in ("relay_ready_bytes", "relay_submitted_bytes", "relay_completed_bytes")
    ], "Stages describe the same relay traffic at different points; do not add them.")
    panel("Starbridge Relay Inflight Bytes", "bytes", [
        (PREFIX + "relay_inflight_bytes", rank + " gpu={{gpu}}")
    ])
    panel("Starbridge Relay Occupancy and Limit", "none", [
        (PREFIX + name, rank + " gpu={{gpu}} " + name)
        for name in ("relay_inflight", "relay_limit", "relay_high_watermark")
    ])
    slots = PREFIX + "lane_slots"
    panel("Starbridge Lane Slots", "none", [
        (f"max by (backend, instance, engine_type, tp_rank, pp_rank, gpu, lane, state) ({slots})",
         rank + " gpu={{gpu}} lane={{lane}} {{state}}")
    ], "All lanes and states are shown continuously; no historical idle-lane filtering.")
    panel("Starbridge Relay Skip and Limit Rates", "ops", [
        (rate(name), rank + " " + name)
        for name in ("skip_not_write", "skip_not_cuda", "skip_no_target",
                     "skip_no_device", "skip_same_rail", "skip_no_relay", "relay_limit_blocked")
    ], "Skip counters explain routing choices; same-rail direct transfer is not a failure.")
    panel("NIC Inflight Bytes", "bytes", [
        (PREFIX + "nic_inflight_bytes", rank + " {{nic}}")
    ])
    panel("NIC Reported Bandwidth", "Bps", [
        (PREFIX + "nic_bandwidth_bytes_per_second", rank + " {{nic}}")
    ], "Engine-provided gauge, not a counter: do not apply rate().")

    variables = dashboard.setdefault("templating", {}).setdefault("list", [])
    variables.append({
        "name": "batch_path", "label": "Batch Path", "type": "query",
        "datasource": {"type": "prometheus", "uid": "promoffline"},
        "query": 'label_values(sglang:transfer_batch_calls_total{engine_type="prefill"}, path)',
        "refresh": 1, "multi": True, "includeAll": True, "allValue": ".*",
        "current": {"text": "All", "value": "$__all"},
        "options": [], "sort": 1,
    })
    batch_prefix = "sglang:transfer_batch_"
    selector = '{engine_type="prefill",path=~"${batch_path:regex}"}'
    group = "instance, tp_rank, pp_rank, cp_rank, dp_rank, path"
    legend = "{{instance}} tp={{tp_rank}} pp={{pp_rank}} cp={{cp_rank}} dp={{dp_rank}} {{path}}"

    def batch_rate(metric, suffix):
        return f"rate({batch_prefix}{metric}_{suffix}{selector}[1m])"

    metrics = (
        ("Slices", "slices", "none", "Address-list entries, not RDMA WRs or slots. Includes failed calls."),
        ("Bytes", "bytes", "bytes", "Requested payload per returned call. Includes failed calls."),
        ("Call Latency", "duration_seconds", "s", "Successful calls only. Includes engine queueing and completion wait; excludes address preparation and metrics."),
        ("Effective Bandwidth", "bandwidth_bytes_per_second", "Bps", "Successful batch bytes / call duration. Mean of individual batch bandwidths, not NIC or multi-thread aggregate throughput."),
    )
    for title, metric, unit, meaning in metrics:
        count = f"sum by ({group}) ({batch_rate(metric, 'count')})"
        mean = f"(sum by ({group}) ({batch_rate(metric, 'sum')}) / {count}) and ({count} > 0)"
        queries = [(mean, legend + " avg")]
        queries.extend(
            (f"histogram_quantile({quantile}, sum by (le, {group}) ({batch_rate(metric, 'bucket')}))",
             legend + " " + label)
            for quantile, label in ((0.5, "p50"), (0.95, "p95"), (0.99, "p99"))
        )
        panel("[Batch] " + title, unit, queries,
              meaning + " Uses a 1-minute window; quantiles are bucket estimates. Requires SGLang transfer_batch metrics.")

    kv_metrics = (
        ("Transfer Latency", "latency_ms", "ms",
         "SGLang request transfer duration. Mooncake/Starbridge use completion minus last transfer-queue entry, not engine-only time or the whole chunked transfer."),
        ("Bootstrap Latency", "bootstrap_ms", "ms",
         "Bootstrap queue entry to bootstrap done; excludes the following allocation wait. Recorded after successful request transfer."),
        ("Allocation Wait", "alloc_ms", "ms",
         "Bootstrap done to waiting-queue entry. Recorded after successful request transfer."),
        ("Transfer Size", "total_mb", "suffix:MiB",
         "Sender-accounted KV and state payload across request chunks, divided by 1024^2; not engine wire bytes."),
        ("Transfer Speed", "speed_gb_s", "suffix:GiB/s",
         "Sender-accounted request payload / request transfer duration, divided by 1024^3. For Mooncake/Starbridge, chunked requests use only the last chunk's time."),
    )
    for title, metric, unit, meaning in kv_metrics:
        def kv_rate(suffix):
            return f'rate(sglang:kv_transfer_{metric}_{suffix}{{engine_type="prefill"}}[1m])'

        count = f"sum by (instance) ({kv_rate('count')})"
        queries = [(f"(sum by (instance) ({kv_rate('sum')}) / {count}) and ({count} > 0)",
                    "{{instance}} avg")]
        queries.extend(
            (f"histogram_quantile({quantile}, sum by (le, instance) ({kv_rate('bucket')}))",
             "{{instance}} " + label)
            for quantile, label in ((0.5, "p50"), (0.75, "p75"), (0.99, "p99"))
        )
        panel("[Prefill KV] " + title, unit, queries,
              meaning + " Uses kv_transfer histograms over 1 minute; quantiles are bucket estimates.")

    for index, p in enumerate(dashboard["panels"]):
        p["gridPos"] = dict(x=(index % 4) * 6, y=(index // 4) * 8, w=6, h=8)
