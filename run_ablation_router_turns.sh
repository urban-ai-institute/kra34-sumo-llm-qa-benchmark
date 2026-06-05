#!/usr/bin/env bash
# Router-turn ablation for PER (Claude default model).
# 3r baseline = existing default plan_execute_revise results.
# Runs 1r, 5r, 10r over the 10 multi-step reasoning types × 3 networks.
set -u
cd "$(dirname "$0")"

TYPES=(worst_congestion_od gap_violations peak_offpeak_degradation lane_utilisation \
       incomplete_od junction_inflow_cv edge_lane_entropy tls_vehicle_delay \
       tls_approach_queue tls_phase_demand_imbalance)
CONDS=(plan_execute_revise_1r plan_execute_revise_5r plan_execute_revise_10r)

for cond in "${CONDS[@]}"; do
  for t in "${TYPES[@]}"; do
    echo ">>> [$cond] $t"
    python3 run_experiment.py --condition "$cond" --type "$t"
  done
done
echo "ROUTER_TURN_ABLATION_DONE"
