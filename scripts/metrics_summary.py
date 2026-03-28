#!/usr/bin/env python3
"""
Quick summary tool for Jarvis metrics.jsonl.

Reads ~/.jarvis_audit/metrics.jsonl and prints simple aggregates
for each metric name: count, min, max, p50, p90.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path


def load_metrics(path: Path) -> dict[str, list[float]]:
    values: dict[str, list[float]] = defaultdict(list)
    if not path.exists():
        return values
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            name = payload.get("name")
            value = payload.get("value")
            if not isinstance(name, str):
                continue
            try:
                v = float(value)
            except Exception:
                continue
            values[name].append(v)
    return values


def percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = max(0, min(len(sorted_vals) - 1, int(len(sorted_vals) * pct) - 1))
    return sorted_vals[k]


def main() -> None:
    metrics_path = Path.home() / ".jarvis_audit" / "metrics.jsonl"
    metrics = load_metrics(metrics_path)
    if not metrics:
        print(f"No metrics found at {metrics_path}")
        return

    print(f"Metrics summary from {metrics_path}:\n")
    for name in sorted(metrics.keys()):
        vals = sorted(metrics[name])
        count = len(vals)
        min_v = vals[0]
        max_v = vals[-1]
        p50 = statistics.median(vals)
        p90 = percentile(vals, 0.9)
        print(f"{name}: count={count} min={min_v:.1f} p50={p50:.1f} p90={p90:.1f} max={max_v:.1f}")


if __name__ == "__main__":
    main()

