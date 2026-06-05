"""
Build the preprocessed JSONL files consumed by the JSON scaffolding
condition (scripts/methods/json_view.py).

For each network and each of the four SUMO file types, this script
writes one JSONL file (one JSON record per line) to:
    data/preprocessed/<network>_<file_type>.jsonl

Conversion rules per file type:
- net.xml      Junctions and edges. Augmented with derived adjacency
               (next_edges per edge; outgoing_edges and
               neighbor_junctions per junction), loaded from
               data/network/<network>_adjacency.json.
- rou.xml      Vehicles (id, depart, type, route).
- tripinfo     Per-vehicle outcomes (depart, arrival, duration,
               route_length, depart_lane, waiting_time). Only
               arrived vehicles.
- netstate     Per-(edge, period) traffic state, six 10-minute
               windows flattened.

Source data is loaded by reusing the helpers in generate_qa.py.

Run once after the simulation outputs change. The json_view
scaffolding method reads these files at request time (no on-the-fly
conversion).

Usage:
    python scripts/build_jsonl.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

import generate_qa as gq  # noqa: E402
from utils import NETWORKS       # noqa: E402

ADJ_DIR = ROOT_DIR / "data" / "network"
OUT_DIR = ROOT_DIR / "data" / "preprocessed"
FILE_TYPES = ["net", "rou", "tripinfo", "edgedata"]
ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth"]


# ============================================================
# Helpers
# ============================================================

def _load_adjacency(network: str) -> tuple[dict[str, list[str]],
                                            dict[str, list[str]],
                                            dict[str, list[str]]]:
    """Return (junc_outgoing_edges, junc_neighbor_junctions, edge_next_edges)."""
    with open(ADJ_DIR / f"{network}_adjacency.json") as f:
        adj = json.load(f)["adjacency_list"]
    junc_outgoing = {
        j["junction_id"]: list(j.get("connected_edges", [])) for j in adj.get("junctions", [])
    }
    junc_neighbors = {
        j["junction_id"]: list(j.get("connected_nodes", [])) for j in adj.get("junctions", [])
    }
    edge_next = {
        e["edge_id"]: list(e.get("connected_edges", [])) for e in adj.get("edges", [])
    }
    return junc_outgoing, junc_neighbors, edge_next


def _round2(x):
    try:
        return round(float(x), 2)
    except (TypeError, ValueError):
        return x


# ============================================================
# Per-file-type JSONL builders
# ============================================================

def net_to_jsonl(network: str) -> str:
    n = gq.load_net(network)
    junc_out, junc_nbr, edge_next = _load_adjacency(network)

    junctions = []
    for j in n.getNodes():
        jid = j.getID()
        if jid.startswith(":"):
            continue
        x, y = j.getCoord()
        junctions.append({
            "_kind": "junction",
            "id": jid,
            "x": _round2(x),
            "y": _round2(y),
            "type": j.getType(),
            "outgoing_edges": junc_out.get(jid, []),
            "neighbor_junctions": junc_nbr.get(jid, []),
        })
    junctions.sort(key=lambda r: r["id"])

    edges = []
    for e in n.getEdges():
        eid = e.getID()
        if eid.startswith(":"):
            continue
        edges.append({
            "_kind": "edge",
            "id": eid,
            "from": e.getFromNode().getID(),
            "to": e.getToNode().getID(),
            "length": _round2(e.getLength()),
            "speed": _round2(e.getSpeed()),
            "lanes": e.getLaneNumber(),
            "type": e.getType() or "",
            "next_edges": edge_next.get(eid, []),
        })
    edges.sort(key=lambda r: r["id"])

    return "\n".join(json.dumps(r, ensure_ascii=False) for r in junctions + edges)


def rou_to_jsonl(network: str) -> str:
    rou = list(gq.load_rou(network))
    return "\n".join(
        json.dumps({
            "id": v["id"],
            "depart": _round2(v["depart"]),
            "type": v["type"],
            "route": v["route"],
        }, ensure_ascii=False)
        for v in rou
    )


def tripinfo_to_jsonl(network: str) -> str:
    ti = gq.load_tripinfo(network)
    rows = []
    for vid, info in ti.items():
        rows.append({
            "id": vid,
            "depart": _round2(info["depart"]),
            "arrival": _round2(info["arrival"]),
            "duration": _round2(info["duration"]),
            "route_length": _round2(info["routeLength"]),
            "depart_lane": info["departLane"],
            "waiting_time": _round2(info["waitingTime"]),
        })

    def sort_key(r):
        try:
            return (0, int(r["id"]))
        except ValueError:
            return (1, r["id"])

    rows.sort(key=sort_key)
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)


def edgedata_to_jsonl(network: str) -> str:
    """Flatten 6-period dict into a per-(edge, period) list, sorted."""
    ed = gq.load_edgedata(network)
    rows = []
    for eid in sorted(ed.keys()):
        for idx, p in enumerate(ed[eid]):
            rows.append({
                "edge": eid,
                "period": ORDINALS[idx],
                "sampledSeconds": _round2(p.get("sampledSeconds", 0.0)),
                "density": _round2(p.get("density", 0.0)),
                "speed": _round2(p["speed"]) if p.get("speed") is not None else None,
                "entered": int(p.get("entered", 0) or 0),
            })
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)


CONVERTERS = {
    "net": net_to_jsonl,
    "rou": rou_to_jsonl,
    "tripinfo": tripinfo_to_jsonl,
    "edgedata": edgedata_to_jsonl,
}


# ============================================================
# Build
# ============================================================

def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for network in NETWORKS:
        for ftype in FILE_TYPES:
            out_path = OUT_DIR / f"{network}_{ftype}.jsonl"
            content = CONVERTERS[ftype](network)
            out_path.write_text(content, encoding="utf-8")
            print(f"  wrote {out_path.relative_to(ROOT_DIR)}  ({len(content):,} chars)")
    print(f"\nDone. {len(NETWORKS) * len(FILE_TYPES)} files written to "
          f"{OUT_DIR.relative_to(ROOT_DIR)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
