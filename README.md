# SUMO-SimQA

A benchmark for measuring how well LLMs can read and reason over raw
[SUMO](https://eclipse.dev/sumo/) traffic-simulation files. Each question is
answered by an LLM that is given the simulation files through one of several
*scaffolding* conditions, ranging from dumping raw XML into the prompt to a
Plan-Execute-Revise (PER) agent that writes and runs Python over the files.

This repository contains only the **core experiment and evaluation logic**:
collecting model answers (`run_experiment.py`) and scoring them
(`evaluate.py`). Paper-writing material, ablation runners, and the
data/QA-generation tooling have been removed.

## Repository layout

```
SUMO-SimQA/
├── run_experiment.py        # Collect LLM answers for (condition, network, type)
├── evaluate.py              # Score answers and aggregate accuracy
├── requirements.txt
├── agentsumo/               # Minimal config shim (API-key loading)
├── scripts/
│   ├── utils.py             # File-path registry + LLM client helper
│   ├── llm_client.py        # Claude (Anthropic) client
│   └── methods/             # Scaffolding conditions (see below)
│       ├── xml_view.py      #   xml   — raw XML in the prompt
│       ├── json_view.py     #   json  — JSONL view in the prompt
│       ├── tool_use.py      #   tool  — path + run_python tool
│       ├── tool_revise.py
│       ├── tool_continuation.py
│       ├── plan_execute.py
│       └── plan_execute_revise.py   # PER agent (main method)
├── data/
│   ├── network/             # SUMO networks (.net.xml, _adjacency.json, _tls.add.xml)
│   └── trips/               # Vehicle demand (.rou.xml)
└── QAdataset/
    ├── questions/           # {network}_{type}.csv — 5 samples per file (question + ground_truth)
    └── results/             # Written here at run time (git-ignored)
```

## LLM Strategies

`run_experiment.py --condition <name>` selects how the SUMO files are exposed to
the model. Available conditions:

| Condition | Description |
|---|---|
| `naive` | File descriptions only, no file contents. |
| `xml` | Raw SUMO XML inserted verbatim into the prompt (baseline). |
| `react` | `tool` with a revise loop |
| `plan_execute` | Plan then execute over the files. |
| `plan_execute_revise` | **PER agent** — plan, execute, and revise. 


## Dataset

`QAdataset/questions/{network}_{type}.csv` holds 5 samples (`sample_id` 0–4) per
(network, type) pair, each row carrying the `question` and its `ground_truth`.
Networks: `grid_8x8`, `random`, `times_square`. Question types
fall into three categories: **retrieval** (single field lookup), **reasoning**
(single file, requires computation), and **multi-step reasoning** (multiple
files + multi-stage computation).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Provide your Claude (Anthropic) API key via an environment variable or a file
at the repo root. Only Claude (`claude-*`) models are supported.

| Backend | Models (prefix) | Env var | Key file |
|---|---|---|---|
| Anthropic | `claude-*` | `ANTHROPIC_API_KEY` | `claude_api.txt` |

> The key file is git-ignored and never committed.

## Running experiments

```bash
# One condition / network / type (5 questions)
python run_experiment.py --condition plan_execute_revise \
    --network times_square --type num_lanes --model claude-sonnet-4-6

# A single question type across all networks
python run_experiment.py --condition xml --type both_junctions

# The full matrix
python run_experiment.py --all --condition plan_execute_revise
```

Results are written to `QAdataset/results/{condition}_{network}_{type}.csv`
(use `--out-subdir NAME` to write under a subfolder). Existing result files are
skipped unless you pass `--force`.

## Evaluating

```bash
# Score everything under QAdataset/results/
python evaluate.py

# Score a specific run directory
python evaluate.py --results-dir QAdataset/results/<subdir>
```

`evaluate.py` writes `*_evaluated.csv` alongside each result file and prints
accuracy per (condition, network, type).
