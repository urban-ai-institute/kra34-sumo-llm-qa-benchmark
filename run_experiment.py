#!/usr/bin/env python3
"""
SUMO-SimQA — run setup methods on the question dataset.

Reads questions from QAdataset/questions/<network>_<type>.csv and writes
responses to QAdataset/results/<condition>_<network>_<type>.csv.

Execution order is optimized for Anthropic prompt caching: questions are
grouped by (condition, network, files_used), and within each group, all
type×sample pairs are processed back-to-back. Since the system prompt
is byte-identical across the group, the first call seeds the cache and
subsequent calls hit it (~94.8% hit rate expected for a full run).

Usage examples:
  python run_experiment.py --all
  python run_experiment.py --condition xml --network grid_8x8
  python run_experiment.py --type both_junctions
  python run_experiment.py --all --force          # ignore existing results
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from collections import defaultdict, OrderedDict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
QUESTIONS_DIR = ROOT_DIR / "QAdataset" / "questions"
RESULTS_DIR = ROOT_DIR / "QAdataset" / "results"

sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "scripts"))
from utils import DEFAULT_MODEL, NETWORKS  # noqa: E402
from methods import ALL_METHODS  # noqa: E402

# Core setups (paper) + round-budget ablation (PER with N rounds).
CORE_CONDITIONS = ["file", "xml", "react", "plan_execute", "plan_execute_revise"]
ABLATION_CONDITIONS = ["plan_execute_revise_1r", "plan_execute_revise_3r",
                       "plan_execute_revise_5r", "plan_execute_revise_10r"]
CONDITIONS = CORE_CONDITIONS + ABLATION_CONDITIONS


# =====================================================================
# Plan construction
# =====================================================================

def all_question_types() -> list[str]:
    """Return the full list of question types from the questions/ files,
    sorted by file name (matches generate_qa.py registry order)."""
    types: list[str] = []
    for net in NETWORKS:
        for path in sorted(QUESTIONS_DIR.glob(f"{net}_*.csv")):
            t = path.stem[len(net) + 1:]
            if t not in types:
                types.append(t)
    return types


def build_plan(args) -> list[tuple[str, str, str]]:
    """Build the (condition, network, type) work plan from CLI flags."""
    types = all_question_types()
    if args.type:
        if args.type not in types:
            print(f"ERROR: unknown type '{args.type}'. Known: {types[:3]}...", file=sys.stderr)
            sys.exit(1)
        types = [args.type]

    networks = [args.network] if args.network else NETWORKS
    conditions = [args.condition] if args.condition else CONDITIONS

    plan = []
    for c in conditions:
        for n in networks:
            for t in types:
                if (QUESTIONS_DIR / f"{n}_{t}.csv").exists():
                    plan.append((c, n, t))
    return plan


def files_used_for_csv(network: str, type_: str) -> list[str]:
    """Read files_used from the FIRST row of the questions CSV.
    All rows of one type share the same files_used (set by generator)."""
    path = QUESTIONS_DIR / f"{network}_{type_}.csv"
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        first = next(reader, None)
    if first is None:
        raise RuntimeError(f"empty CSV: {path}")
    return first["files_used"].split(",")


def group_for_caching(plan: list[tuple[str, str, str]]) -> "OrderedDict":
    """Group the plan by (condition, network, files_used) so all calls
    sharing a system prompt are processed back-to-back. Within a group,
    types are kept in plan order."""
    groups: "OrderedDict[tuple, list[str]]" = OrderedDict()
    for cond, net, type_ in plan:
        files_used = tuple(files_used_for_csv(net, type_))
        key = (cond, net, files_used)
        if key not in groups:
            groups[key] = []
        groups[key].append(type_)
    return groups


# =====================================================================
# CSV I/O
# =====================================================================

RESULT_FIELDS = ["network", "type", "sample_id", "question",
                 "ground_truth", "files_used", "response_text"]

USAGE_FIELDS = ["network", "type", "sample_id",
                "input_tokens", "cached_input_tokens", "cache_write_tokens",
                "output_tokens", "api_calls", "seconds"]

# Per-question token accounting is opt-in (set TRACK_USAGE=1) so default runs
# behave exactly as before.
TRACK_USAGE = os.environ.get("TRACK_USAGE") == "1"


OUT_DIR = RESULTS_DIR  # overridden by --out-subdir


def result_path(condition: str, network: str, type_: str) -> Path:
    return OUT_DIR / f"{condition}_{network}_{type_}.csv"


def usage_path(condition: str, network: str, type_: str) -> Path:
    return OUT_DIR / f"usage_{condition}_{network}_{type_}.csv"


def already_done(path: Path) -> bool:
    """Type-level resume: a result CSV is 'done' iff it exists AND has
    a non-empty `response_text` for every row."""
    if not path.exists():
        return False
    try:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        return bool(rows) and all((r.get("response_text") or "").strip() for r in rows)
    except Exception:
        return False


def write_results(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in RESULT_FIELDS})


# =====================================================================
# Main loop
# =====================================================================

def run_type(condition: str, network: str, type_: str,
             files_used: list[str], model: str) -> tuple[int, int, float]:
    """Process one (condition, network, type): 5 LLM calls. Writes the
    result CSV. Returns (n_done, n_errors, elapsed_seconds)."""
    method = ALL_METHODS[condition]
    q_path = QUESTIONS_DIR / f"{network}_{type_}.csv"
    out_path = result_path(condition, network, type_)

    with open(q_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if TRACK_USAGE:
        from llm_client import reset_usage, get_usage

    out_rows = []
    usage_rows = []
    errors = 0
    t_start = time.time()
    for row in rows:
        question = row["question"]
        row_files = row["files_used"].split(",")
        if TRACK_USAGE:
            reset_usage()
        q_start = time.time()
        try:
            response = method(network, question, row_files, model)
        except Exception as e:
            response = f"ERROR: {type(e).__name__}: {e}"
            errors += 1
        out_rows.append({**row, "response_text": response})
        if TRACK_USAGE:
            u = get_usage()
            usage_rows.append({
                "network": network, "type": type_,
                "sample_id": row.get("sample_id", ""),
                "input_tokens": u["input"],
                "cached_input_tokens": u["cached_input"],
                "cache_write_tokens": u["cache_write"],
                "output_tokens": u["output"],
                "api_calls": u["calls"],
                "seconds": round(time.time() - q_start, 2),
            })

    write_results(out_path, out_rows)
    if TRACK_USAGE:
        up = usage_path(condition, network, type_)
        up.parent.mkdir(parents=True, exist_ok=True)
        with open(up, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=USAGE_FIELDS)
            w.writeheader()
            w.writerows(usage_rows)
    elapsed = time.time() - t_start
    return len(out_rows), errors, elapsed


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--all", action="store_true", help="run the entire matrix")
    p.add_argument("--condition", choices=CONDITIONS)
    p.add_argument("--network", choices=NETWORKS)
    p.add_argument("--type")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--out-subdir", default=None,
                   help="write results into RESULTS_DIR/<subdir>/ (e.g. a model name) "
                        "to avoid colliding with the main Claude results")
    p.add_argument("--force", action="store_true", help="ignore existing result CSVs")
    args = p.parse_args()

    global OUT_DIR
    if args.out_subdir:
        OUT_DIR = RESULTS_DIR / args.out_subdir
        OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not (args.all or args.condition or args.network or args.type):
        p.error("specify at least one of --all / --condition / --network / --type")

    plan = build_plan(args)
    groups = group_for_caching(plan)

    print(f"Plan: {len(plan)} (condition, network, type) units in {len(groups)} cache groups")
    print(f"Model: {args.model}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    grand_done = 0
    grand_errors = 0
    grand_skipped = 0
    t_overall = time.time()

    for (cond, net, files), types in groups.items():
        files_list = list(files)
        n_q = sum(5 for _ in types)  # 5 samples per type
        print(f"\n[{cond} | {net} | files={','.join(files_list)}]  "
              f"{len(types)} types ({n_q} questions)")

        for i, type_ in enumerate(types, 1):
            out_path = result_path(cond, net, type_)
            if already_done(out_path) and not args.force:
                print(f"  [{i}/{len(types)}] {type_:<40} SKIP (already done)")
                grand_skipped += 5
                continue
            n_done, n_err, elapsed = run_type(cond, net, type_, files_list, args.model)
            grand_done += n_done
            grand_errors += n_err
            err_str = f", {n_err} ERRORS" if n_err else ""
            print(f"  [{i}/{len(types)}] {type_:<40} {n_done}/5 done in {elapsed:5.1f}s{err_str}")

    elapsed_total = time.time() - t_overall
    print(f"\n=== Done in {elapsed_total/60:.1f} min ===")
    print(f"  Done:    {grand_done}")
    print(f"  Skipped: {grand_skipped}")
    print(f"  Errors:  {grand_errors}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
