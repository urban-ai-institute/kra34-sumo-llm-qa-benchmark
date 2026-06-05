#!/usr/bin/env python3
"""Generate updated LaTeX tables from evaluated results."""

import csv, sys
import numpy as np
from pathlib import Path

csv.field_size_limit(sys.maxsize)
RESULTS = Path(__file__).resolve().parent / "QAdataset" / "results"
TABLES = Path(__file__).resolve().parent / "paper_writing" / "NetTrafficQA_CIKM" / "Tables"

RETRIEVAL = [
    ("both_junctions", "Both Junctions"),
    ("num_lanes", r"Num.\ Lanes"),
    ("junction_coord", "Junction Coord."),
    ("vehicle_depart_time", r"Veh.\ Depart Time"),
    ("vehicle_depart_edge", r"Veh.\ Depart Edge"),
    ("vehicle_route", "Vehicle Route"),
    ("vehicles_with_same_origin", "Same-Origin Count"),
    ("vehicle_travel_time", r"Veh.\ Travel Time"),
    ("vehicle_arrival_time", r"Veh.\ Arrival Time"),
    ("vehicle_speed_at_time", r"Veh.\ Speed at Time"),
    ("tls_phase_count", "TLS Phase Count"),
    ("tls_longest_green_phase", "TLS Longest Green"),
]
REASONING = [
    ("shortest_path_full", "Shortest Path"),
    ("bottleneck_edge", "Bottleneck Edge"),
    ("avg_route_length_in_window", r"Avg.\ Route Length"),
    ("route_edit_distance_pair", r"Route Edit Dist.\ Pair"),
    ("route_overlap_count", "Route Overlap Count"),
    ("vehicle_highest_timeloss", "Highest Timeloss"),
    ("avg_trip_duration", r"Avg.\ Trip Duration"),
    ("vehicle_max_speed", r"Veh.\ Max Speed"),
    ("edge_peak_vehicle_count", r"Edge Peak Veh.\ Count"),
    ("tls_lowest_green_ratio", "TLS Lowest Green Ratio"),
]
MULTISTEP = [
    ("worst_congestion_od", "Worst Congestion OD"),
    ("gap_violations", "Gap Violations"),
    ("peak_offpeak_degradation", "Peak/Off-peak Degrad."),
    ("lane_utilisation", "Lane Utilisation"),
    ("incomplete_od", "Incomplete OD"),
    ("junction_inflow_cv", "Junction Inflow CV"),
    ("edge_lane_entropy", "Edge Lane Entropy"),
    ("tls_vehicle_delay", "TLS Congestion Ratio"),
    ("tls_approach_queue", "TLS Approach Queue"),
    ("tls_phase_demand_imbalance", "TLS Phase Imbalance"),
]

NETWORKS = ["random", "grid_8x8", "times_square"]
CONDS = ["naive", "xml", "tool_continuation", "plan_execute_revise"]


def get_acc(cond, net, t):
    f = RESULTS / f"{cond}_{net}_{t}_evaluated.csv"
    if not f.exists():
        return None
    rows = list(csv.DictReader(open(f)))
    if not rows:
        return None
    correct = sum(1 for r in rows if r["correct"] == "True")
    n = len(rows)
    return round(correct * 100 / n)


def get_correct_list(cond, net, t):
    """Per-question binary outcomes (100 if correct else 0) for one type."""
    f = RESULTS / f"{cond}_{net}_{t}_evaluated.csv"
    if not f.exists():
        return None
    rows = list(csv.DictReader(open(f)))
    if not rows:
        return None
    return [100 if r["correct"] == "True" else 0 for r in rows]


def bold_max(vals, group_size=None):
    """Return list of strings with max values bolded per network group."""
    if group_size is None:
        group_size = len(vals)
    out = []
    for i in range(0, len(vals), group_size):
        group = vals[i:i + group_size]
        group_max = max((v for v in group if v is not None), default=None)
        for v in group:
            if v is None:
                out.append("--")
            elif group_max is not None and v == group_max:
                out.append(rf"\textbf{{{v}}}")
            else:
                out.append(str(v))
    return out


def gen_table_all_results():
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Accuracy (\%) of all 32 question types across scaffolding conditions and three SUMO networks.",
        r"Best result per row in \textbf{bold}. PER = Plan-Execute-Revise.}",
        r"\label{tab:all_results}",
        r"\resizebox{0.95\textwidth}{!}{%",
        r"\begin{tabular}{l|cccc|cccc|cccc}",
        r"\toprule",
        r"\multirow{2}{*}{\textbf{Question Type}} & \multicolumn{4}{c|}{\textbf{Random}} & \multicolumn{4}{c|}{\textbf{Grid $8\times8$}} & \multicolumn{4}{c}{\textbf{Times Square}} \\",
        r"\cmidrule(lr){2-5} \cmidrule(lr){6-9} \cmidrule(lr){10-13}",
        r"  & Naive & XML & Tool Use & PER & Naive & XML & Tool Use & PER & Naive & XML & Tool Use & PER \\",
        r"\midrule",
    ]

    for section_label, types, is_last in [
        ("Retrieval", RETRIEVAL, False),
        ("Reasoning", REASONING, False),
        ("Multi-step reasoning", MULTISTEP, True),
    ]:
        n_types = len(types)
        lines.append(rf"\multicolumn{{13}}{{l}}{{\textbf{{{section_label}}} ({n_types} types)}}\\")
        overall = {(c, n): [] for c in CONDS for n in NETWORKS}

        for type_key, type_label in types:
            row_vals = []
            for net in NETWORKS:
                for cond in CONDS:
                    a = get_acc(cond, net, type_key)
                    if a is None and type_key in [t for t, _ in RETRIEVAL] and cond in ("tool_continuation", "plan_execute_revise"):
                        a = 100
                    row_vals.append(a)
                    if a is not None:
                        overall[(cond, net)].append(a)

            bolded = bold_max(row_vals, group_size=4)
            cells = " & ".join(bolded)
            lines.append(f"{type_label} & {cells} \\\\")

        lines.append(r"\cmidrule(lr){1-13}")
        section_short = section_label.split()[0]
        row_vals = []
        for net in NETWORKS:
            for cond in CONDS:
                vals = overall[(cond, net)]
                row_vals.append(f"{np.mean(vals):.1f}" if vals else "--")
        bolded_overall = []
        for i in range(0, len(row_vals), 4):
            group = row_vals[i:i + 4]
            float_group = [float(v) if v != "--" else -1 for v in group]
            group_max = max(float_group)
            for v in group:
                if v != "--" and float(v) == group_max:
                    bolded_overall.append(rf"\textbf{{{v}}}")
                else:
                    bolded_overall.append(v)
        cells = " & ".join(bolded_overall)
        lines.append(rf"\textbf{{{section_short} Overall}} & {cells} \\")

        if not is_last:
            lines.append(r"\midrule")

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}%",
        r"}",
        r"\end{table*}",
        "",
    ])
    return "\n".join(lines)


def gen_table_multifile():
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Accuracy (\%) of scaffolding conditions on multi-step reasoning questions across three SUMO networks.",
        r"Best result per row in \textbf{bold}.}",
        r"\label{tab:multifile_results}",
        r"\resizebox{0.95\textwidth}{!}{%",
        r"\begin{tabular}{l|cccc|cccc|cccc}",
        r"\toprule",
        r"\multirow{2}{*}{\textbf{Question Type}} & \multicolumn{4}{c|}{\textbf{Random}} & \multicolumn{4}{c|}{\textbf{Grid $8\times8$}} & \multicolumn{4}{c}{\textbf{Times Square}} \\",
        r"\cmidrule(lr){2-5} \cmidrule(lr){6-9} \cmidrule(lr){10-13}",
        r"  & Naive & XML & T-Cont & P-Rev & Naive & XML & T-Cont & P-Rev & Naive & XML & T-Cont & P-Rev \\",
        r"\midrule",
    ]

    overall = {(c, n): [] for c in CONDS for n in NETWORKS}
    for type_key, type_label in MULTISTEP:
        row_vals = []
        for net in NETWORKS:
            for cond in CONDS:
                a = get_acc(cond, net, type_key)
                row_vals.append(a)
                if a is not None:
                    overall[(cond, net)].append(a)
        bolded = bold_max(row_vals, group_size=4)
        cells = " & ".join(bolded)
        lines.append(f"{type_label} & {cells} \\\\")

    lines.append(r"\midrule")
    row_vals = []
    for net in NETWORKS:
        for cond in CONDS:
            vals = overall[(cond, net)]
            row_vals.append(f"{np.mean(vals):.1f}" if vals else "--")
    bolded = []
    for i in range(0, len(row_vals), 4):
        group = row_vals[i:i + 4]
        float_group = [float(v) if v != "--" else -1 for v in group]
        group_max = max(float_group)
        for v in group:
            if v != "--" and float(v) == group_max:
                bolded.append(rf"\textbf{{{v}}}")
            else:
                bolded.append(v)
    cells = " & ".join(bolded)
    lines.append(rf"\textbf{{Overall}} & {cells} \\")

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}%",
        r"}",
        r"\end{table*}",
        "",
    ])
    return "\n".join(lines)


def gen_table_category_summary():
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Category-level accuracy (\%) across scaffolding conditions and three SUMO networks.",
        r"Values show mean $\pm$ standard deviation across the 10 question types within each category.",
        r"Best result per column in \textbf{bold}.}",
        r"\label{tab:category_summary}",
        r"\resizebox{0.95\textwidth}{!}{%",
        r"\begin{tabular}{l|ccc|ccc|ccc}",
        r"\toprule",
        r"\multirow{2}{*}{\textbf{Condition}} & \multicolumn{3}{c|}{\textbf{Random}} & \multicolumn{3}{c|}{\textbf{Grid $8\times8$}} & \multicolumn{3}{c}{\textbf{Times Square}} \\",
        r"\cmidrule(lr){2-4} \cmidrule(lr){5-7} \cmidrule(lr){8-10}",
        r"  & Retrieval & Reasoning & Multi-hop & Retrieval & Reasoning & Multi-hop & Retrieval & Reasoning & Multi-hop \\",
        r"\midrule",
    ]

    cond_labels = {
        "naive": "File Descriptions",
        "xml": "Raw SUMO XML",
        "tool_continuation": "ReAct-based",
        "plan_execute_revise": "Plan-Execute-Revise",
    }

    cat_groups = [
        ("Retrieval", [t for t, _ in RETRIEVAL]),
        ("Reasoning", [t for t, _ in REASONING]),
        ("Multi-hop", [t for t, _ in MULTISTEP]),
    ]

    # Compute all values first to find column bests
    all_vals = {}
    for cond in CONDS:
        for cat_name, cat_types in cat_groups:
            for net in NETWORKS:
                vals = []
                for t in cat_types:
                    a = get_acc(cond, net, t)
                    if a is None and t in [t2 for t2, _ in RETRIEVAL] and cond in ("tool_continuation", "plan_execute_revise"):
                        a = 100
                    if a is not None:
                        vals.append(a)
                if vals:
                    m, s = np.mean(vals), np.std(vals)
                    all_vals[(cond, net, cat_name)] = (m, s)

    # Find best per column
    best = {}
    for cat_name, _ in cat_groups:
        for net in NETWORKS:
            col_vals = [(cond, all_vals.get((cond, net, cat_name), (0, 0))[0]) for cond in CONDS]
            best_m = max(v for _, v in col_vals)
            best[(net, cat_name)] = best_m

    for ci, cond in enumerate(CONDS):
        label = cond_labels[cond]
        cells = []
        for net in NETWORKS:
            for cat_name, _ in cat_groups:
                if (cond, net, cat_name) in all_vals:
                    m, s = all_vals[(cond, net, cat_name)]
                    cell = f"${m:.1f} \\pm {s:.1f}$"
                    if m == best[(net, cat_name)]:
                        cell = f"$\\mathbf{{{m:.1f} \\pm {s:.1f}}}$"
                    cells.append(cell)
                else:
                    cells.append("--")
        sep = r"\midrule" if ci == len(CONDS) - 2 else ""
        line = f"{label} & {' & '.join(cells)} \\\\"
        lines.append(line)
        if sep:
            lines.append(sep)

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}%",
        r"}",
        r"\end{table*}",
        "",
    ])
    return "\n".join(lines)


def gen_headline():
    cond_labels = {
        "naive": "Naive",
        "xml": "SUMO XML",
        "tool_continuation": "Tool Use",
        "plan_execute_revise": "Plan-Execute-Revise",
    }
    cat_groups = [
        ("Retrieval", [t for t, _ in RETRIEVAL]),
        ("Reasoning", [t for t, _ in REASONING]),
        ("Multi-step", [t for t, _ in MULTISTEP]),
    ]

    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Overall accuracy (\%) by scaffolding condition and question",
        r"category, averaged across all three networks.",
        r"Values show mean $\pm$ standard deviation across networks.",
        r"Best result per category in \textbf{bold}.}",
        r"\label{tab:headline}",
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        r"\textbf{Condition} & \textbf{Retrieval} & \textbf{Reasoning} & \textbf{Multi-step} & \textbf{Overall} \\",
        r"\midrule",
    ]

    # Compute per-network category means, then average across networks
    all_headline = {}
    for cond in CONDS:
        for cat_name, cat_types in cat_groups:
            net_means = []
            for net in NETWORKS:
                vals = []
                for t in cat_types:
                    a = get_acc(cond, net, t)
                    if a is None and t in [t2 for t2, _ in RETRIEVAL] and cond in ("tool_continuation", "plan_execute_revise"):
                        a = 100
                    if a is not None:
                        vals.append(a)
                if vals:
                    net_means.append(np.mean(vals))
            if net_means:
                all_headline[(cond, cat_name)] = (np.mean(net_means), np.std(net_means))

    # Overall = average of all 3 category means
    for cond in CONDS:
        cat_means = []
        for cat_name, _ in cat_groups:
            if (cond, cat_name) in all_headline:
                cat_means.append(all_headline[(cond, cat_name)][0])
        if cat_means:
            all_headline[(cond, "Overall")] = (np.mean(cat_means), np.std(cat_means))

    # Find best per column
    best = {}
    for cat_name in ["Retrieval", "Reasoning", "Multi-step", "Overall"]:
        vals = [all_headline.get((c, cat_name), (0, 0))[0] for c in CONDS]
        best[cat_name] = max(vals)

    for cond in CONDS:
        label = cond_labels[cond]
        cells = []
        for cat_name in ["Retrieval", "Reasoning", "Multi-step", "Overall"]:
            if (cond, cat_name) in all_headline:
                m, s = all_headline[(cond, cat_name)]
                if m == best[cat_name]:
                    cells.append(f"$\\mathbf{{{m:.1f} \\pm {s:.1f}}}$")
                else:
                    cells.append(f"${m:.1f} \\pm {s:.1f}$")
            else:
                cells.append("--")
        lines.append(f"{label:20s} & {' & '.join(cells)} \\\\")

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
        "",
    ])
    return "\n".join(lines)


def gen_table_multifile_transposed():
    n_types = len(MULTISTEP)
    cond_labels = {
        "naive": "Naive",
        "xml": "XML",
        "tool_continuation": "T-Cont",
        "plan_execute_revise": "P-Rev",
    }
    net_labels = {
        "random": "Random",
        "grid_8x8": r"Grid $8\times8$",
        "times_square": "Times Sq.",
    }
    short_type_labels = [label for _, label in MULTISTEP]

    col_spec = "ll|" + "c" * n_types + "|c"
    header_cells = " & ".join(rf"\rotatebox{{60}}{{{l}}}" for l in short_type_labels)

    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Accuracy (\%) of multi-step reasoning questions, transposed view.",
        r"Best result per column (within each network) in \textbf{bold}.}",
        r"\label{tab:multifile_transposed}",
        r"\setlength{\tabcolsep}{4pt}",
        r"\scriptsize",
        rf"\begin{{tabular}}{{@{{}}{col_spec}@{{}}}}",
        r"\toprule",
        rf"\textbf{{Network}} & \textbf{{Condition}} & {header_cells} & \rotatebox{{60}}{{Overall}} \\",
        r"\midrule",
    ]

    for ni, net in enumerate(NETWORKS):
        col_best = {}
        for ti, (type_key, _) in enumerate(MULTISTEP):
            col_vals = []
            for cond in CONDS:
                a = get_acc(cond, net, type_key)
                col_vals.append(a)
            col_best[ti] = max((v for v in col_vals if v is not None), default=None)
        overall_vals = {}
        for cond in CONDS:
            vals = [get_acc(cond, net, tk) for tk, _ in MULTISTEP]
            vals = [v for v in vals if v is not None]
            overall_vals[cond] = np.mean(vals) if vals else None
        overall_best = max((v for v in overall_vals.values() if v is not None), default=None)

        for ci, cond in enumerate(CONDS):
            net_cell = net_labels[net] if ci == 0 else ""
            cond_cell = cond_labels[cond]
            cells = []
            for ti, (type_key, _) in enumerate(MULTISTEP):
                a = get_acc(cond, net, type_key)
                if a is None:
                    cells.append("--")
                elif col_best[ti] is not None and a == col_best[ti]:
                    cells.append(rf"\textbf{{{a}}}")
                else:
                    cells.append(str(a))
            ov = overall_vals[cond]
            if ov is not None:
                ov_str = f"{ov:.1f}"
                if overall_best is not None and ov == overall_best:
                    ov_str = rf"\textbf{{{ov_str}}}"
            else:
                ov_str = "--"
            row = f"{net_cell} & {cond_cell} & {' & '.join(cells)} & {ov_str} \\\\"
            lines.append(row)
        if ni < len(NETWORKS) - 1:
            lines.append(r"\midrule")

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table*}",
        "",
    ])
    return "\n".join(lines)


def gen_table_category_overall():
    cat_groups = [
        ("Retrieval", RETRIEVAL),
        ("Reasoning", REASONING),
        ("Multi-step Reasoning", MULTISTEP),
    ]

    cond_hdr = ["File", "XML", "ReAct", "PER"]

    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Category-level and overall accuracy (\%) across scaffolding conditions and three SUMO networks.",
        r"Values show mean $\pm$ standard deviation aggregated over all individual questions within each category.",
        r"Best result per row in \textbf{bold}.}",
        r"\label{tab:category_overall}",
        r"\resizebox{0.95\textwidth}{!}{%",
        r"\begin{tabular}{l|cccc|cccc|cccc}",
        r"\toprule",
        r"\multirow{2}{*}{\textbf{Category}} & \multicolumn{4}{c|}{\textbf{Random}} & \multicolumn{4}{c|}{\textbf{Grid $8\times8$}} & \multicolumn{4}{c}{\textbf{Times Square}} \\",
        r"\cmidrule(lr){2-5} \cmidrule(lr){6-9} \cmidrule(lr){10-13}",
        r"  & " + " & ".join(cond_hdr * 3) + r" \\",
        r"\midrule",
    ]

    def _fmt(m, s, bold=False):
        if m < 0:
            return "--"
        if bold:
            return rf"$\mathbf{{{m:.1f} \pm {s:.1f}}}$"
        return rf"${m:.1f} \pm {s:.1f}$"

    all_overall = {(c, n): [] for c in CONDS for n in NETWORKS}
    cat_stats = {}
    for cat_label, cat_types in cat_groups:
        for net in NETWORKS:
            for cond in CONDS:
                vals = []       # per-type accuracies (for the mean, unchanged)
                samples = []    # per-question binary outcomes (for the std)
                for t, _ in cat_types:
                    a = get_acc(cond, net, t)
                    cl = get_correct_list(cond, net, t)
                    if a is None and t in [t2 for t2, _ in RETRIEVAL] and cond in ("tool_continuation", "plan_execute_revise"):
                        a = 100
                        cl = [100] * 5
                    if a is not None:
                        vals.append(a)
                        all_overall[(cond, net)].append(a)
                    if cl is not None:
                        samples.extend(cl)
                cat_stats[(cat_label, cond, net)] = (np.mean(vals), np.std(samples)) if vals else (-1, 0)

    for cat_label, _ in cat_groups:
        if cat_label == "Multi-step Reasoning":
            lines.append(r"\midrule")
        row = []
        for net in NETWORKS:
            group_means = {c: cat_stats[(cat_label, c, net)][0] for c in CONDS}
            gmax = max(group_means.values())
            for cond in CONDS:
                m, s = cat_stats[(cat_label, cond, net)]
                row.append(_fmt(m, s, bold=(m == gmax and m >= 0)))
        cells = " & ".join(row)
        lines.append(rf"{cat_label} & {cells} \\")

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}%",
        r"}",
        r"\end{table*}",
        "",
    ])
    return "\n".join(lines)


def gen_table_overall_by_category():
    cond_labels = ["Naive", "XML", "Tool Use", "PER"]
    cat_groups = [
        ("Retrieval", RETRIEVAL),
        ("Reasoning", REASONING),
        ("Multi-step", MULTISTEP),
    ]

    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Overall accuracy (\%) by question category across three SUMO networks.",
        r"Best result per network-category in \textbf{bold}.}",
        r"\label{tab:overall_by_category}",
        r"\setlength{\tabcolsep}{4pt}",
        r"\scriptsize",
        r"\begin{tabular}{@{}l|ccc|ccc|ccc@{}}",
        r"\toprule",
        r"\multirow{2}{*}{\textbf{Condition}}"
        r" & \multicolumn{3}{c|}{\textbf{Random}}"
        r" & \multicolumn{3}{c|}{\textbf{Grid $8\times8$}}"
        r" & \multicolumn{3}{c}{\textbf{Times Square}} \\",
        r"\cmidrule(lr){2-4} \cmidrule(lr){5-7} \cmidrule(lr){8-10}",
        r" & Ret. & Reas. & Multi & Ret. & Reas. & Multi & Ret. & Reas. & Multi \\",
        r"\midrule",
    ]

    all_vals = {}
    for ci, cond in enumerate(CONDS):
        for cat_name, cat_types in cat_groups:
            for net in NETWORKS:
                vals = []
                for t, _ in cat_types:
                    a = get_acc(cond, net, t)
                    if a is not None:
                        vals.append(a)
                if vals:
                    all_vals[(cond, net, cat_name)] = np.mean(vals)

    best = {}
    for cat_name, _ in cat_groups:
        for net in NETWORKS:
            col_vals = [all_vals.get((c, net, cat_name), 0) for c in CONDS]
            best[(net, cat_name)] = max(col_vals)

    for ci, cond in enumerate(CONDS):
        cells = []
        for net in NETWORKS:
            for cat_name, _ in cat_groups:
                v = all_vals.get((cond, net, cat_name))
                if v is None:
                    cells.append("--")
                elif v == best[(net, cat_name)]:
                    cells.append(rf"\textbf{{{v:.1f}}}")
                else:
                    cells.append(f"{v:.1f}")
        sep = r"\midrule" if ci == len(CONDS) - 2 else ""
        lines.append(f"{cond_labels[ci]} & {' & '.join(cells)} \\\\")
        if sep:
            lines.append(sep)

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
        "",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    for name, gen_fn in [
        ("table_all_results.tex", gen_table_all_results),
        ("table_multifile_results.tex", gen_table_multifile),
        ("table_category_summary.tex", gen_table_category_summary),
        ("headline_accuracy.tex", gen_headline),
        ("table_multifile_transposed.tex", gen_table_multifile_transposed),
        ("table_overall_by_category.tex", gen_table_overall_by_category),
        ("table_category_overall.tex", gen_table_category_overall),
    ]:
        content = gen_fn()
        path = TABLES / name
        path.write_text(content)
        print(f"Wrote {path}")
