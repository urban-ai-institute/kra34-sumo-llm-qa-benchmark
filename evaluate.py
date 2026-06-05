#!/usr/bin/env python3
"""
Evaluate collected LLM responses across the SUMO-SimQA matrix.

Reads response CSVs from `QA_dataset/results/` (flat layout):
    <condition>_<network>_<type>.csv
e.g. xml_grid_8x8_both_junctions.csv,
     tool_times_square_edge_density_trend.csv.

Each CSV contains rows from `QA_dataset/questions/<network>_<type>.csv`
plus a `response_text` column. We extract the model's final answer,
compare against `ground_truth` using a per-type matcher, and write
<condition>_<network>_<type>_evaluated.csv next to it.

Aggregate accuracy is printed grouped by (condition, network, type).

Usage:
  python evaluate.py                       # evaluate everything in QA_dataset/results
  python evaluate.py --condition xml       # filter by condition
  python evaluate.py --network grid_8x8  # filter by network
  python evaluate.py --type vehicle_route  # filter by question type
  python evaluate.py --input <path.csv>    # evaluate a single file
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = ROOT_DIR / "QA_dataset" / "results"

CONDITIONS = ["file", "xml", "react", "plan_execute", "plan_execute_revise",
              "plan_execute_revise_1r", "plan_execute_revise_3r",
              "plan_execute_revise_5r", "plan_execute_revise_10r"]
NETWORKS = ["grid_8x8", "random", "times_square"]
ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth"]


# =====================================================================
# Answer extraction
# =====================================================================

def get_final_answer_text(response_text: str) -> str:
    """For tool-use responses (a JSON trace list), return the model's
    final assistant text. For all other conditions, return the response
    string unchanged.
    """
    if not response_text:
        return ""
    try:
        trace = json.loads(response_text)
        if isinstance(trace, list):
            for entry in reversed(trace):
                if isinstance(entry, dict) and entry.get("role") in ("final_answer", "assistant"):
                    return entry.get("text", "")
            return ""
    except (json.JSONDecodeError, TypeError):
        pass
    return response_text


def extract_final_line(text: str) -> str:
    """Extract the last meaningful line, stripping markdown emphasis."""
    if not text:
        return ""
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"`+", "", text)
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    return lines[-1] if lines else ""


_NONE_PHRASES = {"none", "n/a", "null"}


def looks_like_none(text: str) -> bool:
    """Does this final-line text mean 'no answer'?

    Accepts 'None' / 'none' / 'NONE' / 'n/a' as either the entire
    stripped string or as the LAST token. Also recognizes the literal
    phrase 'no answer'.
    """
    s = text.strip().strip(".:,;!?\"' ").lower()
    if s in _NONE_PHRASES or s == "no answer":
        return True
    toks = s.split()
    if toks:
        last = toks[-1].strip(".:,;!?\"' ")
        if last in _NONE_PHRASES:
            return True
    return False


# =====================================================================
# Tokenization helpers (for IDs and sequences)
# =====================================================================

_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-:#\.]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text or "")


def extract_arrow_sequence(text: str) -> list[str]:
    """Extract a sequence of tokens from 'X -> Y -> Z' style text."""
    if not text:
        return []
    parts = re.split(r"\s*->\s*", text.strip())
    out = []
    for p in parts:
        # In case the model wrote multi-token names like "J1 J2", just keep
        # the first whitespace-separated token of each part.
        toks = p.strip().split()
        if toks:
            out.append(toks[0])
    return out


# =====================================================================
# Per-type matchers
# =====================================================================

def match_integer(pred: str, gt: str) -> bool:
    final = extract_final_line(pred)
    try:
        gt_val = int(gt.strip())
    except ValueError:
        return False
    nums = re.findall(r"-?\d+", final)
    if not nums:
        return False
    try:
        return int(nums[-1]) == gt_val
    except ValueError:
        return False


def match_float_rel(pred: str, gt: str,
                    rel_tol: float = 0.05, abs_tol: float = 0.01) -> bool:
    """Match a single float with relative tolerance + absolute floor.

    |pred - gt| <= max(rel_tol * |gt|, abs_tol).
    abs_tol protects values close to zero where rel_tol underflows.
    """
    final = extract_final_line(pred)
    try:
        gt_val = float(gt.strip())
    except ValueError:
        return False
    nums = re.findall(r"-?\d+(?:\.\d+)?", final)
    if not nums:
        return False
    try:
        p_val = float(nums[-1])
    except ValueError:
        return False
    tol = max(rel_tol * abs(gt_val), abs_tol)
    return abs(p_val - gt_val) <= tol


def match_float_or_none(pred: str, gt: str, **kw) -> bool:
    final = extract_final_line(pred)
    if gt.strip().lower() == "none":
        return looks_like_none(final)
    if looks_like_none(final):
        return False
    return match_float_rel(pred, gt, **kw)


def match_string_exact(pred: str, gt: str) -> bool:
    return extract_final_line(pred).strip().lower() == gt.strip().lower()


def match_string_or_none(pred: str, gt: str) -> bool:
    final = extract_final_line(pred).strip().lower()
    gt_clean = gt.strip().lower()
    if gt_clean == "none":
        return looks_like_none(final)
    if looks_like_none(final):
        return False
    # Exact match OR gt appears as a token in the final line
    if final == gt_clean:
        return True
    return any(t.lower() == gt_clean for t in tokenize(final))


def match_yes_no(pred: str, gt: str) -> bool:
    final = extract_final_line(pred).strip().lower()
    gt_clean = gt.strip().lower()
    if gt_clean not in ("yes", "no"):
        return False
    # Find the LAST yes/no token in the final line.
    matches = re.findall(r"\b(yes|no)\b", final)
    return bool(matches) and matches[-1] == gt_clean


def match_enum(pred: str, gt: str, options: list[str]) -> bool:
    final = extract_final_line(pred).strip().lower()
    gt_clean = gt.strip().lower()
    if gt_clean not in [o.lower() for o in options]:
        return False
    if final == gt_clean:
        return True
    # gt appears as a token / substring in final line
    if gt_clean in final.split() or gt_clean in final:
        # Make sure no OTHER enum option appears that conflicts
        other_present = [o.lower() for o in options
                         if o.lower() != gt_clean and o.lower() in final.split()]
        return not other_present
    return False


def match_ordinal_or_none(pred: str, gt: str) -> bool:
    final = extract_final_line(pred).strip().lower()
    gt_clean = gt.strip().lower()
    if gt_clean == "none":
        return looks_like_none(final)
    if gt_clean not in ORDINALS:
        return False
    # The last ordinal-like token in the response wins.
    found = re.findall(r"\b(first|second|third|fourth|fifth|sixth)\b", final)
    return bool(found) and found[-1] == gt_clean


def match_coord(pred: str, gt: str, tol: float = 1.0) -> bool:
    """Match 'x, y' coordinates with an absolute tolerance per axis."""
    gt_nums = re.findall(r"-?\d+(?:\.\d+)?", gt)
    final = extract_final_line(pred)
    p_nums = re.findall(r"-?\d+(?:\.\d+)?", final)
    if len(gt_nums) < 2 or len(p_nums) < 2:
        return False
    try:
        return all(abs(float(gt_nums[i]) - float(p_nums[i])) <= tol for i in range(2))
    except ValueError:
        return False


def match_count_start(pred: str, gt: str) -> bool:
    """Match 'count, start_time' pair (both integers)."""
    final = extract_final_line(pred)
    gt_parts = [s.strip() for s in gt.split(",")]
    if len(gt_parts) < 2:
        return False
    try:
        gt_count = int(gt_parts[0])
        gt_start = int(gt_parts[1])
    except ValueError:
        return False
    nums = re.findall(r"-?\d+", final)
    if len(nums) < 2:
        return False
    try:
        return int(nums[0]) == gt_count and int(nums[1]) == gt_start
    except ValueError:
        return False


def match_od_pair(pred: str, gt: str) -> bool:
    """Order-sensitive match for 'origin_edge, destination_edge'."""
    final = extract_final_line(pred)
    gt_tokens = tokenize(gt)
    p_tokens = tokenize(final)
    if len(gt_tokens) < 2:
        return False
    gt_pair = (gt_tokens[0].lower(), gt_tokens[1].lower())
    p_lower = [t.lower() for t in p_tokens]
    for i in range(len(p_lower) - 1):
        if (p_lower[i], p_lower[i + 1]) == gt_pair:
            return True
    return False


def match_both_junctions(pred: str, gt: str) -> bool:
    """Order-insensitive match for 'X, Y' junction pairs."""
    final = extract_final_line(pred)
    gt_tokens = tokenize(gt)
    p_tokens = tokenize(final)
    if len(gt_tokens) < 2:
        return False
    gt_set = {t.lower() for t in gt_tokens[:2]}
    # Try every adjacent pair in pred
    p_lower = [t.lower() for t in p_tokens]
    for i in range(len(p_lower) - 1):
        if {p_lower[i], p_lower[i+1]} == gt_set:
            return True
    return False


def match_sequence_exact(pred: str, gt: str) -> bool:
    """Exact ordered match between GT sequence ('X -> Y -> ...') and pred."""
    gt_seq = [t.lower() for t in extract_arrow_sequence(gt)]
    if not gt_seq:
        return False
    # Try parsing the entire pred (including codegen final-line)
    final_text = get_final_answer_text(pred)
    # The final answer for vehicle_route should itself be the arrow-joined string.
    # We consider the FULL final assistant text (not just last line) so that
    # very long answers wrap-broken onto multiple lines still parse.
    p_seq = [t.lower() for t in extract_arrow_sequence(final_text)]
    if p_seq == gt_seq:
        return True
    # Fall back to last-line interpretation
    p_seq2 = [t.lower() for t in extract_arrow_sequence(extract_final_line(pred))]
    return p_seq2 == gt_seq


def match_path_or_none(pred: str, gt: str) -> bool:
    """Path match with None handling. Looks for the GT sequence as a
    contiguous run of tokens (or arrow-separated) in the prediction.
    """
    final_line = extract_final_line(pred)
    if gt.strip().lower() == "none":
        return looks_like_none(final_line)
    if looks_like_none(final_line):
        return False

    # Try arrow-style first
    gt_seq = [t.lower() for t in extract_arrow_sequence(gt)]
    if gt_seq:
        full_text = get_final_answer_text(pred)
        for src in (full_text, final_line):
            p_seq = [t.lower() for t in extract_arrow_sequence(src)]
            if p_seq == gt_seq:
                return True
            # Accept alternative shortest paths: same length, same endpoints
            if (len(p_seq) == len(gt_seq) and len(p_seq) >= 2
                    and p_seq[0] == gt_seq[0] and p_seq[-1] == gt_seq[-1]):
                return True

    # Fallback: contiguous token subsequence
    gt_tokens = [t.lower() for t in tokenize(gt)]
    p_tokens = [t.lower() for t in tokenize(get_final_answer_text(pred))]
    if not gt_tokens:
        return False
    n = len(gt_tokens)
    for i in range(len(p_tokens) - n + 1):
        if p_tokens[i:i+n] == gt_tokens:
            return True
    return False


def match_single_id(pred: str, gt: str) -> bool:
    """Check if the GT ID appears as a token in the final line."""
    final = extract_final_line(pred)
    gt_clean = gt.strip().lower()
    return gt_clean in [t.lower() for t in tokenize(final)]


# =====================================================================
# Type → matcher dispatch
# =====================================================================

TYPE_MATCHERS: dict[str, callable] = {
    # Retrieval (12)
    "both_junctions": match_both_junctions,
    "num_lanes": match_integer,
    "junction_coord": match_coord,
    "vehicle_depart_time": match_float_rel,
    "vehicle_depart_edge": match_single_id,
    "vehicle_route": match_sequence_exact,
    "vehicles_with_same_origin": match_integer,
    "vehicle_travel_time": match_float_or_none,
    "vehicle_arrival_time": match_float_or_none,
    "vehicle_speed_at_time": match_float_rel,
    "tls_phase_count": match_integer,
    "tls_longest_green_phase": match_integer,
    # Reasoning — single-file (10)
    "shortest_path_full": match_path_or_none,
    "bottleneck_edge": match_single_id,
    "avg_route_length_in_window": match_float_or_none,
    "route_edit_distance_pair": match_od_pair,
    "route_overlap_count": match_od_pair,
    "vehicle_highest_timeloss": match_single_id,
    "avg_trip_duration": match_float_rel,
    "vehicle_max_speed": match_float_rel,
    "edge_peak_vehicle_count": match_integer,
    "tls_lowest_green_ratio": match_single_id,
    # Cross-file Reasoning — multiple files (10)
    "worst_congestion_od": match_od_pair,
    "gap_violations": match_single_id,
    "peak_offpeak_degradation": match_single_id,
    "lane_utilisation": match_single_id,
    "incomplete_od": match_od_pair,
    "junction_inflow_cv": match_single_id,
    "edge_lane_entropy": match_single_id,
    "tls_vehicle_delay": match_single_id,
    "tls_approach_queue": match_single_id,
    "tls_phase_demand_imbalance": match_single_id,
}


def compare_answers(pred: str, gt: str, type_name: str) -> bool:
    matcher = TYPE_MATCHERS.get(type_name)
    if matcher is None:
        # Conservative fallback
        return extract_final_line(pred).strip().lower() == gt.strip().lower()
    try:
        return bool(matcher(pred, gt))
    except Exception:
        return False


# =====================================================================
# File parsing
# =====================================================================

def parse_filename(stem: str) -> tuple[str | None, str | None, str | None]:
    """Parse '<condition>_<network>_<type>' from a CSV stem.

    Returns (condition, network, type) or (None, None, None) if it
    doesn't match the expected pattern.
    """
    for cond in CONDITIONS:
        if not stem.startswith(cond + "_"):
            continue
        rest = stem[len(cond) + 1:]
        # Strip a trailing _evaluated marker if present
        if rest.endswith("_evaluated"):
            rest = rest[: -len("_evaluated")]
        for net in NETWORKS:
            if rest.startswith(net + "_"):
                t = rest[len(net) + 1:]
                if t in TYPE_MATCHERS:
                    return cond, net, t
    return None, None, None


def evaluate_file(path: Path) -> list[dict]:
    """Evaluate one response CSV; return rows enriched with predicted+correct."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for row in rows:
        gt = row.get("ground_truth", "")
        type_name = row.get("type", "")
        response = row.get("response_text", "")
        predicted = get_final_answer_text(response)
        correct = compare_answers(predicted, gt, type_name)
        out.append({**row, "predicted": predicted, "correct": correct})
    return out


def write_evaluated(path: Path, rows: list[dict]) -> Path:
    """Write *_evaluated.csv next to the input path."""
    out_path = path.with_name(path.stem + "_evaluated.csv")
    if not rows:
        return out_path
    fieldnames = list(rows[0].keys())
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return out_path


# =====================================================================
# Aggregation
# =====================================================================

def compute_stats(rows: list[dict]) -> dict:
    n = len(rows)
    correct = sum(1 for r in rows if r.get("correct"))
    return {"n": n, "correct": correct, "accuracy": correct / n if n else 0.0}


def print_aggregate(grouped: dict[tuple, list[dict]]) -> None:
    print("\n" + "=" * 80)
    print("EVALUATION RESULTS")
    print("=" * 80)
    print(f"{'condition':<10} {'network':<14} {'type':<40} {'acc':>6}  n")
    print("-" * 80)
    for key in sorted(grouped):
        cond, net, t = key
        s = compute_stats(grouped[key])
        print(f"{cond:<10} {net:<14} {t:<40} {s['accuracy']*100:>5.1f}% {s['n']:>3}")
    print("-" * 80)


# =====================================================================
# CLI
# =====================================================================

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--condition", choices=CONDITIONS, default=None)
    p.add_argument("--network", choices=NETWORKS, default=None)
    p.add_argument("--type", default=None)
    p.add_argument("--input", default=None,
                   help="Evaluate a single CSV path instead of scanning results/.")
    p.add_argument("--results-dir", default=None,
                   help="Scan this directory instead of the default results/ "
                        "(e.g. results/<model> for cross-provider ablations).")
    args = p.parse_args()

    scan_dir = Path(args.results_dir) if args.results_dir else RESULTS_DIR

    if args.input:
        files = [Path(args.input)]
    else:
        files = sorted(scan_dir.glob("*.csv"))
        # Skip already-evaluated files (we will overwrite them anyway, but
        # they shouldn't be re-parsed as response files).
        files = [f for f in files if not f.stem.endswith("_evaluated")]

    grouped: dict[tuple, list[dict]] = defaultdict(list)
    n_files = 0
    for path in files:
        cond, net, t = parse_filename(path.stem)
        if not (cond and net and t):
            print(f"  SKIP {path.name}: cannot parse condition/network/type", file=sys.stderr)
            continue
        if args.condition and cond != args.condition:
            continue
        if args.network and net != args.network:
            continue
        if args.type and t != args.type:
            continue

        rows = evaluate_file(path)
        out_path = write_evaluated(path, rows)
        grouped[(cond, net, t)].extend(rows)
        n_files += 1
        print(f"  {path.name} -> {out_path.name}  ({sum(1 for r in rows if r['correct'])}/{len(rows)})")

    if not grouped:
        print(f"No matching response files under {scan_dir}", file=sys.stderr)
        return 1

    print_aggregate(grouped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
