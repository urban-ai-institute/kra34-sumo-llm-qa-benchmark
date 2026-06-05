#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"
export TRACK_USAGE=1
MODEL="claude-haiku-4-5-20251001"
SUBDIR="claude-haiku-4-5"
NETS=(random grid_8x8 times_square)
RETRIEVAL=(both_junctions num_lanes junction_coord vehicle_depart_time \
  vehicle_depart_edge vehicle_route vehicles_with_same_origin vehicle_travel_time \
  vehicle_arrival_time vehicle_speed_at_time tls_phase_count tls_longest_green_phase)
REASONING=(shortest_path_full bottleneck_edge avg_route_length_in_window \
  route_edit_distance_pair route_overlap_count vehicle_highest_timeloss \
  avg_trip_duration vehicle_max_speed edge_peak_vehicle_count tls_lowest_green_ratio)
TYPES=("${RETRIEVAL[@]}" "${REASONING[@]}")
for n in "${NETS[@]}"; do
  for t in "${TYPES[@]}"; do
    echo ">>> [$MODEL] $n $t"
    python3 run_experiment.py --condition plan_execute_revise --model "$MODEL" \
      --network "$n" --out-subdir "$SUBDIR" --type "$t"
  done
done
echo "HAIKU_RETRIEVAL_REASONING_DONE"
