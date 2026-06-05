#!/usr/bin/env bash
# API ablation: PER on a given backbone model, restricted to the 32 curated
# paper question types (12 retrieval + 10 reasoning + 10 multi-step) x 3 nets.
# Usage: run_ablation_api.sh <model> <out-subdir>
set -u
cd "$(dirname "$0")"
MODEL="$1"; SUBDIR="$2"

RETRIEVAL=(both_junctions num_lanes junction_coord vehicle_depart_time \
  vehicle_depart_edge vehicle_route vehicles_with_same_origin vehicle_travel_time \
  vehicle_arrival_time vehicle_speed_at_time tls_phase_count tls_longest_green_phase)
REASONING=(shortest_path_full bottleneck_edge avg_route_length_in_window \
  route_edit_distance_pair route_overlap_count vehicle_highest_timeloss \
  avg_trip_duration vehicle_max_speed edge_peak_vehicle_count tls_lowest_green_ratio)
MULTISTEP=(worst_congestion_od gap_violations peak_offpeak_degradation \
  lane_utilisation incomplete_od junction_inflow_cv edge_lane_entropy \
  tls_vehicle_delay tls_approach_queue tls_phase_demand_imbalance)
TYPES=("${RETRIEVAL[@]}" "${REASONING[@]}" "${MULTISTEP[@]}")

for t in "${TYPES[@]}"; do
  echo ">>> [$MODEL] $t"
  python3 run_experiment.py --condition plan_execute_revise --model "$MODEL" \
    --out-subdir "$SUBDIR" --type "$t"
done
echo "API_ABLATION_DONE $MODEL"
