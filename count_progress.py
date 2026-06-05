#!/usr/bin/env python3
"""Print done-counts for the ablation runs against their true targets.

  gpt=<n>/96 gemini=<n>/96 router=<n>/90

Counts only the curated 32 paper types (API ablation) and the 10 multi-step
types x 3 router-turn conditions (router ablation), ignoring any extra
non-paper type files left over from earlier broad runs.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "QAdataset" / "results"
NETS = ["random", "grid_8x8", "times_square"]

PAPER32 = (
    ["both_junctions", "num_lanes", "junction_coord", "vehicle_depart_time",
     "vehicle_depart_edge", "vehicle_route", "vehicles_with_same_origin",
     "vehicle_travel_time", "vehicle_arrival_time", "vehicle_speed_at_time",
     "tls_phase_count", "tls_longest_green_phase"] +
    ["shortest_path_full", "bottleneck_edge", "avg_route_length_in_window",
     "route_edit_distance_pair", "route_overlap_count", "vehicle_highest_timeloss",
     "avg_trip_duration", "vehicle_max_speed", "edge_peak_vehicle_count",
     "tls_lowest_green_ratio"] +
    ["worst_congestion_od", "gap_violations", "peak_offpeak_degradation",
     "lane_utilisation", "incomplete_od", "junction_inflow_cv",
     "edge_lane_entropy", "tls_vehicle_delay", "tls_approach_queue",
     "tls_phase_demand_imbalance"]
)
MULTISTEP = PAPER32[-10:]
ROUTER_CONDS = ["plan_execute_revise_1r", "plan_execute_revise_5r",
                "plan_execute_revise_10r"]


def count_api(subdir):
    d = RESULTS / subdir
    n = 0
    for net in NETS:
        for t in PAPER32:
            if (d / f"plan_execute_revise_{net}_{t}.csv").exists():
                n += 1
    return n


def count_router():
    n = 0
    for cond in ROUTER_CONDS:
        for net in NETS:
            for t in MULTISTEP:
                if (RESULTS / f"{cond}_{net}_{t}.csv").exists():
                    n += 1
    return n


if __name__ == "__main__":
    g = count_api("gpt-5.4-mini")
    m = count_api("gemini-3.5-flash")
    r = count_router()
    print(f"gpt={g}/96 gemini={m}/96 router={r}/90")
