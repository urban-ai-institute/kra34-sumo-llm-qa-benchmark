#!/usr/bin/env python3
"""Run only the paper-relevant experiments: tool_continuation (all networks)
and plan_execute_revise (times_square only), for reasoning + multi-step types."""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from run_experiment import (
    QUESTIONS_DIR, RESULTS_DIR, files_used_for_csv,
    run_type, result_path, already_done,
)
from utils import DEFAULT_MODEL

REASONING_TYPES = [
    "shortest_path_full", "node_removal_connectivity", "bottleneck_edge",
    "avg_route_length_in_window", "route_jaccard_pair", "route_edit_distance_pair",
    "route_overlap_count", "vehicle_highest_timeloss", "avg_trip_duration",
    "vehicle_max_speed", "edge_peak_vehicle_count", "tls_total_cycle_time",
]

MULTISTEP_TYPES = [
    "vehicle_route_distance_meters", "worst_congestion_od", "gap_violations",
    "peak_offpeak_degradation", "lane_utilisation", "incomplete_od",
    "junction_blocked", "junction_inflow_cv", "edge_lane_entropy",
    "tls_vehicle_delay", "tls_approach_queue", "tls_phase_demand_imbalance",
]

PAPER_TYPES = REASONING_TYPES + MULTISTEP_TYPES
NETWORKS = ["random", "grid_8x8", "times_square"]

PLAN = []
for net in NETWORKS:
    for t in PAPER_TYPES:
        PLAN.append(("tool_continuation", net, t))
for t in PAPER_TYPES:
    PLAN.append(("plan_execute_revise", "times_square", t))


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    model = DEFAULT_MODEL
    force = "--force" in sys.argv

    total = len(PLAN)
    done = 0
    skipped = 0
    errors = 0
    t0 = time.time()

    print(f"Plan: {total} (condition, network, type) units")
    print(f"Model: {model}")

    for i, (cond, net, type_) in enumerate(PLAN, 1):
        qpath = QUESTIONS_DIR / f"{net}_{type_}.csv"
        if not qpath.exists():
            print(f"  [{i}/{total}] {cond} {net} {type_:<40} SKIP (no questions)")
            skipped += 1
            continue

        out = result_path(cond, net, type_)
        if already_done(out) and not force:
            print(f"  [{i}/{total}] {cond} {net} {type_:<40} SKIP (already done)")
            skipped += 1
            continue

        files_used = files_used_for_csv(net, type_)
        n_done, n_err, elapsed = run_type(cond, net, type_, files_used, model)
        done += n_done
        errors += n_err
        err_str = f", {n_err} ERRORS" if n_err else ""
        print(f"  [{i}/{total}] {cond} {net} {type_:<40} {n_done}/5 in {elapsed:5.1f}s{err_str}")

    elapsed_total = time.time() - t0
    print(f"\n=== Done in {elapsed_total/60:.1f} min ===")
    print(f"  Done:    {done}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors:  {errors}")


if __name__ == "__main__":
    main()
