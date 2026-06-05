#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"
export TRACK_USAGE=1
MODEL="gpt-5.4"
SUBDIR="gpt-5.4"
NETS=(random grid_8x8 times_square)
MULTISTEP=(worst_congestion_od gap_violations peak_offpeak_degradation \
  lane_utilisation incomplete_od junction_inflow_cv edge_lane_entropy \
  tls_vehicle_delay tls_approach_queue tls_phase_demand_imbalance)
for n in "${NETS[@]}"; do
  for t in "${MULTISTEP[@]}"; do
    echo ">>> [$MODEL] $n $t"
    python3 run_experiment.py --condition plan_execute_revise --model "$MODEL" \
      --network "$n" --out-subdir "$SUBDIR" --type "$t"
  done
done
echo "GPT54_MULTISTEP_DONE"
