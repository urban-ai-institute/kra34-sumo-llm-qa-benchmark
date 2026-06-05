#!/usr/bin/env python3
"""Compute API cost per completed question from the usage_*.csv sidecars
written by run_experiment.py (TRACK_USAGE=1).

Usage: python3 compute_cost.py <results-subdir> [--condition plan_execute_revise]

Prices are per 1M tokens (USD). Defaults are GPT-5.4 (2026-06).
"""
import argparse
import csv
import glob
import os

# Pricing per 1M tokens (USD), keyed by results subdir.
# input / cached (cache read) / cache_write / output
PRICES = {
    "gpt-5.4": {"input": 2.50, "cached_input": 0.25, "cache_write": 2.50, "output": 15.00},
    "claude-haiku-4-5": {"input": 1.00, "cached_input": 0.10, "cache_write": 1.25, "output": 5.00},
}
RESULTS = "QAdataset/results"


def cost(p, inp, cached, cwrite, out):
    return (inp * p["input"] + cached * p["cached_input"]
            + cwrite * p["cache_write"] + out * p["output"]) / 1_000_000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("subdir")
    ap.add_argument("--condition", default="plan_execute_revise")
    args = ap.parse_args()

    p = PRICES.get(args.subdir)
    if p is None:
        raise SystemExit(f"No pricing for subdir '{args.subdir}'. Known: {list(PRICES)}")

    d = os.path.join(RESULTS, args.subdir)
    files = sorted(glob.glob(os.path.join(d, f"usage_{args.condition}_*.csv")))
    rows = []
    for f in files:
        with open(f, newline="") as fh:
            for r in csv.DictReader(fh):
                r = {k: r[k] for k in r}
                for k in ("input_tokens", "cached_input_tokens", "cache_write_tokens",
                          "output_tokens", "api_calls"):
                    r[k] = int(r.get(k) or 0)
                r["seconds"] = float(r["seconds"] or 0)
                r["cost"] = cost(p, r["input_tokens"], r["cached_input_tokens"],
                                 r["cache_write_tokens"], r["output_tokens"])
                rows.append(r)

    if not rows:
        print(f"No usage files found in {d}")
        return

    n = len(rows)
    tin = sum(r["input_tokens"] for r in rows)
    tcached = sum(r["cached_input_tokens"] for r in rows)
    tcwrite = sum(r["cache_write_tokens"] for r in rows)
    tout = sum(r["output_tokens"] for r in rows)
    tcalls = sum(r["api_calls"] for r in rows)
    tcost = sum(r["cost"] for r in rows)
    tsec = sum(r["seconds"] for r in rows)

    print(f"Model (subdir)      : {args.subdir}")
    print(f"Questions completed : {n}")
    print(f"Prices (per 1M tok) : input ${p['input']} | cache-read ${p['cached_input']} "
          f"| cache-write ${p['cache_write']} | output ${p['output']}")
    print()
    print(f"{'Metric':<22}{'Total':>16}{'Per question (avg)':>22}")
    print("-" * 60)
    print(f"{'Uncached input tok':<22}{tin:>16,}{tin/n:>22,.0f}")
    print(f"{'Cache-read tok':<22}{tcached:>16,}{tcached/n:>22,.0f}")
    print(f"{'Cache-write tok':<22}{tcwrite:>16,}{tcwrite/n:>22,.0f}")
    print(f"{'Output tok':<22}{tout:>16,}{tout/n:>22,.0f}")
    print(f"{'API calls':<22}{tcalls:>16,}{tcalls/n:>22,.1f}")
    print(f"{'Wall seconds':<22}{tsec:>16,.0f}{tsec/n:>22,.1f}")
    print(f"{'Cost (USD)':<22}{tcost:>16,.4f}{tcost/n:>22,.4f}")
    print()

    # Per-network breakdown
    print(f"{'Network':<16}{'n':>5}{'avg cost':>12}{'avg out tok':>14}{'avg calls':>11}")
    print("-" * 58)
    nets = {}
    for r in rows:
        nets.setdefault(r["network"], []).append(r)
    for net, rs in sorted(nets.items()):
        m = len(rs)
        print(f"{net:<16}{m:>5}{sum(x['cost'] for x in rs)/m:>12.4f}"
              f"{sum(x['output_tokens'] for x in rs)/m:>14,.0f}"
              f"{sum(x['api_calls'] for x in rs)/m:>11.1f}")

    # Most/least expensive question
    rows.sort(key=lambda r: r["cost"])
    cheap, exp = rows[0], rows[-1]
    print()
    print(f"Cheapest  Q: ${cheap['cost']:.4f}  ({cheap['network']}/{cheap['type']} #{cheap['sample_id']})")
    print(f"Priciest  Q: ${exp['cost']:.4f}  ({exp['network']}/{exp['type']} #{exp['sample_id']})")


if __name__ == "__main__":
    main()
