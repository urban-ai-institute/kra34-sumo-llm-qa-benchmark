#!/usr/bin/env bash
# NetTrafficQA end-to-end pipeline.
#
# Requires:
#   - $SUMO_HOME pointing to a SUMO installation
#   - $ANTHROPIC_API_KEY (or claude_api.txt at the project root used by scripts/utils.py)
#   - Python deps: anthropic, sumolib (bundled with SUMO)
#
# Skip step 1 if data/network/, data/trips/, data/output/ already exist:
# all artifacts are committed to the repository.

set -e

# 1. Build the simulations (one-off; deterministic at seed=42).
#    Produces data/trips/<net>.{trips,rou}.xml and data/output/<net>_{tripinfo,netstate}.xml.
# python run_simulation.py

# 2. Pre-build the JSONL views consumed by the JSON scaffolding condition.
#    Writes data/preprocessed/<net>_<file>.jsonl.
# python scripts/build_jsonl.py

# 3. Generate the 27-type question matrix (3 networks × 27 types × 5 samples = 405 questions).
#    Writes QAdataset/questions/<net>_<type>.csv. Deterministic at seed=42.
python generate_qa.py

# 4. Full matrix (3 conditions × 3 networks × 27 types × 5 samples = 1{,}215 calls).
#    Resumes on existing CSVs in QAdataset/results/.
python run_experiment.py --all

# 5. Evaluate. Reads QAdataset/results/*.csv and writes *_evaluated.csv next to them.
python evaluate.py
