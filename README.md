<div align="center">

# SUMO-SimQA

### SUMO-SimQA: A Benchmark for LLM Cross-File Reasoning over Traffic Simulation Files

[![Paper](https://img.shields.io/badge/Paper-CIKM%202026-b31b1b.svg)](https://doi.org/10.1145/3799682.3839980)
[![DOI](https://img.shields.io/badge/DOI-10.1145%2F3799682.3839980-blue.svg)](https://doi.org/10.1145/3799682.3839980)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

<p align="center">
  <a href="#overview">Overview</a> ·
  <a href="#experiment-setups">Experiment Setups</a> ·
  <a href="#dataset">Dataset</a> ·
  <a href="#results">Results</a> ·
  <a href="#requirements">Requirements</a> ·
  <a href="#running-experiments">Running Experiments</a> ·
  <a href="#citation">Citation</a>
</p>

</div>

---

## Overview

A benchmark for measuring how well LLMs can read and reason over raw
[SUMO](https://eclipse.dev/sumo/) traffic-simulation files. Each question is
answered by an LLM that is given the simulation files through one of several
*setups*, ranging from dumping raw XML into the prompt to a
Plan-Execute-Revise (PER) agent that writes and runs Python over the files.

The repository provides the question dataset, the SUMO scenario files, and the
code to collect model answers (`run_experiment.py`) and score them
(`evaluate.py`).

### Repository layout

```
SUMO-SimQA/
├── run_experiment.py        # Collect LLM answers for (condition, network, type)
├── evaluate.py              # Score answers and aggregate accuracy
├── run_simulation.py        # Regenerate tripinfo/fcd outputs with SUMO
├── requirements.txt
├── scripts/
│   ├── utils.py             # File-path registry + LLM client helper
│   ├── llm_client.py        # Claude (Anthropic) client
│   └── methods/             # Experiment Setup conditions
│       ├── file.py                  # file                 (File)
│       ├── xml_view.py              # xml                  (XML)
│       ├── react.py                 # react                (ReAct)
│       ├── plan_execute.py          # plan_execute         (PE)
│       └── plan_execute_revise.py   # plan_execute_revise  (PER)
├── SUMO_dataset/
│   ├── configuration_files/
│   │   ├── net/             # {net}.net.xml
│   │   ├── rou/             # {net}.rou.xml
│   │   └── add/             # {net}_tls.add.xml
│   └── output_files/
│       ├── tripinfo/        # {net}_tripinfo.xml
│       └── fcd/             # {net}_fcd.xml
└── QA_dataset/
    └── questions/           # {network}_{type}.csv
```

## Requirements

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Set your Anthropic API key in `claude_api.txt` at the repo root, or via the `ANTHROPIC_API_KEY` environment variable.

[SUMO](https://eclipse.dev/sumo/) (1.25.0) is required to
regenerate the simulation outputs; install it and set `SUMO_HOME` to your SUMO installation directory.

## Experiment Setups

`run_experiment.py --condition <name>` selects how the SUMO files are exposed to
the LLM:

| Setup                     | `--condition`         | Description                                      |
| ------------------------- | ----------------------- | ------------------------------------------------ |
| File-Description (File)   | `file`                | File structure description only, no contents.    |
| Full-XML (XML)            | `xml`                 | Raw SUMO XML inserted verbatim into the prompt.  |
| Code execution (ReAct)    | `react`               | LLM executes Python code (no plan, no revision). |
| Plan-Execute (PE)         | `plan_execute`        | LLM plans, then executes as code (no revision).  |
| Plan-Execute-Revise (PER) | `plan_execute_revise` | LLM plans, executes, then revises the plan.      |

## Dataset

SUMO-SimQA contains **480 questions** = 32 question types × 3 networks × 5 samples.
Networks are `grid_8x8`, `random`, and `times_square`.
The 32 types fall into three categories of increasing complexity:

- **Retrieval** (12 types) — single field lookup
- **Reasoning** (10 types) — single file, requires computation
- **Cross-file Reasoning** (10 types) — requires two or more files

Each `QA_dataset/questions/{network}_{type}.csv` holds 5 samples
(`sample_id` 0–4), with the `question` and its `ground_truth` per row.

![Question types](images/question_types.png)

## Regenerating simulation outputs (tripinfo / fcd)

```bash
export SUMO_HOME=/path/to/sumo
python run_simulation.py
```

This runs SUMO on the existing network and route files — every route scenario
(base and `_s0`–`_s4`) per network — and writes the corresponding
`*_tripinfo.xml` to `SUMO_dataset/output_files/tripinfo/` and `*_fcd.xml` to
`SUMO_dataset/output_files/fcd/` (18 files each).

## Running experiments

```bash
# One condition / network / type (5 questions)
python run_experiment.py --condition plan_execute_revise \
    --network times_square --type num_lanes

# A single question type across all networks
python run_experiment.py --condition xml --type both_junctions

# The full matrix
python run_experiment.py --all --condition plan_execute_revise
```

Results are written to `QA_dataset/results/{condition}_{network}_{type}.csv`.
Existing result files are skipped unless you pass `--force`.

## Evaluating

```bash
# Score everything under QA_dataset/results/
python evaluate.py
```

`evaluate.py` writes `*_evaluated.csv` alongside each result file and prints
accuracy per (condition, network, type).

## Results

Accuracy (%) across different LLM strategies and three SUMO networks. Best result per row in bold.

![Main results](images/main_result.png)

## Citation

If you find SUMO-SimQA helpful, please cite our paper:

```bibtex
@inproceedings{10.1145/3799682.3839980,
author = {Chang, Jeeyun and Yun, Taeyoung and Jeong, Minwoo and Park, Jinkyoo and Yoon, Yoonjin},
title = {SUMO-SimQA: A Benchmark for LLM Cross-File Reasoning over Traffic Simulation Files},
year = {2026},
isbn = {9798400725395},
publisher = {Association for Computing Machinery},
address = {New York, NY, USA},
url = {https://doi.org/10.1145/3799682.3839980},
doi = {10.1145/3799682.3839980},
booktitle = {Proceedings of the 35th ACM International Conference on Information and Knowledge Management},
pages = {6989–6994},
numpages = {6},
keywords = {llm benchmark, traffic simulation, sumo},
location = {Rome, Italy},
series = {CIKM '26}
}
```

## License

This project is released under the MIT License. See [LICENSE](LICENSE) for details.
