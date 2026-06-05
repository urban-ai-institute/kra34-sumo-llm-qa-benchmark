#!/usr/bin/env python3
"""Generate LaTeX tables for the two PER ablations:

  1. API ablation  -> Tables/table_ablation_api.tex
     PER accuracy by category x network for Claude / GPT-5.4-mini / Gemini-3.1-pro.
  2. Router-turn ablation -> Tables/table_ablation_router_turns.tex
     PER accuracy on multi-step reasoning tasks vs. router-turn budget {1,3,5,10}.

Reads evaluated CSVs written by evaluate.py.
"""

import csv
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)
ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "QAdataset" / "results"
TABLES = ROOT / "paper_writing" / "NetTrafficQA_CIKM" / "Tables"

NETWORKS = ["random", "grid_8x8", "times_square"]
NET_HDR = {"random": "Random", "grid_8x8": r"Grid $8\times8$", "times_square": "Times Square"}

# Category -> list of type ids (must match update_paper_tables.py).
RETRIEVAL = ["both_junctions", "num_lanes", "junction_coord", "vehicle_depart_time",
             "vehicle_depart_edge", "vehicle_route", "vehicles_with_same_origin",
             "vehicle_travel_time", "vehicle_arrival_time", "vehicle_speed_at_time",
             "tls_phase_count", "tls_longest_green_phase"]
REASONING = ["shortest_path_full", "bottleneck_edge", "avg_route_length_in_window",
             "route_edit_distance_pair", "route_overlap_count", "vehicle_highest_timeloss",
             "avg_trip_duration", "vehicle_max_speed", "edge_peak_vehicle_count",
             "tls_lowest_green_ratio"]
MULTISTEP = ["worst_congestion_od", "gap_violations", "peak_offpeak_degradation",
             "lane_utilisation", "incomplete_od", "junction_inflow_cv",
             "edge_lane_entropy", "tls_vehicle_delay", "tls_approach_queue",
             "tls_phase_demand_imbalance"]


def _counts(path: Path):
    """Return (n_correct, n_total) from an evaluated CSV, or (0, 0)."""
    if not path.exists():
        return 0, 0
    rows = list(csv.DictReader(open(path)))
    if not rows:
        return 0, 0
    c = sum(1 for r in rows if r["correct"] == "True")
    return c, len(rows)


def cat_acc(results_dir: Path, cond: str, net: str, types: list[str]):
    """Pooled accuracy (%) over all samples of all types in a category."""
    tc = tt = 0
    for t in types:
        c, n = _counts(results_dir / f"{cond}_{net}_{t}_evaluated.csv")
        tc += c
        tt += n
    if tt == 0:
        return None
    return round(tc * 100 / tt, 1)


def fmt(v):
    return "--" if v is None else f"{v:.1f}"


def bold_row(vals):
    """Bold the max across a list of (possibly None) floats."""
    m = max((v for v in vals if v is not None), default=None)
    out = []
    for v in vals:
        if v is None:
            out.append("--")
        elif m is not None and v == m:
            out.append(rf"\textbf{{{v:.1f}}}")
        else:
            out.append(f"{v:.1f}")
    return out


# =====================================================================
# Table 1: API ablation
# =====================================================================

# (label, results_dir, condition)
# (label, results_dir, condition). results_dir=None -> empty placeholder row.
API_MODELS = [
    ("Claude-Sonnet 4.6", RESULTS, "plan_execute_revise"),
    ("Claude-Haiku 4.5", RESULTS / "claude-haiku-4-5", "plan_execute_revise"),
    ("GPT-5.4-mini", RESULTS / "gpt-5.4-mini", "plan_execute_revise"),
    ("Gemini-3.5-flash", RESULTS / "gemini-3.5-flash", "plan_execute_revise"),
]
CATS = [("Retrieval", RETRIEVAL), ("Reasoning", REASONING),
        ("Multi-step", MULTISTEP)]


def pooled_acc(results_dir: Path, cond: str, types: list[str]):
    """Accuracy (%) pooled over all samples of all types across all
    networks that have evaluated results (missing nets are skipped)."""
    tc = tt = 0
    for net in NETWORKS:
        for t in types:
            c, n = _counts(results_dir / f"{cond}_{net}_{t}_evaluated.csv")
            tc += c
            tt += n
    if tt == 0:
        return None
    return round(tc * 100 / tt, 1)


def gen_table_api():
    col_spec = "l|" + "c" * len(CATS)
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{API ablation: Plan-Execute-Revise (PER) accuracy (\%) by question "
        r"category for backbone LLMs, pooled across the three SUMO networks. "
        r"Best per column in \textbf{bold}.}",
        r"\label{tab:ablation_api}",
        r"\resizebox{\columnwidth}{!}{%",
        rf"\begin{{tabular}}{{{col_spec}}}",
        r"\toprule",
        r"\textbf{Model} & " + " & ".join(rf"\textbf{{{c}}}" for c, _ in CATS) + r" \\",
        r"\midrule",
    ]
    # rows: one per model; placeholder rows (rdir=None) render as all "--"
    matrix = []
    for label, rdir, cond in API_MODELS:
        if rdir is None:
            matrix.append((label, [None] * len(CATS)))
        else:
            matrix.append((label, [pooled_acc(rdir, cond, types) for _, types in CATS]))
    # bold the best per column (category)
    col_max = [max((row[j] for _, row in matrix if row[j] is not None), default=None)
               for j in range(len(CATS))]
    for label, row in matrix:
        cells = []
        for j, v in enumerate(row):
            if v is None:
                cells.append("--")
            elif col_max[j] is not None and v == col_max[j]:
                cells.append(rf"\textbf{{{v:.1f}}}")
            else:
                cells.append(f"{v:.1f}")
        lines.append(f"{label} & " + " & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}%", r"}", r"\end{table}", ""]
    return "\n".join(lines)


# =====================================================================
# Table 2: Router-turn ablation (multi-step only)
# =====================================================================

# (turns label, condition)
ROUTER_CONDS = [
    ("1", "plan_execute_revise_1r"),
    ("3", "plan_execute_revise"),       # default = 3 router turns
    ("5", "plan_execute_revise_5r"),
    ("10", "plan_execute_revise_10r"),
]


ROUTER_NET_STYLE = [
    ("random", "Random", "royalblue", "*"),
    ("grid_8x8", r"Grid $8\times8$", "firebrick", "square*"),
    ("times_square", "Times Square", "darkgreen", "triangle*"),
]


def gen_table_router_turns():
    turns = [int(t) for t, _ in ROUTER_CONDS]
    series = {}  # net -> list of (turn, acc)
    for net, _, _, _ in ROUTER_NET_STYLE:
        pts = []
        for (tlabel, cond), x in zip(ROUTER_CONDS, turns):
            pts.append((x, cat_acc(RESULTS, cond, net, MULTISTEP)))
        series[net] = pts

    lines = [
        r"\definecolor{royalblue}{RGB}{65,105,225}",
        r"\definecolor{firebrick}{RGB}{178,34,34}",
        r"\definecolor{darkgreen}{RGB}{0,100,0}",
        r"\begin{figure}[t]",
        r"\centering",
        r"\begin{tikzpicture}[font=\fontfamily{ptm}\selectfont]",
        r"\begin{axis}[",
        r"    width=0.95\columnwidth, height=0.62\columnwidth,",
        r"    xlabel={\# of router calls}, ylabel={Accuracy (\%)},",
        r"    label style={font=\LARGE\fontfamily{ptm}\selectfont},",
        r"    tick label style={font=\fontfamily{ptm}\selectfont},",
        r"    legend style={draw=none, font=\fontfamily{ptm}\selectfont},",
        rf"    xtick={{{','.join(str(t) for t in turns)}}},",
        r"    xmin=0, xmax=11, ymin=60, ymax=100,",
        r"    legend pos=south east, legend cell align={left},",
        r"    grid=both, grid style={gray!20}, thick, mark size=2pt,",
        r"]",
    ]
    for net, label, color, mark in ROUTER_NET_STYLE:
        coords = " ".join(
            f"({x},{a:.1f})" for x, a in series[net] if a is not None)
        lines.append(rf"\addplot[{color}, mark={mark}] coordinates {{{coords}}};")
        lines.append(rf"\addlegendentry{{{label}}}")
    lines += [
        r"\end{axis}",
        r"\end{tikzpicture}",
        r"\caption{Router-turn ablation: PER accuracy (\%) on the multi-step "
        r"reasoning tasks as the router-turn budget varies.}",
        r"\label{fig:ablation_router_turns}",
        r"\end{figure}",
        "",
    ]
    return "\n".join(lines)


def main():
    TABLES.mkdir(parents=True, exist_ok=True)
    (TABLES / "table_ablation_api.tex").write_text(gen_table_api())
    (TABLES / "table_ablation_router_turns.tex").write_text(gen_table_router_turns())
    print("Wrote table_ablation_api.tex and table_ablation_router_turns.tex")
    print("\n--- API ablation ---")
    print(gen_table_api())
    print("\n--- Router-turn ablation ---")
    print(gen_table_router_turns())


if __name__ == "__main__":
    main()
