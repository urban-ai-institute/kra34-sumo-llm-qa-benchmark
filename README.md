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
│   ├── llm_client.py        # Unified client (Anthropic / OpenAI / Gemini)
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

> **Note on `data/output/`.** The large simulation outputs (`*_fcd.xml`,
> `*_tripinfo.xml`) are **not** bundled (they exceed GitHub's file-size limit).
> Question types whose `files_used` includes `fcd` or `tripinfo` require those
> files to be placed under `data/output/` first. Question types that only need
> `net`, `rou`, or `add` files run out of the box.

## Scaffolding conditions

`run_experiment.py --condition <name>` selects how the SUMO files are exposed to
the model. Available conditions:

| Condition | Description |
|---|---|
| `xml` | Raw SUMO XML inserted verbatim into the prompt (baseline). |
| `json` | The same files converted to a flat JSONL view in the prompt. |
| `tool` | Only file *paths* plus a `run_python` tool; the model writes Python. |
| `tool_revise` | `tool` with a revise loop (`tool_revise_1r`, `tool_revise_3r`). |
| `tool_continuation` | Tool use with conversational continuation. |
| `plan_execute` | Plan then execute over the files. |
| `plan_execute_revise` | **PER agent** — plan, execute, and revise. Router-turn budget variants: `plan_execute_revise_{1r,3r,5r,10r}`. |
| `naive` | File descriptions only, no file contents. |

## Dataset

`QAdataset/questions/{network}_{type}.csv` holds 5 samples (`sample_id` 0–4) per
(network, type) pair, each row carrying the `question` and its `ground_truth`.
Networks: `grid_8x8`, `random`, `random_large`, `times_square`. Question types
fall into three categories: **retrieval** (single field lookup), **reasoning**
(single file, requires computation), and **multi-step reasoning** (multiple
files + multi-stage computation).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Provide an API key for whichever backend you use, via an environment variable
or a file at the repo root:

| Backend | Models (prefix) | Env var | Key file |
|---|---|---|---|
| Anthropic | `claude-*` | `ANTHROPIC_API_KEY` | `claude_api.txt` |
| OpenAI | `gpt-*`, `o*` | `OPENAI_API_KEY` | `openai_api.txt` |
| Gemini | `gemini-*` | `GEMINI_API_KEY` | `gemini_api.txt` |

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
