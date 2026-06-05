# SUMO-SimQA

A benchmark for measuring how well LLMs can read and reason over raw
[SUMO](https://eclipse.dev/sumo/) traffic-simulation files. Each question is
answered by an LLM that is given the simulation files through one of several
*setups*, ranging from dumping raw XML into the prompt to a
Plan-Execute-Revise (PER) agent that writes and runs Python over the files.

This repository contains the **experiment and evaluation logic**:
collecting model answers (`run_experiment.py`) and scoring them
(`evaluate.py`), together with the question dataset and SUMO scenario files.

## Repository layout

```
SUMO-SimQA/
├── run_experiment.py        # Collect LLM answers for (condition, network, type)
├── evaluate.py              # Score answers and aggregate accuracy
├── requirements.txt
├── scripts/
│   ├── utils.py             # File-path registry + LLM client helper
│   ├── llm_client.py        # Claude (Anthropic) client
│   └── methods/             # Setup conditions (see below)
│       ├── naive.py         #   naive               — file paths only
│       ├── xml_view.py      #   xml                 — raw XML in the prompt
│       ├── tool_use.py      #   tool   (ReAct)      — code execution
│       ├── plan_execute.py  #   plan_execute (PE)   — plan then execute
│       └── plan_execute_revise.py  # plan_execute_revise (PER) — plan, execute, revise
├── data/
│   ├── network/             # SUMO networks (.net.xml, _adjacency.json, _tls.add.xml)
│   └── trips/               # Vehicle demand (.rou.xml)
└── QAdataset/
    ├── questions/           # {network}_{type}.csv — 5 samples per file (question + ground_truth)
    └── results/             # Written here at run time (git-ignored)
```

## Setups

`run_experiment.py --condition <name>` selects how the SUMO files are exposed to
the LLM. Available setups:

| Setup | `--condition` | Description |
|---|---|---|
| File-path (Naive) | `naive` | File paths only, no contents, no code. |
| Full-XML (XML) | `xml` | Raw SUMO XML inserted verbatim into the prompt. |
| Code execution (ReAct) | `tool` | LLM executes Python code (no plan, no revision). |
| Plan-Execute (PE) | `plan_execute` | LLM plans, then executes as code (no revision). |
| Plan-Execute-Revise (PER) | `plan_execute_revise` | LLM plans, executes, then revises the plan. |


## Dataset

`QAdataset/questions/{network}_{type}.csv` holds 5 samples (`sample_id` 0–4) per
(network, type) pair, each row carrying the `question` and its `ground_truth`.

SUMO-SimQA contains **480 questions** = 32 question types × 3 networks × 5 samples.
Networks: `grid_8x8`, `random`, `times_square`. The 32 types fall into three
categories of increasing complexity: **Retrieval** (12 types — single field lookup),
**Reasoning** (10 types — single file, requires computation), and
**Multi-step Reasoning** (10 types — combines two or more files).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Provide your Claude (Anthropic) API key via an environment variable or a file
at the repo root.

| Backend | Models (prefix) | Env var | Key file |
|---|---|---|---|
| Anthropic | `claude-*` | `ANTHROPIC_API_KEY` | `claude_api.txt` |

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
