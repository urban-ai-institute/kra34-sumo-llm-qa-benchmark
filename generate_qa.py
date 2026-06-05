#!/usr/bin/env python3
"""
NetTrafficQA — single-file generator for 32 question types.

Reads:
  data/network/<net>.net.xml
  data/network/<net>_tls.add.xml
  data/trips/<net>.rou.xml
  data/output/<net>_tripinfo.xml
  data/output/<net>_fcd.xml

Writes:
  QAdataset/questions/<net>_<type>.csv  (5 rows each)

CSV schema:
  network,type,sample_id,question,ground_truth,files_used

Determinism: a fixed Random(SEED) per (network, type) pair.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any

import sumolib

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
NETWORK_DIR = DATA_DIR / "network"
TRIPS_DIR = DATA_DIR / "trips"
OUTPUT_DIR = DATA_DIR / "output"
QA_DIR = ROOT_DIR / "QAdataset" / "questions"

NETWORKS = ["grid_8x8", "random", "random_large", "times_square"]
SAMPLES_PER_TYPE = 5
SEED = 42

NUM_PERIODS = 6
PERIOD_SECONDS = 600
SIM_END = 3600
ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth"]


# ===================== File path helpers =====================

def net_path(net: str) -> Path:
    return NETWORK_DIR / f"{net}.net.xml"


def rou_path(net: str) -> Path:
    return TRIPS_DIR / f"{net}.rou.xml"


def tripinfo_path(net: str) -> Path:
    return OUTPUT_DIR / f"{net}_tripinfo.xml"


# ===================== Loaders =====================

_net_cache: dict[str, Any] = {}
_rou_cache: dict[str, list] = {}
_tripinfo_cache: dict[str, dict] = {}
_tls_cache: dict[str, list] = {}


def load_net(net: str):
    if net not in _net_cache:
        _net_cache[net] = sumolib.net.readNet(str(net_path(net)))
    return _net_cache[net]


def load_rou(net: str) -> list[dict]:
    """Return list of {id, depart, type, route: [edge_ids]} for each vehicle."""
    if net in _rou_cache:
        return _rou_cache[net]
    out = []
    root = ET.parse(str(rou_path(net))).getroot()
    for v in root.iter("vehicle"):
        vid = v.get("id")
        depart = float(v.get("depart", "0"))
        vtype = v.get("type", "")
        route_el = v.find("route")
        edges = route_el.get("edges").split() if route_el is not None else []
        out.append({"id": vid, "depart": depart, "type": vtype, "route": edges})
    _rou_cache[net] = out
    return out


def load_tripinfo(net: str) -> dict[str, dict]:
    """Return {vehicle_id: {arrival, duration, routeLength, departLane, ...}}."""
    if net in _tripinfo_cache:
        return _tripinfo_cache[net]
    out: dict[str, dict] = {}
    p = tripinfo_path(net)
    if not p.exists():
        _tripinfo_cache[net] = out
        return out
    for ti in ET.parse(str(p)).getroot().iter("tripinfo"):
        vid = ti.get("id")
        out[vid] = {
            "depart": float(ti.get("depart", "nan")),
            "arrival": float(ti.get("arrival", "nan")),
            "duration": float(ti.get("duration", "nan")),
            "routeLength": float(ti.get("routeLength", "nan")),
            "departLane": ti.get("departLane", ""),
            "waitingTime": float(ti.get("waitingTime", "nan")),
            "timeLoss": float(ti.get("timeLoss", "nan")),
        }
    _tripinfo_cache[net] = out
    return out


def load_tls(net: str) -> list[dict]:
    """Return list of {id, phases: [{duration, state}]} for each tlLogic."""
    if net in _tls_cache:
        return _tls_cache[net]
    p = tls_add_path(net)
    if not p.exists():
        _tls_cache[net] = []
        return []
    out = []
    root = ET.parse(str(p)).getroot()
    for tl in root.iter("tlLogic"):
        phases = []
        for ph in tl.findall("phase"):
            phases.append({
                "duration": int(float(ph.get("duration", "0"))),
                "state": ph.get("state", ""),
            })
        out.append({"id": tl.get("id"), "phases": phases})
    _tls_cache[net] = out
    return out


# ===================== Seed-variant loaders =====================

_rou_s_cache: dict[str, list] = {}
_tripinfo_s_cache: dict[str, dict] = {}


def fcd_path(net: str) -> Path:
    return OUTPUT_DIR / f"{net}_fcd.xml"


def fcd_path_s(net: str, seed_idx: int) -> Path:
    return OUTPUT_DIR / f"{net}_s{seed_idx}_fcd.xml"


def tls_add_path(net: str) -> Path:
    return NETWORK_DIR / f"{net}_tls.add.xml"


def rou_path_s(net: str, seed_idx: int) -> Path:
    return TRIPS_DIR / f"{net}_s{seed_idx}.rou.xml"


def tripinfo_path_s(net: str, seed_idx: int) -> Path:
    return OUTPUT_DIR / f"{net}_s{seed_idx}_tripinfo.xml"


def load_rou_s(net: str, seed_idx: int) -> list[dict]:
    key = f"{net}_s{seed_idx}"
    if key in _rou_s_cache:
        return _rou_s_cache[key]
    out = []
    root = ET.parse(str(rou_path_s(net, seed_idx))).getroot()
    for v in root.iter("vehicle"):
        route_el = v.find("route")
        edges = route_el.get("edges").split() if route_el is not None else []
        out.append({
            "id": v.get("id"),
            "depart": float(v.get("depart", "0")),
            "type": v.get("type", ""),
            "route": edges,
        })
    _rou_s_cache[key] = out
    return out


def load_tripinfo_s(net: str, seed_idx: int) -> dict[str, dict]:
    key = f"{net}_s{seed_idx}"
    if key in _tripinfo_s_cache:
        return _tripinfo_s_cache[key]
    out: dict[str, dict] = {}
    p = tripinfo_path_s(net, seed_idx)
    if not p.exists():
        _tripinfo_s_cache[key] = out
        return out
    for ti in ET.parse(str(p)).getroot().iter("tripinfo"):
        vid = ti.get("id")
        out[vid] = {
            "depart": float(ti.get("depart", "nan")),
            "arrival": float(ti.get("arrival", "nan")),
            "duration": float(ti.get("duration", "nan")),
            "routeLength": float(ti.get("routeLength", "nan")),
            "departLane": ti.get("departLane", ""),
            "waitingTime": float(ti.get("waitingTime", "nan")),
        }
    _tripinfo_s_cache[key] = out
    return out


# ===================== FCD streaming loader =====================

def iter_fcd_timesteps(fcd_file: Path):
    """Yield (time, lane_vehicles) per timestep via iterparse.

    lane_vehicles: dict mapping lane_id -> list of (vid, pos, speed) tuples.
    Internal lanes (starting with ':') are excluded.
    Memory: O(vehicles_per_timestep).
    """
    lane_vehicles: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    current_time = 0.0
    for event, elem in ET.iterparse(str(fcd_file), events=("start", "end")):
        if event == "start" and elem.tag == "timestep":
            current_time = float(elem.get("time", "0"))
            lane_vehicles = defaultdict(list)
        elif event == "end" and elem.tag == "vehicle":
            lane = elem.get("lane", "")
            if not lane.startswith(":"):
                lane_vehicles[lane].append((
                    elem.get("id"),
                    float(elem.get("pos", "0")),
                    float(elem.get("speed", "0")),
                ))
            elem.clear()
        elif event == "end" and elem.tag == "timestep":
            yield current_time, lane_vehicles
            elem.clear()


def load_tls_controlled_edges(net_str: str) -> dict[str, set[str]]:
    """Return {tls_id: set_of_incoming_edge_ids} using sumolib."""
    n = load_net(net_str)
    result: dict[str, set[str]] = {}
    for tls in n.getTrafficLights():
        edges: set[str] = set()
        for conn in tls.getConnections():
            edges.add(conn[0].getEdge().getID())
        result[tls.getID()] = edges
    return result


# ===================== Sampling helpers =====================

def sample_edges(net_obj, n: int, rng: random.Random) -> list:
    edges = [e for e in net_obj.getEdges() if not e.getID().startswith(":")]
    return rng.sample(edges, min(n, len(edges)))


def sample_junctions(net_obj, n: int, rng: random.Random) -> list:
    juncs = [j for j in net_obj.getNodes() if not j.getID().startswith(":")]
    return rng.sample(juncs, min(n, len(juncs)))


def sample_vehicles(net: str, n: int, rng: random.Random) -> list[dict]:
    rou = load_rou(net)
    return rng.sample(rou, min(n, len(rou)))


def sample_junction_pair(net_obj, rng: random.Random):
    """Return a pair (A, B) of distinct junctions."""
    juncs = [j for j in net_obj.getNodes() if not j.getID().startswith(":")]
    a, b = rng.sample(juncs, 2)
    return a, b


def sample_window(rng: random.Random) -> tuple[int, int]:
    """Return a random (start, end) window of length 600s within [0, 3600]."""
    start = rng.randint(0, SIM_END - PERIOD_SECONDS)
    return start, start + PERIOD_SECONDS


# ===================== Graph helpers =====================

def edge_graph(net_obj) -> tuple[dict, dict]:
    """Return (junction_outgoing, edge_lookup).

    junction_outgoing: {junction_id: [(neighbor_junction_id, edge_id, length)]}
    edge_lookup: {edge_id: {from, to, length}}
    """
    out: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
    edges: dict[str, dict] = {}
    for e in net_obj.getEdges():
        eid = e.getID()
        if eid.startswith(":"):
            continue
        frm = e.getFromNode().getID()
        to = e.getToNode().getID()
        length = e.getLength()
        out[frm].append((to, eid, length))
        edges[eid] = {"from": frm, "to": to, "length": length}
    return dict(out), edges


def dijkstra(adj: dict, edges: dict, src: str, dst: str,
             excluded_edge: str | None = None) -> tuple[list[str] | None, list[str] | None, float]:
    """Return (junction_path, edge_path, total_length) from src to dst.

    Returns (None, None, inf) if no path.
    """
    import heapq
    dist = {src: 0.0}
    prev: dict[str, tuple[str, str]] = {}  # node -> (prev_node, edge_id_used)
    pq: list[tuple[float, str]] = [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == dst:
            break
        if d > dist.get(u, float("inf")):
            continue
        for v, eid, length in adj.get(u, []):
            if eid == excluded_edge:
                continue
            nd = d + length
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = (u, eid)
                heapq.heappush(pq, (nd, v))
    if dst not in dist:
        return None, None, float("inf")
    junctions = [dst]
    edge_seq: list[str] = []
    cur = dst
    while cur in prev:
        pu, peid = prev[cur]
        junctions.append(pu)
        edge_seq.append(peid)
        cur = pu
    junctions.reverse()
    edge_seq.reverse()
    return junctions, edge_seq, dist[dst]


def bfs_reachable(adj: dict, src: str, excluded_edge: str | None = None) -> set[str]:
    """Set of junctions reachable from src (directed)."""
    seen = {src}
    stack = [src]
    while stack:
        u = stack.pop()
        for v, eid, _ in adj.get(u, []):
            if eid == excluded_edge:
                continue
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return seen


def is_strongly_connected(adj: dict, nodes: list[str],
                          removed_node: str | None = None,
                          removed_edges: set[str] | None = None) -> bool:
    """Check strong connectivity over `nodes` (excluding removed)."""
    removed_edges = removed_edges or set()
    active = [n for n in nodes if n != removed_node]
    if not active:
        return True
    src = active[0]
    # Forward
    fwd = {src}
    stack = [src]
    while stack:
        u = stack.pop()
        for v, eid, _ in adj.get(u, []):
            if v == removed_node or eid in removed_edges:
                continue
            if v not in fwd:
                fwd.add(v)
                stack.append(v)
    if not all(n in fwd for n in active):
        return False
    # Backward — build reverse adj on the fly (small graphs OK).
    rev: dict[str, list] = defaultdict(list)
    for u, neighbors in adj.items():
        if u == removed_node:
            continue
        for v, eid, length in neighbors:
            if v == removed_node or eid in removed_edges:
                continue
            rev[v].append((u, eid, length))
    bwd = {src}
    stack = [src]
    while stack:
        u = stack.pop()
        for v, eid, _ in rev.get(u, []):
            if v not in bwd:
                bwd.add(v)
                stack.append(v)
    return all(n in bwd for n in active)


# ===================== Network generators (8) =====================

def gen_both_junctions(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|both_junctions")
    n = load_net(net)
    rows = []
    for e in sample_edges(n, SAMPLES_PER_TYPE, rng):
        eid = e.getID()
        frm = e.getFromNode().getID()
        to = e.getToNode().getID()
        rows.append({
            "question": f"What are the from-junction and to-junction ids of edge {eid}? Answer format: <from_junction>, <to_junction>",
            "ground_truth": f"{frm}, {to}",
        })
    return rows


def gen_num_lanes(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|num_lanes")
    n = load_net(net)
    rows = []
    for e in sample_edges(n, SAMPLES_PER_TYPE, rng):
        rows.append({
            "question": f"How many lanes does edge {e.getID()} have? Answer format: <integer>",
            "ground_truth": str(e.getLaneNumber()),
        })
    return rows


def gen_junction_coord(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|junction_coord")
    n = load_net(net)
    rows = []
    for j in sample_junctions(n, SAMPLES_PER_TYPE, rng):
        x, y = j.getCoord()
        rows.append({
            "question": f"What are the (x, y) coordinates of junction {j.getID()}? Answer format: <x>, <y>",
            "ground_truth": f"{round(x, 2)}, {round(y, 2)}",
        })
    return rows


def gen_shortest_path_full(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|shortest_path_full")
    n = load_net(net)
    adj, edges = edge_graph(n)
    rows = []
    for _ in range(SAMPLES_PER_TYPE):
        a, b = sample_junction_pair(n, rng)
        junctions, edge_seq, _ = dijkstra(adj, edges, a.getID(), b.getID())
        if junctions is None:
            gt = "None"
        else:
            parts = [junctions[0]]
            for jct, ed in zip(junctions[1:], edge_seq):
                parts.append(ed)
                parts.append(jct)
            gt = " -> ".join(parts)
        rows.append({
            "question": f"What is the shortest path from junction {a.getID()} to junction {b.getID()}? List the junctions and edges in alternating order. Answer format: <J1> -> <e1> -> <J2> -> <e2> -> ..., or 'None' if no path exists",
            "ground_truth": gt,
        })
    return rows


def gen_shortest_path_edge_removal(net: str) -> list[dict]:
    """Sample (A,B) such that a path exists, then remove one edge ON that
    path. This guarantees the removed edge actually affects the original
    shortest path (no fallback / no trivial samples).
    """
    rng = random.Random(f"{SEED}|{net}|shortest_path_edge_removal")
    n = load_net(net)
    adj, edges = edge_graph(n)
    rows = []
    attempts = 0
    max_attempts = SAMPLES_PER_TYPE * 50
    while len(rows) < SAMPLES_PER_TYPE and attempts < max_attempts:
        attempts += 1
        a, b = sample_junction_pair(n, rng)
        _, edge_seq, _ = dijkstra(adj, edges, a.getID(), b.getID())
        if edge_seq is None or len(edge_seq) == 0:
            continue
        # Pick one edge that lies ON the original shortest path.
        e = rng.choice(edge_seq)
        _, edge_seq2, _ = dijkstra(adj, edges, a.getID(), b.getID(), excluded_edge=e)
        gt = "None" if edge_seq2 is None else " -> ".join(edge_seq2)
        rows.append({
            "question": f"If edge {e} is removed, what is the shortest path from junction {a.getID()} to junction {b.getID()}? Answer format: <e1> -> <e2> -> ..., or 'None' if no path exists after removal",
            "ground_truth": gt,
        })
    if len(rows) < SAMPLES_PER_TYPE:
        # Should not happen for our networks, but be explicit if it does.
        raise RuntimeError(
            f"shortest_path_edge_removal: could not find {SAMPLES_PER_TYPE} valid "
            f"(A,B,E) triples in {max_attempts} attempts for network {net!r}"
        )
    return rows


def gen_node_removal_connectivity(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|node_removal_connectivity")
    n = load_net(net)
    adj, edges = edge_graph(n)
    junction_ids = [j.getID() for j in n.getNodes() if not j.getID().startswith(":")]
    # Find edges touching each junction
    touching: dict[str, set[str]] = defaultdict(set)
    for eid, info in edges.items():
        touching[info["from"]].add(eid)
        touching[info["to"]].add(eid)
    rows = []
    for j in sample_junctions(n, SAMPLES_PER_TYPE, rng):
        jid = j.getID()
        connected = is_strongly_connected(
            adj, junction_ids,
            removed_node=jid,
            removed_edges=touching[jid],
        )
        rows.append({
            "question": f"If junction {jid} is removed (along with all its incident edges), does the resulting network remain strongly connected? Answer format: yes or no",
            "ground_truth": "yes" if connected else "no",
        })
    return rows


# ===================== Demand generators (6) =====================

def gen_vehicle_depart_edge(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|vehicle_depart_edge")
    rows = []
    for v in sample_vehicles(net, SAMPLES_PER_TYPE, rng):
        if not v["route"]:
            continue
        rows.append({
            "question": f"What is the departure edge of vehicle {v['id']}? "
                        f"Answer format: <edge_id>",
            "ground_truth": v["route"][0],
        })
    return rows


def gen_vehicle_depart_time(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|vehicle_depart_time")
    rows = []
    for v in sample_vehicles(net, SAMPLES_PER_TYPE, rng):
        rows.append({
            "question": f"At what time (in seconds) does vehicle {v['id']} depart? Answer format: <number> rounded to 2 decimal places",
            "ground_truth": f"{v['depart']:.2f}",
        })
    return rows


def gen_vehicle_route(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|vehicle_route")
    rows = []
    for v in sample_vehicles(net, SAMPLES_PER_TYPE, rng):
        rows.append({
            "question": f"List the planned route of vehicle {v['id']} as an ordered edge sequence. Answer format: <e1> -> <e2> -> ...",
            "ground_truth": " -> ".join(v["route"]),
        })
    return rows


def gen_vehicles_passing_edge(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|vehicles_passing_edge")
    n = load_net(net)
    rou = load_rou(net)
    rows = []
    for e in sample_edges(n, SAMPLES_PER_TYPE, rng):
        eid = e.getID()
        count = sum(1 for v in rou if eid in v["route"])
        rows.append({
            "question": f"How many vehicles include edge {eid} in their planned route? Answer format: <integer>",
            "ground_truth": str(count),
        })
    return rows


def gen_vehicles_with_same_origin(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|vehicles_with_same_origin")
    rou = load_rou(net)
    rows = []
    for v in sample_vehicles(net, SAMPLES_PER_TYPE, rng):
        if not v["route"]:
            count = 0
        else:
            origin = v["route"][0]
            count = sum(1 for u in rou
                        if u["id"] != v["id"] and u["route"] and u["route"][0] == origin)
        rows.append({
            "question": f"How many other vehicles depart from the same edge as vehicle {v['id']} (i.e., share V's origin edge)? Answer format: <integer>",
            "ground_truth": str(count),
        })
    return rows


def gen_avg_route_length_in_window(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|avg_route_length_in_window")
    rou = load_rou(net)
    rows = []
    for _ in range(SAMPLES_PER_TYPE):
        t_start, t_end = sample_window(rng)
        in_window = [v for v in rou if t_start <= v["depart"] < t_end]
        if not in_window:
            gt = "None"
        else:
            avg = sum(len(v["route"]) for v in in_window) / len(in_window)
            gt = f"{avg:.2f}"
        rows.append({
            "question": f"For vehicles departing between time {t_start} and time {t_end} (in seconds), what is the average number of edges in their planned routes? Answer format: <number> rounded to 2 decimal places, or 'None' if no vehicles depart in this window",
            "ground_truth": gt,
        })
    return rows


# ===================== Retrieval — tripinfo =====================

def gen_vehicle_travel_time(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|vehicle_travel_time")
    ti = load_tripinfo(net)
    rows = []
    for v in sample_vehicles(net, SAMPLES_PER_TYPE, rng):
        info = ti.get(v["id"])
        gt = "None" if info is None else f"{info['duration']:.2f}"
        rows.append({
            "question": f"What was the total travel time (in seconds) of vehicle {v['id']}? Answer format: <number> rounded to 2 decimal places, or 'None' if {v['id']} did not arrive within the simulation",
            "ground_truth": gt,
        })
    return rows


def gen_vehicle_arrival_time(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|vehicle_arrival_time")
    ti = load_tripinfo(net)
    rows = []
    for v in sample_vehicles(net, SAMPLES_PER_TYPE, rng):
        info = ti.get(v["id"])
        gt = "None" if info is None else f"{info['arrival']:.2f}"
        rows.append({
            "question": f"At what simulation time (in seconds) did vehicle {v['id']} arrive at its destination? Answer format: <number> rounded to 2 decimal places, or 'None' if {v['id']} did not arrive within the simulation",
            "ground_truth": gt,
        })
    return rows


# ===================== Multi-step reasoning generators =====================

def gen_edge_removal_route_count(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|edge_removal_route_count")
    n = load_net(net)
    rou = load_rou(net)
    rows = []
    for e in sample_edges(n, SAMPLES_PER_TYPE, rng):
        eid = e.getID()
        count = sum(1 for v in rou if eid in v["route"])
        rows.append({
            "question": f"If edge {eid} is removed, how many vehicles' planned routes become invalid (i.e., contain {eid})? Answer format: <integer>",
            "ground_truth": str(count),
        })
    return rows


def gen_vehicle_route_distance_meters(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|vehicle_route_distance_meters")
    n = load_net(net)
    rows = []
    for v in sample_vehicles(net, SAMPLES_PER_TYPE, rng):
        total = 0.0
        for eid in v["route"]:
            edge_obj = n.getEdge(eid) if eid in {e.getID() for e in n.getEdges()} else None
            # Robust path:
            try:
                edge_obj = n.getEdge(eid)
            except KeyError:
                edge_obj = None
            if edge_obj is not None:
                total += edge_obj.getLength()
        rows.append({
            "question": f"What is the total length (in meters) of vehicle {v['id']}'s planned route? Answer format: <number> rounded to 2 decimal places",
            "ground_truth": f"{total:.2f}",
        })
    return rows


def gen_worst_congestion_od(net: str) -> list[dict]:
    n = load_net(net)
    edge_ids = {e.getID() for e in n.getEdges()}
    rows = []
    for i in range(SAMPLES_PER_TYPE):
        rou = load_rou_s(net, i)
        ti = load_tripinfo_s(net, i)

        od_ratios: dict[tuple[str, str], list[float]] = defaultdict(list)
        for v in rou:
            info = ti.get(v["id"])
            if info is None or not v["route"]:
                continue
            origin = v["route"][0]
            dest = v["route"][-1]
            free_flow = 0.0
            for eid in v["route"]:
                if eid in edge_ids:
                    edge = n.getEdge(eid)
                    free_flow += edge.getLength() / edge.getSpeed()
            if free_flow > 0:
                ratio = info["duration"] / free_flow
                od_ratios[(origin, dest)].append(ratio)

        worst_od = max(od_ratios, key=lambda k: sum(od_ratios[k]) / len(od_ratios[k]))
        gt = f"{worst_od[0]}, {worst_od[1]}"
        rows.append({
            "question": "Which origin-destination edge pair has the worst congestion ratio "
                        "(actual travel time / free-flow travel time) averaged across all "
                        "vehicles sharing that OD pair? "
                        "Answer format: <origin_edge>, <destination_edge>",
            "ground_truth": gt,
            "files_used": f"net,rou_s{i},tripinfo_s{i}",
        })
    return rows


def gen_gap_violations(net: str) -> list[dict]:
    VEH_LENGTH = 5.0
    TAU = 1.0
    rows = []
    for i in range(SAMPLES_PER_TYPE):
        violations: dict[str, int] = defaultdict(int)
        for _time, lane_vehicles in iter_fcd_timesteps(fcd_path_s(net, i)):
            for lane, vehs in lane_vehicles.items():
                if len(vehs) < 2:
                    continue
                vehs_sorted = sorted(vehs, key=lambda x: x[1])
                edge = lane.rsplit("_", 1)[0]
                for j in range(1, len(vehs_sorted)):
                    gap = vehs_sorted[j][1] - vehs_sorted[j - 1][1] - VEH_LENGTH
                    safe = vehs_sorted[j - 1][2] * TAU
                    if gap < safe:
                        violations[edge] += 1
        if not violations:
            continue
        worst = max(violations, key=violations.get)
        rows.append({
            "question": "Which edge has the most inter-vehicle gap violations? "
                        "For each pair of consecutive vehicles on the same lane "
                        "(sorted by position), compute: "
                        "gap = leader_pos - follower_pos - 5.0 (vehicle length). "
                        "A violation occurs when gap < follower_speed * 1.0 "
                        "(1-second rule). "
                        "Count total violations per edge across all timesteps. "
                        "Answer format: <edge_id>",
            "ground_truth": worst,
            "files_used": f"net,rou_s{i},fcd_s{i}",
        })
    return rows


def gen_tls_delay(net: str) -> list[dict]:
    tls_edges = load_tls_controlled_edges(net)
    if not tls_edges:
        return []
    n = load_net(net)
    approach_set = set()
    for edges in tls_edges.values():
        approach_set.update(edges)
    edge_freeflow: dict[str, float] = {}
    for eid in approach_set:
        e = n.getEdge(eid)
        edge_freeflow[eid] = e.getLength() / e.getSpeed()

    rows = []
    for i in range(SAMPLES_PER_TYPE):
        traversals: dict[tuple[str, str], dict] = {}
        for time, lane_vehicles in iter_fcd_timesteps(fcd_path_s(net, i)):
            for lane, vehs in lane_vehicles.items():
                edge = lane.rsplit("_", 1)[0]
                if edge not in approach_set:
                    continue
                for vid, pos, speed in vehs:
                    key = (vid, edge)
                    if key not in traversals:
                        traversals[key] = {"enter": time, "exit": time}
                    else:
                        traversals[key]["exit"] = time

        tls_ratios: dict[str, list[float]] = defaultdict(list)
        for (vid, edge), times in traversals.items():
            actual = times["exit"] - times["enter"]
            ff = edge_freeflow.get(edge, 0)
            if ff <= 0 or actual <= 0:
                continue
            ratio = actual / ff
            for tls_id, edges in tls_edges.items():
                if edge in edges:
                    tls_ratios[tls_id].append(ratio)

        if not tls_ratios:
            continue
        worst_tls = max(tls_ratios,
                        key=lambda k: sum(tls_ratios[k]) / len(tls_ratios[k]))
        rows.append({
            "question": "Which traffic signal has the highest mean actual/free-flow "
                        "traversal time ratio on its incoming edges? "
                        "For each vehicle-edge traversal on a TLS incoming edge, "
                        "compute ratio = (last_seen_time - first_seen_time) / "
                        "(edge_length / edge_speed_limit). "
                        "Skip traversals with actual <= 0. "
                        "Average all ratios per TLS and find the worst. "
                        "Answer format: <tls_id>",
            "ground_truth": worst_tls,
            "files_used": f"net,add,fcd_s{i}",
        })
    return rows


def gen_peak_offpeak_degradation(net: str) -> list[dict]:
    BIN_SIZE = 300
    rows = []
    for i in range(SAMPLES_PER_TYPE):
        ti = load_tripinfo_s(net, i)
        rou = load_rou_s(net, i)
        bins: dict[int, int] = defaultdict(int)
        for v in rou:
            info = ti.get(v["id"])
            if info is None:
                continue
            b = int(v["depart"]) // BIN_SIZE
            bins[b] += 1
        if not bins:
            continue
        peak_bin = max(bins, key=bins.get)

        origin_durations: dict[str, list[tuple[float, bool]]] = defaultdict(list)
        for v in rou:
            info = ti.get(v["id"])
            if info is None or not v["route"]:
                continue
            origin = v["route"][0]
            in_peak = (int(v["depart"]) // BIN_SIZE) == peak_bin
            origin_durations[origin].append((info["duration"], in_peak))

        best_origin = None
        best_deg = -1.0
        for origin, entries in origin_durations.items():
            peak_durs = [d for d, ip in entries if ip]
            offpeak_durs = [d for d, ip in entries if not ip]
            if not peak_durs or not offpeak_durs:
                continue
            deg = (sum(peak_durs) / len(peak_durs)) / (sum(offpeak_durs) / len(offpeak_durs))
            if deg > best_deg:
                best_deg = deg
                best_origin = origin

        if best_origin is None:
            continue
        rows.append({
            "question": "Which origin edge has the worst peak vs. off-peak travel time "
                        "degradation ratio? "
                        "Divide the simulation into fixed 300-second bins starting at 0. "
                        "The peak bin is the one with the most vehicle departures "
                        "(use int(depart_time) // 300). "
                        "For each origin edge, compute degradation = "
                        "mean_peak_duration / mean_offpeak_duration. "
                        "Skip origins without both peak and off-peak vehicles. "
                        "Answer format: <edge_id>",
            "ground_truth": best_origin,
            "files_used": f"rou_s{i},tripinfo_s{i}",
        })
    return rows


def gen_lane_utilisation(net: str) -> list[dict]:
    n = load_net(net)
    multilane_edges: dict[str, list[str]] = {}
    for e in n.getEdges():
        eid = e.getID()
        if eid.startswith(":"):
            continue
        lanes = e.getLanes()
        if len(lanes) >= 2:
            multilane_edges[eid] = [l.getID() for l in lanes]

    if not multilane_edges:
        return []

    rows = []
    for i in range(SAMPLES_PER_TYPE):
        lane_counts: dict[str, int] = defaultdict(int)
        for _time, lane_vehicles in iter_fcd_timesteps(fcd_path_s(net, i)):
            for lane, vehs in lane_vehicles.items():
                lane_counts[lane] += len(vehs)

        best_edge = None
        best_cv = -1.0
        for eid, lane_ids in multilane_edges.items():
            counts = [lane_counts.get(lid, 0) for lid in lane_ids]
            mean_c = sum(counts) / len(counts)
            if mean_c == 0:
                continue
            std_c = (sum((c - mean_c) ** 2 for c in counts) / len(counts)) ** 0.5
            cv = round(std_c / mean_c, 6)
            if cv > best_cv or (cv == best_cv and sum(counts) > sum(
                    lane_counts.get(lid, 0) for lid in multilane_edges.get(best_edge, []))):
                best_cv = cv
                best_edge = eid

        if best_edge is None:
            continue
        rows.append({
            "question": "Which multi-lane edge has the most unequal lane utilisation "
                        "(highest coefficient of variation across lanes) "
                        "across the simulation? "
                        "Answer format: <edge_id>",
            "ground_truth": best_edge,
            "files_used": f"net,fcd_s{i}",
        })
    return rows


def gen_incomplete_od(net: str) -> list[dict]:
    rows = []
    for i in range(SAMPLES_PER_TYPE):
        rou = load_rou_s(net, i)
        ti = load_tripinfo_s(net, i)
        od_incomplete: dict[tuple[str, str], int] = defaultdict(int)
        for v in rou:
            if not v["route"]:
                continue
            origin = v["route"][0]
            dest = v["route"][-1]
            info = ti.get(v["id"])
            if info is None or info["arrival"] < 0:
                od_incomplete[(origin, dest)] += 1

        if not od_incomplete:
            continue
        worst = max(od_incomplete, key=od_incomplete.get)
        gt = f"{worst[0]}, {worst[1]}"
        rows.append({
            "question": "Which OD pair has the most vehicles that depart but never arrive? "
                        "Answer format: <origin_edge>, <destination_edge>",
            "ground_truth": gt,
            "files_used": f"rou_s{i},tripinfo_s{i}",
        })
    return rows


def _build_junction_incoming(net_str: str):
    """Return junction_incoming: {jid: {edge_id: edge_length}} for non-internal junctions."""
    n = load_net(net_str)
    junction_incoming: dict[str, dict[str, float]] = {}
    for node in n.getNodes():
        jid = node.getID()
        if jid.startswith(":"):
            continue
        incoming: dict[str, float] = {}
        for e in node.getIncoming():
            eid = e.getID()
            if not eid.startswith(":"):
                incoming[eid] = e.getLength()
        if len(incoming) >= 2:
            junction_incoming[jid] = incoming
    return junction_incoming


def _scan_junction_occupancy(fcd_file: Path, junction_incoming, edge_to_junctions):
    """Scan FCD and return {jid: count_of_timesteps_with_occupied_edges_set}.

    Returns per-junction list of sets: occupied_edges[jid] is a list with one
    set per timestep containing the incoming edge IDs that had a vehicle
    within 30m of the stop line.
    """
    junc_occupied: dict[str, list[set[str]]] = {jid: [] for jid in junction_incoming}
    for _time, lane_vehicles in iter_fcd_timesteps(fcd_file):
        ts_occ: dict[str, set[str]] = {jid: set() for jid in junction_incoming}
        for lane, vehs in lane_vehicles.items():
            edge = lane.rsplit("_", 1)[0]
            if edge not in edge_to_junctions:
                continue
            for jid, edge_len in edge_to_junctions[edge]:
                for vid, pos, speed in vehs:
                    if pos >= edge_len - 30.0:
                        ts_occ[jid].add(edge)
                        break
        for jid in junction_incoming:
            junc_occupied[jid].append(ts_occ[jid])
    return junc_occupied


def gen_junction_conflict(net: str) -> list[dict]:
    junction_incoming = _build_junction_incoming(net)
    if not junction_incoming:
        return []
    edge_to_junctions: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for jid, edges in junction_incoming.items():
        for eid, elen in edges.items():
            edge_to_junctions[eid].append((jid, elen))

    rows = []
    for i in range(SAMPLES_PER_TYPE):
        junc_occ = _scan_junction_occupancy(
            fcd_path_s(net, i), junction_incoming, edge_to_junctions)
        conflict_counts: dict[str, int] = {}
        for jid, ts_sets in junc_occ.items():
            conflict_counts[jid] = sum(1 for s in ts_sets if len(s) >= 2)
        if not conflict_counts or max(conflict_counts.values()) == 0:
            continue
        worst = max(conflict_counts, key=conflict_counts.get)
        rows.append({
            "question": "Which junction has the most simulation timesteps where "
                        "at least two of its incoming edges each have a vehicle "
                        "within 30 meters of the stop line? Use each edge's length "
                        "from the network file to determine the stop-line position "
                        "(pos >= edge_length - 30). "
                        "Answer format: <junction_id>",
            "ground_truth": worst,
            "files_used": f"net,rou_s{i},fcd_s{i}",
        })
    return rows


def gen_junction_blocked(net: str) -> list[dict]:
    n = load_net(net)
    junction_incoming: dict[str, dict[str, float]] = {}
    for node in n.getNodes():
        jid = node.getID()
        if jid.startswith(":"):
            continue
        incoming: dict[str, float] = {}
        for e in node.getIncoming():
            eid = e.getID()
            if not eid.startswith(":"):
                incoming[eid] = e.getLength()
        if len(incoming) >= 3:
            junction_incoming[jid] = incoming

    if not junction_incoming:
        return []

    edge_to_junctions: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for jid, edges in junction_incoming.items():
        for eid, elen in edges.items():
            edge_to_junctions[eid].append((jid, elen))

    rows = []
    for i in range(SAMPLES_PER_TYPE):
        junc_occ = _scan_junction_occupancy(
            fcd_path_s(net, i), junction_incoming, edge_to_junctions)
        blocked_counts: dict[str, int] = {}
        for jid, ts_sets in junc_occ.items():
            total_inc = len(junction_incoming[jid])
            blocked_counts[jid] = sum(1 for s in ts_sets if len(s) == total_inc)
        if not blocked_counts or max(blocked_counts.values()) == 0:
            continue
        worst = max(blocked_counts, key=blocked_counts.get)
        rows.append({
            "question": "Among junctions with at least 3 incoming edges, which "
                        "junction has the most simulation timesteps where every "
                        "incoming edge has at least one vehicle within 30 meters "
                        "of the stop line? Use each edge's length from the "
                        "network file. "
                        "Answer format: <junction_id>",
            "ground_truth": worst,
            "files_used": f"net,fcd_s{i}",
        })
    return rows


# ===================== New retrieval generators (FCD, ADD) =====================

def gen_vehicle_speed_at_time(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|vehicle_speed_at_time")
    target_vids = [v["id"] for v in sample_vehicles(net, SAMPLES_PER_TYPE, rng)]
    vid_set = set(target_vids)
    appearances: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for time, lane_vehicles in iter_fcd_timesteps(fcd_path(net)):
        for lane, vehs in lane_vehicles.items():
            for vid, pos, speed in vehs:
                if vid in vid_set:
                    appearances[vid].append((time, speed))
    rows = []
    for vid in target_vids:
        entries = appearances.get(vid, [])
        if not entries:
            continue
        t, s = rng.choice(entries)
        rows.append({
            "question": f"What is the speed (m/s) of vehicle {vid} at simulation time {int(t)}? "
                        f"Answer format: <number> rounded to 2 decimal places",
            "ground_truth": f"{s:.2f}",
            "files_used": "fcd",
        })
    return rows


def gen_tls_phase_count(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|tls_phase_count")
    tls_list = load_tls(net)
    if not tls_list:
        return []
    selected = rng.sample(tls_list, min(SAMPLES_PER_TYPE, len(tls_list)))
    rows = []
    for tl in selected:
        rows.append({
            "question": f"How many phases does traffic light {tl['id']} have? "
                        f"Answer format: <integer>",
            "ground_truth": str(len(tl["phases"])),
            "files_used": "add",
        })
    return rows


# ===================== New reasoning generators (tripinfo, FCD, ADD) =====================

def gen_vehicle_highest_timeloss(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|vehicle_highest_timeloss")
    ti = load_tripinfo(net)
    if not ti:
        return []
    rows = []
    for _ in range(SAMPLES_PER_TYPE):
        t_start, t_end = sample_window(rng)
        candidates = {vid: info for vid, info in ti.items()
                      if t_start <= info["depart"] < t_end and info.get("timeLoss", 0.0) > 0}
        if not candidates:
            continue
        worst_vid = max(candidates, key=lambda v: candidates[v]["timeLoss"])
        rows.append({
            "question": f"Among vehicles departing between time {t_start} and {t_end} (seconds), "
                        f"which experienced the highest time loss? "
                        f"Answer format: <vehicle_id>",
            "ground_truth": worst_vid,
            "files_used": "tripinfo",
        })
    return rows


def gen_avg_trip_duration(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|avg_trip_duration")
    ti = load_tripinfo(net)
    if not ti:
        return []
    rows = []
    for _ in range(SAMPLES_PER_TYPE):
        t_start, t_end = sample_window(rng)
        completed = [info for info in ti.values()
                     if t_start <= info["depart"] < t_end
                     and info["arrival"] > 0
                     and info["duration"] == info["duration"]]
        if not completed:
            gt = "None"
        else:
            avg = sum(info["duration"] for info in completed) / len(completed)
            gt = f"{avg:.2f}"
        rows.append({
            "question": f"What is the average trip duration (seconds) of vehicles "
                        f"departing between time {t_start} and {t_end} that completed their trips? "
                        f"Answer format: <number> rounded to 2 decimal places, or 'None' if none completed",
            "ground_truth": gt,
            "files_used": "tripinfo",
        })
    return rows


def gen_vehicle_max_speed(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|vehicle_max_speed")
    target_vids = [v["id"] for v in sample_vehicles(net, SAMPLES_PER_TYPE, rng)]
    vid_set = set(target_vids)
    max_speeds: dict[str, float] = {}
    for _time, lane_vehicles in iter_fcd_timesteps(fcd_path(net)):
        for lane, vehs in lane_vehicles.items():
            for vid, pos, speed in vehs:
                if vid in vid_set:
                    if vid not in max_speeds or speed > max_speeds[vid]:
                        max_speeds[vid] = speed
    rows = []
    for vid in target_vids:
        if vid not in max_speeds:
            continue
        rows.append({
            "question": f"What is the maximum speed (m/s) that vehicle {vid} reached "
                        f"during the simulation? Answer format: <number> rounded to 2 decimal places",
            "ground_truth": f"{max_speeds[vid]:.2f}",
            "files_used": "fcd",
        })
    return rows


def gen_edge_peak_vehicle_count(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|edge_peak_vehicle_count")
    peak: dict[str, tuple[int, int]] = {}
    for time, lane_vehicles in iter_fcd_timesteps(fcd_path(net)):
        edge_counts: dict[str, int] = defaultdict(int)
        for lane, vehs in lane_vehicles.items():
            edge = lane.rsplit("_", 1)[0]
            edge_counts[edge] += len(vehs)
        for eid, cnt in edge_counts.items():
            if eid not in peak or cnt > peak[eid][1]:
                peak[eid] = (int(time), cnt)
    if not peak:
        return []
    candidates = list(peak.keys())
    selected = rng.sample(candidates, min(SAMPLES_PER_TYPE, len(candidates)))
    rows = []
    for eid in selected:
        rows.append({
            "question": f"At which simulation second did edge {eid} have the most vehicles "
                        f"present simultaneously? Answer format: <integer>",
            "ground_truth": str(peak[eid][0]),
            "files_used": "fcd",
        })
    return rows


def gen_tls_total_cycle_time(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|tls_total_cycle_time")
    tls_list = load_tls(net)
    if not tls_list:
        return []
    selected = rng.sample(tls_list, min(SAMPLES_PER_TYPE, len(tls_list)))
    rows = []
    for tl in selected:
        total = sum(ph["duration"] for ph in tl["phases"])
        rows.append({
            "question": f"What is the total cycle time (seconds) of traffic light {tl['id']}? "
                        f"(Sum of all phase durations.) Answer format: <integer>",
            "ground_truth": str(total),
            "files_used": "add",
        })
    return rows


def gen_tls_green_phase_count(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|tls_green_phase_count")
    tls_list = load_tls(net)
    if not tls_list:
        return []
    multi = [tl for tl in tls_list if len(tl["phases"]) >= 2]
    if not multi:
        return []
    selected = rng.sample(multi, min(SAMPLES_PER_TYPE, len(multi)))
    rows = []
    for tl in selected:
        n_green = sum(1 for ph in tl["phases"]
                      if any(c in "Gg" for c in ph["state"]))
        rows.append({
            "question": f"How many green phases (phases containing at least one 'G' or 'g' signal) "
                        f"does traffic light {tl['id']} have? Answer format: <integer>",
            "ground_truth": str(n_green),
            "files_used": "add",
        })
    return rows


def gen_tls_longest_green_phase(net: str) -> list[dict]:
    rng = random.Random(f"{SEED}|{net}|tls_longest_green_phase")
    tls_list = load_tls(net)
    if not tls_list:
        return []
    with_green = [tl for tl in tls_list
                  if any(any(c in "Gg" for c in ph["state"]) for ph in tl["phases"])]
    if not with_green:
        return []
    selected = rng.sample(with_green, min(SAMPLES_PER_TYPE, len(with_green)))
    rows = []
    for tl in selected:
        green_phases = [ph for ph in tl["phases"] if any(c in "Gg" for c in ph["state"])]
        longest = max(green_phases, key=lambda ph: ph["duration"])
        rows.append({
            "question": f"What is the duration (seconds) of the longest green phase "
                        f"(a phase containing at least one 'G' or 'g' signal) "
                        f"for traffic light {tl['id']}? Answer format: <integer>",
            "ground_truth": str(longest["duration"]),
            "files_used": "add",
        })
    return rows


def gen_nearest_vehicle_depart(net: str) -> list[dict]:
    """Distractor retrieval: given vehicle V, find the other vehicle departing
    from the same edge whose departure time is closest to V's."""
    rng = random.Random(f"{SEED}|{net}|nearest_vehicle_depart")
    rou = load_rou(net)
    origin_groups: dict[str, list[dict]] = defaultdict(list)
    for v in rou:
        if v["route"]:
            origin_groups[v["route"][0]].append(v)
    busy_edges = [e for e, vs in origin_groups.items() if len(vs) >= 3]
    if not busy_edges:
        return []
    rows = []
    attempts = 0
    while len(rows) < SAMPLES_PER_TYPE and attempts < SAMPLES_PER_TYPE * 20:
        attempts += 1
        edge = rng.choice(busy_edges)
        group = origin_groups[edge]
        target = rng.choice(group)
        others = [v for v in group if v["id"] != target["id"]]
        if not others:
            continue
        nearest = min(others, key=lambda v: abs(v["depart"] - target["depart"]))
        rows.append({
            "question": (
                f"Among all vehicles that depart from edge {edge}, "
                f"which vehicle departs closest in time to vehicle {target['id']}? "
                f"(Exclude {target['id']} itself.) "
                f"Answer format: <vehicle_id>"
            ),
            "ground_truth": nearest["id"],
        })
    return rows


# ===================== New harder reasoning generators (5) =====================

def gen_stop_and_go_count(net: str) -> list[dict]:
    """Count stop-and-go cycles for a vehicle.

    A cycle: vehicle speed reaches 0.00 m/s (stopped), then later
    exceeds 3 m/s (resumed), then stops again. Each resumed→stopped
    transition after the first stop counts as one event. The first
    stop itself is not counted.
    """
    rng = random.Random(f"{SEED}|{net}|stop_and_go_count")
    vid_speeds: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for time, lane_vehicles in iter_fcd_timesteps(fcd_path(net)):
        for lane, vehs in lane_vehicles.items():
            for vid, pos, speed in vehs:
                vid_speeds[vid].append((time, speed))
    if not vid_speeds:
        return []
    candidates = []
    for vid, records in vid_speeds.items():
        records.sort()
        has_stop = any(s == 0.0 for _, s in records)
        has_move = any(s > 3.0 for _, s in records)
        if has_stop and has_move and len(records) >= 20:
            candidates.append(vid)
    if not candidates:
        return []
    selected = rng.sample(candidates, min(SAMPLES_PER_TYPE, len(candidates)))
    rows = []
    for vid in selected:
        records = sorted(vid_speeds[vid])
        state = "moving"
        count = 0
        for _, speed in records:
            if state == "moving" and speed == 0.0:
                state = "stopped"
            elif state == "stopped" and speed > 3.0:
                state = "resumed"
            elif state == "resumed" and speed == 0.0:
                count += 1
                state = "stopped"
        rows.append({
            "question": (
                f"How many stop-and-go events does vehicle {vid} experience? "
                f"A stop-and-go event is counted each time the vehicle, having "
                f"previously stopped (speed = 0.00 m/s) and then resumed moving "
                f"(speed > 3 m/s), stops again (speed = 0.00 m/s). The initial "
                f"stop is not counted — only subsequent stops after resuming. "
                f"Answer format: <integer>"
            ),
            "ground_truth": str(count),
            "files_used": "fcd",
        })
    return rows


def gen_speed_percentile(net: str) -> list[dict]:
    """90th percentile of per-timestep average speeds on an edge."""
    rng = random.Random(f"{SEED}|{net}|speed_percentile")
    edge_avg_speeds: dict[str, list[float]] = defaultdict(list)
    for time, lane_vehicles in iter_fcd_timesteps(fcd_path(net)):
        edge_speeds: dict[str, list[float]] = defaultdict(list)
        for lane, vehs in lane_vehicles.items():
            edge = lane.rsplit("_", 1)[0]
            for vid, pos, speed in vehs:
                edge_speeds[edge].append(speed)
        for eid, speeds in edge_speeds.items():
            edge_avg_speeds[eid].append(sum(speeds) / len(speeds))
    if not edge_avg_speeds:
        return []
    candidates = [eid for eid, avgs in edge_avg_speeds.items() if len(avgs) >= 10]
    if not candidates:
        return []
    selected = rng.sample(candidates, min(SAMPLES_PER_TYPE, len(candidates)))
    rows = []
    for eid in selected:
        avgs = sorted(edge_avg_speeds[eid])
        idx = int(len(avgs) * 0.9)
        idx = min(idx, len(avgs) - 1)
        p90 = avgs[idx]
        rows.append({
            "question": (
                f"What is the 90th percentile of the per-timestep average vehicle speed "
                f"(m/s) on edge {eid}? For each simulation second that the edge has at "
                f"least one vehicle, compute the average speed of all vehicles on that edge, "
                f"then find the 90th percentile of those averages. "
                f"Answer format: <number> rounded to 2 decimal places"
            ),
            "ground_truth": f"{p90:.2f}",
            "files_used": "fcd",
        })
    return rows


def gen_bottleneck_edge(net: str) -> list[dict]:
    """Which edge on the shortest A→B path causes the largest detour if removed?"""
    rng = random.Random(f"{SEED}|{net}|bottleneck_edge")
    n = load_net(net)
    adj, edges = edge_graph(n)
    rows = []
    attempts = 0
    while len(rows) < SAMPLES_PER_TYPE and attempts < 50:
        attempts += 1
        a, b = sample_junction_pair(n, rng)
        aid, bid = a.getID(), b.getID()
        _, orig_edges, orig_dist = dijkstra(adj, edges, aid, bid)
        if orig_edges is None or len(orig_edges) < 2:
            continue
        worst_edge = None
        worst_increase = -1.0
        for eid in orig_edges:
            _, _, new_dist = dijkstra(adj, edges, aid, bid, excluded_edge=eid)
            if new_dist == float("inf"):
                worst_edge = eid
                worst_increase = float("inf")
                break
            increase = new_dist - orig_dist
            if increase > worst_increase:
                worst_increase = increase
                worst_edge = eid
        if worst_edge is None:
            continue
        if worst_increase == float("inf"):
            gt = worst_edge
            rows.append({
                "question": (
                    f"Consider the shortest path from junction {aid} to junction {bid}. "
                    f"For each edge on this path, compute the shortest-path distance "
                    f"from {aid} to {bid} after removing that edge. Which edge causes "
                    f"the largest increase in distance (or disconnects the path)? "
                    f"If an edge disconnects the path, report that edge. "
                    f"Answer format: <edge_id>"
                ),
                "ground_truth": gt,
                "files_used": "net",
            })
        else:
            gt = worst_edge
            rows.append({
                "question": (
                    f"Consider the shortest path from junction {aid} to junction {bid}. "
                    f"For each edge on this path, compute the shortest-path distance "
                    f"from {aid} to {bid} after removing that edge. Which edge causes "
                    f"the largest increase in distance (or disconnects the path)? "
                    f"If an edge disconnects the path, report that edge. "
                    f"Answer format: <edge_id>"
                ),
                "ground_truth": gt,
                "files_used": "net",
            })
    return rows


def gen_route_jaccard_pair(net: str) -> list[dict]:
    """Most similar pair of vehicle routes by Jaccard similarity.

    Jaccard = |intersection| / |union| of edge sets.
    Requires O(V^2) pairwise comparison. T-Rev may use wrong set
    operation or fail to handle large route files efficiently.
    Reports the pair as "vehA, vehB" (lexicographic order).
    """
    rows = []
    for i in range(SAMPLES_PER_TYPE):
        rou = load_rou_s(net, i)
        vehs = [(v["id"], set(v["route"])) for v in rou if v["route"]]
        if len(vehs) < 2:
            continue
        best_j = -1.0
        best_pair = None
        for a_idx in range(len(vehs)):
            vid_a, edges_a = vehs[a_idx]
            for b_idx in range(a_idx + 1, len(vehs)):
                vid_b, edges_b = vehs[b_idx]
                inter = len(edges_a & edges_b)
                union = len(edges_a | edges_b)
                if union == 0:
                    continue
                j = inter / union
                pair = tuple(sorted([vid_a, vid_b]))
                if (j > best_j
                        or (j == best_j and best_pair is not None
                            and pair < best_pair)):
                    best_j = j
                    best_pair = pair
        if best_pair is None:
            continue
        rows.append({
            "question": (
                "Which pair of vehicles has the most similar routes, "
                "measured by Jaccard similarity of their edge sets? "
                "Jaccard(A,B) = |edges_A intersect edges_B| / "
                "|edges_A union edges_B|. Compare ALL pairs of vehicles. "
                "Break ties by lexicographic order of the pair "
                "(smaller vehicle ID first). "
                "Answer format: <vehicle_id_1>, <vehicle_id_2>"
            ),
            "ground_truth": f"{best_pair[0]}, {best_pair[1]}",
            "files_used": f"rou_s{i}",
        })
    return rows


def gen_route_weighted_jaccard_pair(net: str) -> list[dict]:
    """Vehicle pair with the highest NON-IDENTICAL IDF-weighted Jaccard.

    Excludes pairs whose edge-sets are identical (sim=1.0 ties are
    degenerate on grid networks).  Among remaining pairs, picks the
    highest IDF-weighted Jaccard.  O(V^2) exhaustive, no shortcut.
    """
    import math
    rows = []
    for i in range(SAMPLES_PER_TYPE):
        rou = load_rou_s(net, i)
        vehs = [(v["id"], set(v["route"])) for v in rou if v["route"]]
        if len(vehs) < 2:
            continue
        edge_freq: dict[str, int] = defaultdict(int)
        for _vid, route_edges in vehs:
            for e in route_edges:
                edge_freq[e] += 1
        edge_weight = {e: 1.0 / math.log2(1 + f) for e, f in edge_freq.items()}
        best_j = -1.0
        best_pair = None
        for a_idx in range(len(vehs)):
            vid_a, edges_a = vehs[a_idx]
            for b_idx in range(a_idx + 1, len(vehs)):
                vid_b, edges_b = vehs[b_idx]
                if edges_a == edges_b:
                    continue
                inter = edges_a & edges_b
                union = edges_a | edges_b
                w_inter = sum(edge_weight[e] for e in inter)
                w_union = sum(edge_weight[e] for e in union)
                if w_union == 0:
                    continue
                j = w_inter / w_union
                pair = tuple(sorted([vid_a, vid_b]))
                if (j > best_j
                        or (j == best_j and best_pair is not None
                            and pair < best_pair)):
                    best_j = j
                    best_pair = pair
        if best_pair is None:
            continue
        rows.append({
            "question": (
                "Which pair of vehicles has the most similar but NOT "
                "identical routes, measured by IDF-weighted Jaccard "
                "similarity? First, compute the weight of each edge as "
                "w(e) = 1 / log2(1 + freq(e)), where freq(e) is the "
                "number of vehicles whose routes include edge e. "
                "Then for each pair whose edge-sets differ, compute: "
                "sum(w(e) for e in intersection) / "
                "sum(w(e) for e in union). "
                "Skip pairs with identical edge-sets. "
                "Compare ALL remaining pairs exhaustively. Break ties "
                "by lexicographic order (smaller vehicle ID first). "
                "Answer format: <vehicle_id_1>, <vehicle_id_2>"
            ),
            "ground_truth": f"{best_pair[0]}, {best_pair[1]}",
            "files_used": f"rou_s{i}",
        })
    return rows


def gen_route_edit_distance_pair(net: str) -> list[dict]:
    """Pair of vehicles with the smallest Levenshtein edit distance
    between their ordered edge sequences, excluding identical routes.

    O(V^2 * L^2) exhaustive — same computational profile as
    route_overlap_count.  Produces different ground truths because
    edit distance favours routes with few scattered substitutions
    rather than routes sharing a long consecutive block.
    """
    rows = []
    for i in range(SAMPLES_PER_TYPE):
        rou = load_rou_s(net, i)
        vehs = [(v["id"], v["route"]) for v in rou if len(v["route"]) >= 2]
        if len(vehs) < 2:
            continue

        def _edit_distance(a: list[str], b: list[str]) -> int:
            m, n = len(a), len(b)
            dp = list(range(n + 1))
            for i_row in range(1, m + 1):
                prev, dp[0] = dp[0], i_row
                for j_col in range(1, n + 1):
                    tmp = dp[j_col]
                    if a[i_row - 1] == b[j_col - 1]:
                        dp[j_col] = prev
                    else:
                        dp[j_col] = 1 + min(prev, dp[j_col], dp[j_col - 1])
                    prev = tmp
            return dp[n]

        best_ed = float("inf")
        best_pair = None
        for a_idx in range(len(vehs)):
            vid_a, route_a = vehs[a_idx]
            for b_idx in range(a_idx + 1, len(vehs)):
                vid_b, route_b = vehs[b_idx]
                if route_a == route_b:
                    continue
                ed = _edit_distance(route_a, route_b)
                pair = tuple(sorted([vid_a, vid_b]))
                if (ed < best_ed
                        or (ed == best_ed and best_pair is not None
                            and pair < best_pair)):
                    best_ed = ed
                    best_pair = pair
        if best_pair is None:
            continue
        rows.append({
            "question": (
                "Which pair of vehicles has the most similar but "
                "NOT identical routes, measured by Levenshtein edit "
                "distance of their ordered edge sequences? "
                "Each insertion, deletion, or substitution costs 1. "
                "Skip pairs with identical edge sequences. "
                "Find the pair with the smallest edit distance. "
                "Break ties by lexicographic order of the vehicle "
                "pair (smaller ID first). "
                "Answer format: <vehicle_id_1>, <vehicle_id_2>"
            ),
            "ground_truth": f"{best_pair[0]}, {best_pair[1]}",
            "files_used": f"rou_s{i}",
        })
    return rows


def gen_route_alignment_pair(net: str) -> list[dict]:
    """Pair of vehicles with the highest Needleman-Wunsch global alignment
    score between their ordered edge sequences, excluding identical routes.

    Uses match=+1, mismatch=-1, gap=-2.  Produces different ground truths
    from edit distance because NW penalises insertions/deletions (gaps) more
    heavily than substitutions, so it prefers routes of similar length with
    scattered mismatches over routes that share a long block but differ in
    length.  O(V^2 * L^2) exhaustive."""
    rows = []
    for i in range(SAMPLES_PER_TYPE):
        rou = load_rou_s(net, i)
        vehs = [(v["id"], v["route"]) for v in rou if len(v["route"]) >= 2]
        if len(vehs) < 2:
            continue

        def _nw_score(a: list[str], b: list[str]) -> int:
            m, n = len(a), len(b)
            MATCH, MISMATCH, GAP = 1, -1, -2
            dp = [j * GAP for j in range(n + 1)]
            for i_row in range(1, m + 1):
                prev, dp[0] = dp[0], i_row * GAP
                for j_col in range(1, n + 1):
                    tmp = dp[j_col]
                    s = MATCH if a[i_row - 1] == b[j_col - 1] else MISMATCH
                    dp[j_col] = max(prev + s, dp[j_col] + GAP, dp[j_col - 1] + GAP)
                    prev = tmp
            return dp[n]

        best_score = float("-inf")
        best_pair = None
        for a_idx in range(len(vehs)):
            vid_a, route_a = vehs[a_idx]
            for b_idx in range(a_idx + 1, len(vehs)):
                vid_b, route_b = vehs[b_idx]
                if route_a == route_b:
                    continue
                sc = _nw_score(route_a, route_b)
                pair = tuple(sorted([vid_a, vid_b]))
                if (sc > best_score
                        or (sc == best_score and best_pair is not None
                            and pair < best_pair)):
                    best_score = sc
                    best_pair = pair
        if best_pair is None:
            continue
        rows.append({
            "question": (
                "Which pair of vehicles has the best global alignment "
                "of their ordered edge sequences (Needleman-Wunsch), "
                "excluding identical routes? "
                "Use scoring: match = +1, mismatch = -1, gap = -2. "
                "Skip pairs with identical edge sequences. "
                "Find the pair with the HIGHEST alignment score. "
                "Compare ALL pairs exhaustively. "
                "Break ties by lexicographic order of the vehicle "
                "pair (smaller ID first). "
                "Answer format: <vehicle_id_1>, <vehicle_id_2>"
            ),
            "ground_truth": f"{best_pair[0]}, {best_pair[1]}",
            "files_used": f"rou_s{i}",
        })
    return rows


def _gen_shortest_path_count_UNUSED(net: str) -> list[dict]:
    """DEAD CODE – not in registry. Only works on grid_8x8."""
    import heapq
    rng = random.Random(f"{SEED}|{net}|shortest_path_count")
    n = load_net(net)
    adj, edges = edge_graph(n)
    rows = []
    attempts = 0
    while len(rows) < SAMPLES_PER_TYPE and attempts < 100:
        attempts += 1
        a, b = sample_junction_pair(n, rng)
        aid, bid = a.getID(), b.getID()
        dist: dict[str, float] = {aid: 0.0}
        count: dict[str, int] = {aid: 1}
        pq: list[tuple[float, str]] = [(0.0, aid)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, float("inf")):
                continue
            for v, eid, length in adj.get(u, []):
                nd = d + length
                if nd < dist.get(v, float("inf")):
                    dist[v] = nd
                    count[v] = count[u]
                    heapq.heappush(pq, (nd, v))
                elif abs(nd - dist.get(v, float("inf"))) < 1e-9:
                    count[v] = count.get(v, 0) + count[u]
        if bid not in dist or count.get(bid, 0) < 2:
            continue
        rows.append({
            "question": (
                f"How many distinct shortest paths exist from junction "
                f"{aid} to junction {bid}? Two paths are distinct if "
                f"they differ in at least one edge. Count ALL shortest "
                f"paths (same total distance as the minimum). "
                f"Answer format: <integer>"
            ),
            "ground_truth": str(count[bid]),
            "files_used": "net",
        })
    return rows


def _gen_route_isolation_vehicle_UNUSED(net: str) -> list[dict]:
    """DEAD CODE – not in registry. T-Rev gets 100%%.

    Vehicle whose route is most dissimilar from all other routes.
    For each vehicle, compute its average Jaccard similarity to every
    other vehicle. The vehicle with the LOWEST average similarity has
    the most isolated/unique route. O(V^2) exhaustive. T-Rev may
    shortcut by only comparing each vehicle against a subset.
    """
    rows = []
    for i in range(SAMPLES_PER_TYPE):
        rou = load_rou_s(net, i)
        vehs = [(v["id"], set(v["route"])) for v in rou if v["route"]]
        if len(vehs) < 3:
            continue
        best_vid = None
        best_avg = float("inf")
        for a_idx in range(len(vehs)):
            vid_a, edges_a = vehs[a_idx]
            total_j = 0.0
            for b_idx in range(len(vehs)):
                if a_idx == b_idx:
                    continue
                edges_b = vehs[b_idx][1]
                inter = len(edges_a & edges_b)
                union = len(edges_a | edges_b)
                if union > 0:
                    total_j += inter / union
            avg_j = total_j / (len(vehs) - 1)
            if (avg_j < best_avg
                    or (avg_j == best_avg
                        and (best_vid is None or vid_a < best_vid))):
                best_avg = avg_j
                best_vid = vid_a
        if best_vid is None:
            continue
        rows.append({
            "question": (
                "Which vehicle has the most unique route compared to "
                "all other vehicles? For each vehicle, compute its "
                "average Jaccard similarity to every other vehicle: "
                "Jaccard(A,B) = |edges_A intersect edges_B| / "
                "|edges_A union edges_B|. Average over ALL other "
                "vehicles. The vehicle with the LOWEST average "
                "Jaccard similarity has the most unique route. "
                "Break ties by lexicographic order of vehicle ID. "
                "Answer format: <vehicle_id>"
            ),
            "ground_truth": best_vid,
            "files_used": f"rou_s{i}",
        })
    return rows


def gen_route_overlap_count(net: str) -> list[dict]:
    """Vehicle pair with the longest shared consecutive sub-route.

    For each pair of vehicles, find the longest common substring
    (consecutive edge sequence) in their routes. Report the pair
    with the longest overlap. O(V^2 * L) where L is route length.
    T-Rev may shortcut the exhaustive search.
    """
    rows = []
    for i in range(SAMPLES_PER_TYPE):
        rou = load_rou_s(net, i)
        vehs = [(v["id"], v["route"]) for v in rou if len(v["route"]) >= 2]
        if len(vehs) < 2:
            continue

        def longest_common_substring_len(a: list[str], b: list[str]) -> int:
            best = 0
            for start_a in range(len(a)):
                for start_b in range(len(b)):
                    length = 0
                    while (start_a + length < len(a)
                           and start_b + length < len(b)
                           and a[start_a + length] == b[start_b + length]):
                        length += 1
                    if length > best:
                        best = length
            return best

        best_len = 0
        best_pair = None
        for a_idx in range(len(vehs)):
            vid_a, route_a = vehs[a_idx]
            for b_idx in range(a_idx + 1, len(vehs)):
                vid_b, route_b = vehs[b_idx]
                lcs = longest_common_substring_len(route_a, route_b)
                pair = tuple(sorted([vid_a, vid_b]))
                if (lcs > best_len
                        or (lcs == best_len and best_pair is not None
                            and pair < best_pair)):
                    best_len = lcs
                    best_pair = pair
        if best_pair is None or best_len == 0:
            continue
        rows.append({
            "question": (
                "Which pair of vehicles shares the longest consecutive "
                "sub-route (longest common substring of edge sequences)? "
                "For each pair, find the longest sequence of consecutive "
                "edges that appears in both routes in the same order. "
                "Compare ALL pairs exhaustively. "
                "Break ties by lexicographic order of the vehicle pair "
                "(smaller ID first). "
                "Answer format: <vehicle_id_1>, <vehicle_id_2>"
            ),
            "ground_truth": f"{best_pair[0]}, {best_pair[1]}",
            "files_used": f"rou_s{i}",
        })
    return rows




def gen_max_speed_drop(net: str) -> list[dict]:
    """Largest single-second average-speed drop on an edge.

    For each pair of consecutive simulation seconds (t, t+1) where
    the edge has vehicles in BOTH seconds, compute:
      drop = avg_speed(t) - avg_speed(t+1)
    Report the maximum drop (positive = deceleration).
    """
    rng = random.Random(f"{SEED}|{net}|max_speed_drop")
    edge_ts_speeds: dict[str, dict[int, list[float]]] = defaultdict(
        lambda: defaultdict(list))
    for time, lane_vehicles in iter_fcd_timesteps(fcd_path(net)):
        t_int = int(time)
        for lane, vehs in lane_vehicles.items():
            edge = lane.rsplit("_", 1)[0]
            for vid, pos, speed in vehs:
                edge_ts_speeds[edge][t_int].append(speed)
    if not edge_ts_speeds:
        return []
    edge_max_drop: dict[str, tuple[float, int]] = {}
    for eid, ts_speeds in edge_ts_speeds.items():
        sorted_ts = sorted(ts_speeds.keys())
        best_drop = 0.0
        best_t = sorted_ts[0] if sorted_ts else 0
        for i in range(len(sorted_ts) - 1):
            t1, t2 = sorted_ts[i], sorted_ts[i + 1]
            if t2 - t1 != 1:
                continue
            avg1 = sum(ts_speeds[t1]) / len(ts_speeds[t1])
            avg2 = sum(ts_speeds[t2]) / len(ts_speeds[t2])
            drop = avg1 - avg2
            if drop > best_drop:
                best_drop = drop
                best_t = t1
        if best_drop > 0:
            edge_max_drop[eid] = (best_drop, best_t)
    candidates = list(edge_max_drop.keys())
    if not candidates:
        return []
    selected = rng.sample(candidates, min(SAMPLES_PER_TYPE, len(candidates)))
    rows = []
    for eid in selected:
        drop, t = edge_max_drop[eid]
        rows.append({
            "question": (
                f"What is the largest single-second average speed drop (m/s) on "
                f"edge {eid}? For each pair of consecutive simulation seconds "
                f"(t, t+1) where edge {eid} has at least one vehicle in BOTH "
                f"seconds, compute: drop = avg_speed(t) - avg_speed(t+1). "
                f"Only consecutive seconds count (t and t+1 must differ by "
                f"exactly 1). Report the maximum drop value (positive means "
                f"deceleration). Answer format: <number> rounded to 2 decimal places"
            ),
            "ground_truth": f"{drop:.2f}",
            "files_used": "fcd",
        })
    return rows


def gen_congestion_onset_count(net: str) -> list[dict]:
    """Count upward threshold crossings of vehicle count on an edge.

    A crossing occurs when the vehicle count on an edge transitions from
    strictly below the threshold to at-or-above the threshold between
    consecutive simulation seconds. The initial state (before the first
    timestep) is considered as 0 vehicles. Timesteps where the edge has
    no vehicles are counted as 0.
    """
    rng = random.Random(f"{SEED}|{net}|congestion_onset_count")
    edge_ts_count: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    all_times: set[int] = set()
    for time, lane_vehicles in iter_fcd_timesteps(fcd_path(net)):
        t_int = int(time)
        all_times.add(t_int)
        edge_counts: dict[str, int] = defaultdict(int)
        for lane, vehs in lane_vehicles.items():
            edge = lane.rsplit("_", 1)[0]
            edge_counts[edge] += len(vehs)
        for eid, cnt in edge_counts.items():
            edge_ts_count[eid][t_int] = cnt
    if not edge_ts_count or not all_times:
        return []
    min_t, max_t = min(all_times), max(all_times)
    candidates = []
    edge_results: dict[str, tuple[int, int]] = {}
    for eid, ts_count in edge_ts_count.items():
        peak = max(ts_count.values())
        if peak < 3:
            continue
        threshold = max(2, peak // 2)
        crossings = 0
        prev_count = 0
        for t in range(min_t, max_t + 1):
            cur_count = ts_count.get(t, 0)
            if prev_count < threshold and cur_count >= threshold:
                crossings += 1
            prev_count = cur_count
        if crossings > 0:
            candidates.append(eid)
            edge_results[eid] = (crossings, threshold)
    if not candidates:
        return []
    selected = rng.sample(candidates, min(SAMPLES_PER_TYPE, len(candidates)))
    rows = []
    for eid in selected:
        crossings, threshold = edge_results[eid]
        rows.append({
            "question": (
                f"How many times does the vehicle count on edge {eid} cross "
                f"upward through {threshold}? Count transitions where the count "
                f"goes from strictly below {threshold} to at-or-above {threshold} "
                f"between consecutive simulation seconds. If the edge has no "
                f"vehicles at a given second, its count is 0. The count before "
                f"the first simulation second is also 0. "
                f"Answer format: <integer>"
            ),
            "ground_truth": str(crossings),
            "files_used": "fcd",
        })
    return rows


def gen_network_diameter(net: str) -> list[dict]:
    """Diameter of the directed road network.

    The diameter is the maximum finite shortest-path distance (meters)
    over all ordered pairs (A, B) of junctions where a directed path
    from A to B exists.  Internal junctions (starting with ':') are
    excluded.  There is only one question per network (the diameter is
    a global property), but we generate SAMPLES_PER_TYPE copies with
    the same answer so the experiment runner stays uniform.
    """
    import heapq
    rng = random.Random(f"{SEED}|{net}|network_diameter")
    n = load_net(net)
    adj, edges = edge_graph(n)
    all_nodes = [j.getID() for j in n.getNodes() if not j.getID().startswith(":")]

    max_dist = 0.0
    max_pair = (all_nodes[0], all_nodes[1]) if len(all_nodes) >= 2 else ("", "")
    for src in all_nodes:
        dist = {src: 0.0}
        pq = [(0.0, src)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, float("inf")):
                continue
            for v, eid, length in adj.get(u, []):
                nd = d + length
                if nd < dist.get(v, float("inf")):
                    dist[v] = nd
                    heapq.heappush(pq, (nd, v))
        for dst, d in dist.items():
            if dst != src and d > max_dist:
                max_dist = d
                max_pair = (src, dst)

    rows = []
    for _ in range(SAMPLES_PER_TYPE):
        rows.append({
            "question": (
                f"What is the diameter of the road network? The diameter is the "
                f"maximum shortest-path distance (in meters) over all ordered "
                f"pairs of junctions (A, B) where a directed path from A to B "
                f"exists. Exclude internal junctions (whose IDs start with ':'). "
                f"Answer format: <number> rounded to 2 decimal places"
            ),
            "ground_truth": f"{max_dist:.2f}",
            "files_used": "net",
        })
    return rows


def gen_critical_junction(net: str) -> list[dict]:
    """How many ordered junction pairs become unreachable when a specific
    junction is removed?

    For junction J, we compute:
      before = ordered pairs (A,B) with A≠J, B≠J reachable in the original graph
               (paths may traverse J)
      after  = ordered pairs (A,B) with A≠J, B≠J reachable in the graph with J
               and all its edges removed
      lost   = before − after
    Each question picks a different junction and asks for its `lost` count.
    """
    from collections import deque
    rng = random.Random(f"{SEED}|{net}|critical_junction")
    n = load_net(net)
    adj, edges = edge_graph(n)
    all_nodes = [j.getID() for j in n.getNodes() if not j.getID().startswith(":")]
    all_set = set(all_nodes)

    reach: dict[str, set[str]] = {}
    for src in all_nodes:
        visited = {src}
        queue = deque([src])
        while queue:
            u = queue.popleft()
            for v, eid, length in adj.get(u, []):
                if v not in visited and v in all_set:
                    visited.add(v)
                    queue.append(v)
        reach[src] = visited

    impacts: dict[str, int] = {}
    for j in all_nodes:
        remaining_set = all_set - {j}
        before = sum(len(reach[src] & remaining_set) - 1 for src in all_nodes if src != j)
        after = 0
        for src in all_nodes:
            if src == j:
                continue
            visited = {src}
            queue = deque([src])
            while queue:
                u = queue.popleft()
                for v, eid, length in adj.get(u, []):
                    if v not in visited and v in remaining_set:
                        visited.add(v)
                        queue.append(v)
            after += len(visited) - 1
        impacts[j] = before - after

    positive = [(jid, imp) for jid, imp in impacts.items() if imp > 0]
    positive.sort(key=lambda x: -x[1])
    if len(positive) >= SAMPLES_PER_TYPE:
        step = max(1, len(positive) // SAMPLES_PER_TYPE)
        selected = [positive[i * step] for i in range(SAMPLES_PER_TYPE)]
    else:
        selected = list(positive)
        zero = [(jid, 0) for jid, imp in impacts.items() if imp == 0]
        rng.shuffle(zero)
        selected.extend(zero[:SAMPLES_PER_TYPE - len(selected)])
    rng.shuffle(selected)

    rows = []
    for junc_id, lost_count in selected:
        rows.append({
            "question": (
                f"How many ordered pairs of non-internal junctions become "
                f"unreachable when junction {junc_id} is removed from the "
                f"road network? A pair (A, B) 'becomes unreachable' if a "
                f"directed path from A to B existed in the original network "
                f"(paths may pass through {junc_id}) but no directed path "
                f"exists after removing junction {junc_id} and every edge "
                f"that starts or ends at {junc_id}. Exclude internal "
                f"junctions (IDs starting with ':'). Do NOT count pairs "
                f"where A or B is {junc_id} itself. "
                f"Answer format: <integer>"
            ),
            "ground_truth": str(lost_count),
            "files_used": "net",
        })
    return rows


def gen_path_flow_potential(net: str) -> list[dict]:
    """Maximum number of edge-disjoint directed paths between two junctions.

    Equivalent to max-flow with unit edge capacities.  Computed via
    Edmonds-Karp (BFS augmenting paths on the residual graph).
    """
    from collections import deque
    rng = random.Random(f"{SEED}|{net}|path_flow_potential")
    n = load_net(net)
    adj, edges = edge_graph(n)
    all_nodes = [j.getID() for j in n.getNodes() if not j.getID().startswith(":")]

    def max_flow_ek(src: str, dst: str) -> int:
        cap: dict[tuple[str, str], int] = {}
        res_adj: dict[str, set[str]] = defaultdict(set)
        for u, neighbors in adj.items():
            for v, eid, length in neighbors:
                cap[(u, v)] = cap.get((u, v), 0) + 1
                res_adj[u].add(v)
                res_adj[v].add(u)
                cap.setdefault((v, u), 0)
        flow = 0
        while True:
            parent: dict[str, str | None] = {src: None}
            queue = deque([src])
            while queue:
                u = queue.popleft()
                if u == dst:
                    break
                for v in res_adj[u]:
                    if v not in parent and cap.get((u, v), 0) > 0:
                        parent[v] = u
                        queue.append(v)
            if dst not in parent:
                break
            cur = dst
            while cur != src:
                prev = parent[cur]
                cap[(prev, cur)] -= 1
                cap[(cur, prev)] += 1
                cur = prev
            flow += 1
        return flow

    rows: list[dict] = []
    for _ in range(SAMPLES_PER_TYPE):
        for attempt in range(200):
            a, b = rng.sample(all_nodes, 2)
            jpath, epath, dist = dijkstra(adj, edges, a, b)
            if jpath is not None:
                break
        else:
            continue
        mf = max_flow_ek(a, b)
        rows.append({
            "question": (
                f"What is the maximum number of edge-disjoint directed "
                f"paths from junction {a} to junction {b}? Two paths are "
                f"edge-disjoint if they share no edges (they may share "
                f"junctions). Exclude internal junctions and edges (IDs "
                f"starting with ':'). "
                f"Answer format: <integer>"
            ),
            "ground_truth": str(mf),
            "files_used": "net",
        })
    return rows


def gen_junction_inflow_cv(net: str) -> list[dict]:
    """Junction with the most unequal distribution of incoming edge traffic.

    For each non-internal junction with ≥ 2 incoming non-internal edges,
    compute the total vehicle observations on each incoming edge (sum of
    vehicle counts across all lanes of that edge, across all FCD timesteps).
    Then compute the coefficient of variation (population std / mean) of
    those edge totals. Return the junction with the highest CV.
    Tie-break: higher total flow, then lexicographic junction ID.
    """
    n = load_net(net)

    junction_incoming: dict[str, list[str]] = {}
    edge_lanes: dict[str, list[str]] = {}
    for e in n.getEdges():
        eid = e.getID()
        if eid.startswith(":"):
            continue
        edge_lanes[eid] = [l.getID() for l in e.getLanes()]
        to_node = e.getToNode().getID()
        if to_node.startswith(":"):
            continue
        junction_incoming.setdefault(to_node, []).append(eid)

    junction_incoming = {j: edges for j, edges in junction_incoming.items()
                         if len(edges) >= 2}
    if not junction_incoming:
        return []

    lane_to_edge: dict[str, str] = {}
    for eid, lids in edge_lanes.items():
        for lid in lids:
            lane_to_edge[lid] = eid

    rows = []
    for i in range(SAMPLES_PER_TYPE):
        edge_flow: dict[str, int] = defaultdict(int)
        for _time, lane_vehicles in iter_fcd_timesteps(fcd_path_s(net, i)):
            for lane, vehs in lane_vehicles.items():
                eid = lane_to_edge.get(lane)
                if eid is not None:
                    edge_flow[eid] += len(vehs)

        best_junc = None
        best_cv = -1.0
        best_total = 0
        for jid, edges in junction_incoming.items():
            flows = [edge_flow.get(eid, 0) for eid in edges]
            mean_f = sum(flows) / len(flows)
            if mean_f == 0:
                continue
            var_f = sum((f - mean_f) ** 2 for f in flows) / len(flows)
            cv = round(var_f ** 0.5 / mean_f, 6)
            total = sum(flows)
            if (cv > best_cv
                    or (cv == best_cv and total > best_total)
                    or (cv == best_cv and total == best_total
                        and (best_junc is None or jid < best_junc))):
                best_cv = cv
                best_junc = jid
                best_total = total

        if best_junc is None:
            continue
        rows.append({
            "question": (
                "Which junction has the most unequal distribution of "
                "incoming traffic across its edges? For each non-internal "
                "junction with at least 2 incoming edges, compute the "
                "total vehicle count on each incoming edge (sum of all "
                "vehicle observations across all lanes and all timesteps "
                "in the FCD). Then compute the coefficient of variation "
                "(std / mean) of those totals. Report the junction with "
                "the highest CV. If multiple junctions tie at the highest "
                "CV, break the tie by the largest total incoming vehicle "
                "count, then by the lexicographically smallest junction ID. "
                "Answer format: <junction_id>"
            ),
            "ground_truth": best_junc,
            "files_used": f"net,fcd_s{i}",
        })
    return rows


def gen_edge_lane_entropy(net: str) -> list[dict]:
    """Shannon entropy of per-lane vehicle distribution per multi-lane edge.

    Entropy is harder to compute correctly than CV (need log, handle zeros).
    Many edges produce similar entropy values, creating tie-breaking traps.
    """
    import math

    n = load_net(net)
    multilane_edges: dict[str, list[str]] = {}
    lane_to_edge: dict[str, str] = {}
    for e in n.getEdges():
        eid = e.getID()
        if eid.startswith(":"):
            continue
        lanes = e.getLanes()
        if len(lanes) >= 2:
            multilane_edges[eid] = [l.getID() for l in lanes]
            for l in lanes:
                lane_to_edge[l.getID()] = eid

    if not multilane_edges:
        return []

    rows = []
    for i in range(SAMPLES_PER_TYPE):
        lane_counts: dict[str, int] = defaultdict(int)
        for _time, lane_vehicles in iter_fcd_timesteps(fcd_path_s(net, i)):
            for lane, vehs in lane_vehicles.items():
                lane_counts[lane] += len(vehs)

        best_edge = None
        best_entropy = float("inf")
        best_total = 0
        for eid, lane_ids in multilane_edges.items():
            counts = [lane_counts.get(lid, 0) for lid in lane_ids]
            total = sum(counts)
            if total == 0:
                continue
            probs = [c / total for c in counts]
            entropy = -sum(p * math.log2(p) for p in probs if p > 0)
            if (entropy < best_entropy
                    or (entropy == best_entropy and total > best_total)
                    or (entropy == best_entropy and total == best_total
                        and (best_edge is None or eid < best_edge))):
                best_entropy = entropy
                best_edge = eid
                best_total = total

        if best_edge is None:
            continue
        rows.append({
            "question": (
                "Which multi-lane edge has the most unequal lane usage, "
                "measured by the lowest Shannon entropy of vehicle "
                "distribution across lanes? For each multi-lane edge, "
                "compute the total vehicle observations on each lane "
                "across all FCD timesteps. Then compute the Shannon "
                "entropy (base-2) of the resulting distribution: "
                "H = -sum(p_i * log2(p_i)) where p_i = lane_count / "
                "total_count (skip lanes with 0 count). Lower entropy "
                "means more unequal. Break ties by higher total vehicle "
                "count, then lexicographic edge ID. "
                "Answer format: <edge_id>"
            ),
            "ground_truth": best_edge,
            "files_used": f"net,fcd_s{i}",
        })
    return rows


def gen_vehicle_freeflow_ratio(net: str) -> list[dict]:
    """Which completed vehicle has the highest actual/free-flow travel time ratio?"""
    n = load_net(net)
    edge_ff: dict[str, float] = {}
    for e in n.getEdges():
        eid = e.getID()
        if not eid.startswith(":"):
            edge_ff[eid] = e.getLength() / e.getSpeed() if e.getSpeed() > 0 else 0
    rows = []
    for i in range(SAMPLES_PER_TYPE):
        ti = load_tripinfo_s(net, i)
        rou = load_rou_s(net, i)
        best_vid, best_ratio = None, -1.0
        for v in rou:
            info = ti.get(v["id"])
            if info is None or math.isnan(info["duration"]):
                continue
            ff = sum(edge_ff.get(e, 0) for e in v["route"])
            if ff <= 0:
                continue
            ratio = info["duration"] / ff
            if ratio > best_ratio or (ratio == best_ratio and (best_vid is None or v["id"] < best_vid)):
                best_ratio = ratio
                best_vid = v["id"]
        if best_vid is None:
            continue
        rows.append({
            "question": (
                "Which completed vehicle has the highest ratio of actual "
                "trip duration to free-flow travel time? "
                "Free-flow time = sum of (edge_length / edge_speed_limit) "
                "for each edge in the vehicle's planned route. "
                "Actual duration is from tripinfo. "
                "Skip vehicles that did not arrive. "
                "Break ties by lexicographic vehicle ID. "
                "Answer format: <vehicle_id>"
            ),
            "ground_truth": best_vid,
            "files_used": f"net,rou_s{i},tripinfo_s{i}",
        })
    return rows


def gen_tls_approach_queue(net: str) -> list[dict]:
    """Which signalized junction has the highest average number of queued
    vehicles (speed < 0.1 m/s) on its incoming edges?"""
    tls_edges = load_tls_controlled_edges(net)
    if not tls_edges:
        return []
    approach_set: set[str] = set()
    for edges in tls_edges.values():
        approach_set.update(edges)
    rows = []
    for i in range(SAMPLES_PER_TYPE):
        tls_queued: dict[str, list[int]] = defaultdict(list)
        timestep_count = 0
        tls_ts_counts: dict[str, int] = defaultdict(int)
        for _time, lane_vehicles in iter_fcd_timesteps(fcd_path_s(net, i)):
            timestep_count += 1
            ts_queue: dict[str, int] = defaultdict(int)
            for lane, vehs in lane_vehicles.items():
                edge = lane.rsplit("_", 1)[0]
                if edge not in approach_set:
                    continue
                for vid, pos, speed in vehs:
                    if speed < 0.1:
                        for tls_id, edges in tls_edges.items():
                            if edge in edges:
                                ts_queue[tls_id] += 1
            for tls_id in tls_edges:
                tls_queued[tls_id].append(ts_queue.get(tls_id, 0))
        if timestep_count == 0:
            continue
        worst_tls = max(tls_queued,
                        key=lambda k: sum(tls_queued[k]) / len(tls_queued[k]))
        rows.append({
            "question": (
                "Which signalized junction has the highest average number "
                "of queued vehicles on its incoming edges? "
                "A vehicle is queued if its speed < 0.1 m/s. "
                "For each timestep, count queued vehicles on all incoming "
                "edges of each TLS junction. "
                "Average across all timesteps. "
                "Answer format: <tls_id>"
            ),
            "ground_truth": worst_tls,
            "files_used": f"net,add,fcd_s{i}",
        })
    return rows


def gen_tls_vehicle_delay(net: str) -> list[dict]:
    """Which signalized junction causes the most total vehicle delay?
    Uses all 5 file types."""
    tls_edges = load_tls_controlled_edges(net)
    if not tls_edges:
        return []
    n = load_net(net)
    approach_set: set[str] = set()
    for edges in tls_edges.values():
        approach_set.update(edges)
    edge_ff: dict[str, float] = {}
    for eid in approach_set:
        e = n.getEdge(eid)
        edge_ff[eid] = e.getLength() / e.getSpeed() if e.getSpeed() > 0 else 0

    rows = []
    for i in range(SAMPLES_PER_TYPE):
        ti = load_tripinfo_s(net, i)
        rou = load_rou_s(net, i)
        completed = {v["id"] for v in rou if v["id"] in ti}
        veh_routes: dict[str, list[str]] = {}
        for v in rou:
            if v["id"] in completed:
                veh_routes[v["id"]] = v["route"]

        traversals: dict[tuple[str, str], dict] = {}
        for time, lane_vehicles in iter_fcd_timesteps(fcd_path_s(net, i)):
            for lane, vehs in lane_vehicles.items():
                edge = lane.rsplit("_", 1)[0]
                if edge not in approach_set:
                    continue
                for vid, pos, speed in vehs:
                    if vid not in completed:
                        continue
                    key = (vid, edge)
                    if key not in traversals:
                        traversals[key] = {"enter": time, "exit": time}
                    else:
                        traversals[key]["exit"] = time

        tls_delay: dict[str, float] = defaultdict(float)
        for (vid, edge), times in traversals.items():
            actual = times["exit"] - times["enter"]
            ff = edge_ff.get(edge, 0)
            if ff <= 0 or actual <= 0:
                continue
            delay = max(0.0, actual - ff)
            for tls_id, edges in tls_edges.items():
                if edge in edges:
                    tls_delay[tls_id] += delay

        if not tls_delay:
            continue
        worst = max(tls_delay, key=tls_delay.get)
        rows.append({
            "question": (
                "Which signalized junction causes the most total vehicle "
                "delay (in vehicle-seconds)? "
                "For each completed vehicle traversing a TLS incoming edge, "
                "compute delay = max(0, actual_traversal_time - free_flow_time). "
                "actual_traversal_time = last_seen_time - first_seen_time on that edge. "
                "free_flow_time = edge_length / edge_speed_limit. "
                "Sum delays across all completed vehicles per TLS. "
                "Only count vehicles present in tripinfo (completed trips). "
                "Answer format: <tls_id>"
            ),
            "ground_truth": worst,
            "files_used": f"net,rou_s{i},tripinfo_s{i},fcd_s{i},add",
        })
    return rows


def gen_tls_phase_demand_imbalance(net: str) -> list[dict]:
    """Which TLS has the most unequal phase utilization (highest CV of
    arrival-rate across green phases)?  Uses all 5 file types."""
    tls_data = load_tls(net)
    if not tls_data:
        return []
    n = load_net(net)

    # linkIndex -> from-edge mapping per TLS (from net.xml connections)
    tls_link_edges: dict[str, dict[int, str]] = {}
    for tls in n.getTrafficLights():
        tid = tls.getID()
        link_map: dict[int, str] = {}
        for conn in tls.getConnections():
            inLane, _outLane, linkIndex = conn
            link_map[linkIndex] = inLane.getEdge().getID()
        tls_link_edges[tid] = link_map

    # Build phase windows for each TLS; keep only those with >= 2 green phases
    eligible: dict[str, dict] = {}
    for tl in tls_data:
        tid = tl["id"]
        if tid not in tls_link_edges:
            continue
        link_map = tls_link_edges[tid]
        phases = tl["phases"]
        cycle_time = sum(p["duration"] for p in phases)
        if cycle_time <= 0:
            continue

        windows: list[dict] = []
        t = 0
        green_indices: list[int] = []
        for pi, phase in enumerate(phases):
            state = phase["state"]
            dur = phase["duration"]
            green_edges: set[str] = set()
            for li, ch in enumerate(state):
                if ch in ("G", "g") and li in link_map:
                    green_edges.add(link_map[li])
            windows.append({"start": t, "end": t + dur,
                            "duration": dur, "green_edges": green_edges})
            if green_edges:
                green_indices.append(pi)
            t += dur

        if len(green_indices) >= 2:
            eligible[tid] = {"windows": windows,
                             "green_indices": green_indices,
                             "cycle_time": cycle_time}

    if not eligible:
        return []

    # Collect all TLS approach edges for FCD filtering
    all_approach: set[str] = set()
    for info in eligible.values():
        for pi in info["green_indices"]:
            all_approach.update(info["windows"][pi]["green_edges"])

    rows: list[dict] = []
    for i in range(SAMPLES_PER_TYPE):
        ti = load_tripinfo_s(net, i)
        rou = load_rou_s(net, i)
        completed = {v["id"] for v in rou if v["id"] in ti}
        veh_route_edges: dict[str, set[str]] = {}
        for v in rou:
            if v["id"] in completed:
                veh_route_edges[v["id"]] = set(v["route"])

        # first-seen time per (vehicle, edge) from FCD
        first_seen: dict[tuple[str, str], float] = {}
        for time, lane_vehicles in iter_fcd_timesteps(fcd_path_s(net, i)):
            for lane, vehs in lane_vehicles.items():
                edge = lane.rsplit("_", 1)[0]
                if edge not in all_approach:
                    continue
                for vid, _pos, _speed in vehs:
                    if vid not in completed:
                        continue
                    key = (vid, edge)
                    if key not in first_seen:
                        first_seen[key] = time

        # Compute CV per TLS
        tls_cv: dict[str, float] = {}
        for tid, info in eligible.items():
            cycle = info["cycle_time"]
            windows = info["windows"]
            green_idx = info["green_indices"]

            tls_approach: set[str] = set()
            for pi in green_idx:
                tls_approach.update(windows[pi]["green_edges"])

            phase_counts: dict[int, int] = {pi: 0 for pi in green_idx}
            for (vid, edge), arr_time in first_seen.items():
                if edge not in tls_approach:
                    continue
                if vid not in veh_route_edges or edge not in veh_route_edges[vid]:
                    continue
                tic = arr_time % cycle
                arrived_pi = None
                for pi_check in range(len(windows)):
                    w = windows[pi_check]
                    if w["start"] <= tic < w["end"]:
                        arrived_pi = pi_check
                        break
                if arrived_pi in green_idx and edge in windows[arrived_pi]["green_edges"]:
                    phase_counts[arrived_pi] += 1

            rates = [phase_counts[pi] / windows[pi]["duration"]
                     for pi in green_idx if windows[pi]["duration"] > 0]
            if len(rates) < 2:
                continue
            mean_r = sum(rates) / len(rates)
            if mean_r <= 0:
                continue
            var_r = sum((r - mean_r) ** 2 for r in rates) / (len(rates) - 1)
            cv = var_r ** 0.5 / mean_r
            tls_cv[tid] = cv

        if not tls_cv:
            continue
        worst = max(tls_cv, key=tls_cv.get)
        rows.append({
            "question": (
                "Which traffic light has the most unequal phase utilization "
                "(highest coefficient of variation of vehicle arrival rate "
                "across green phases)? "
                "Algorithm: (1) Parse the TLS add file for phase definitions "
                "(state strings and durations). (2) Parse network file "
                "connections with 'tl' and 'linkIndex' attributes to map each "
                "state-string position to its approach edge. (3) A 'green "
                "phase' is one whose state contains at least one 'G' or 'g'. "
                "Only consider TLS with >= 2 green phases. (4) For each "
                "completed vehicle (in tripinfo) whose planned route (from "
                "route file) includes a TLS approach edge, determine its "
                "arrival phase: compute first_seen_time (from FCD) mod "
                "cycle_time, then find which phase window that falls in. "
                "Count the arrival only if the approach edge has green in "
                "that phase. (5) arrival_rate = count / phase_duration for "
                "each green phase. CV = sample_std(rates) / mean(rates). "
                "Tiebreaker: higher total arrival count, then smaller TLS id "
                "(lexicographic). "
                "Answer format: <tls_id>"
            ),
            "ground_truth": worst,
            "files_used": f"net,rou_s{i},tripinfo_s{i},fcd_s{i},add",
        })
    return rows


def gen_signal_retiming_priority(net: str) -> list[dict]:
    """TLS with highest average stopped delay per approaching vehicle.
    Decision: where to invest in signal optimization first."""
    tls_edges = load_tls_controlled_edges(net)
    if not tls_edges:
        return []
    n = load_net(net)
    approach_set: set[str] = set()
    edge_lengths: dict[str, float] = {}
    for edges in tls_edges.values():
        approach_set.update(edges)
    for eid in approach_set:
        edge_lengths[eid] = n.getEdge(eid).getLength()

    rows = []
    for i in range(SAMPLES_PER_TYPE):
        tls_stopped_seconds: dict[str, float] = defaultdict(float)
        tls_vehicles: dict[str, set] = defaultdict(set)

        for time, lane_vehicles in iter_fcd_timesteps(fcd_path_s(net, i)):
            for lane, vehs in lane_vehicles.items():
                edge = lane.rsplit("_", 1)[0]
                if edge not in approach_set:
                    continue
                elen = edge_lengths.get(edge, 0)
                for vid, pos, speed in vehs:
                    if pos >= elen - 50.0:
                        for tls_id, edges in tls_edges.items():
                            if edge in edges:
                                tls_vehicles[tls_id].add(vid)
                                if speed < 0.5:
                                    tls_stopped_seconds[tls_id] += 1.0

        best_tls = None
        best_delay = -1.0
        for tls_id in tls_edges:
            n_veh = len(tls_vehicles.get(tls_id, set()))
            if n_veh == 0:
                continue
            avg_delay = tls_stopped_seconds.get(tls_id, 0) / n_veh
            if avg_delay > best_delay or (avg_delay == best_delay
                                          and (best_tls is None or tls_id < best_tls)):
                best_delay = avg_delay
                best_tls = tls_id

        if best_tls is None:
            continue
        rows.append({
            "question": (
                "Which intersection most needs signal retiming? "
                "Consider the average stopped delay experienced by "
                "vehicles approaching each signalized intersection. "
                "Answer format: <tls_id>"
            ),
            "ground_truth": best_tls,
            "files_used": f"net,add,fcd_s{i}",
        })
    return rows


def gen_volume_to_capacity_ratio(net: str) -> list[dict]:
    """Edge with highest V/C ratio in peak 15-min period.
    Decision: where to add lanes / widen roads."""
    n = load_net(net)
    edge_lanes: dict[str, int] = {}
    for e in n.getEdges():
        eid = e.getID()
        if not eid.startswith(":"):
            edge_lanes[eid] = e.getLaneNumber()

    rows = []
    for i in range(SAMPLES_PER_TYPE):
        edge_window_vehs: dict[str, dict[int, set]] = defaultdict(
            lambda: defaultdict(set))
        for time, lane_vehicles in iter_fcd_timesteps(fcd_path_s(net, i)):
            window = int(time) // 900
            for lane, vehs in lane_vehicles.items():
                edge = lane.rsplit("_", 1)[0]
                for vid, pos, speed in vehs:
                    edge_window_vehs[edge][window].add(vid)

        best_edge = None
        best_vc = -1.0
        for eid, windows in edge_window_vehs.items():
            nlanes = edge_lanes.get(eid, 1)
            capacity_15min = nlanes * 450
            for w, vids in windows.items():
                vc = len(vids) / capacity_15min if capacity_15min > 0 else 0
                if vc > best_vc or (vc == best_vc
                                    and (best_edge is None or eid < best_edge)):
                    best_vc = vc
                    best_edge = eid

        if best_edge is None:
            continue
        rows.append({
            "question": (
                "Which road segment most needs capacity expansion "
                "(e.g., adding lanes)? Consider how traffic volume "
                "compares to roadway capacity during peak periods. "
                "Answer format: <edge_id>"
            ),
            "ground_truth": best_edge,
            "files_used": f"net,fcd_s{i}",
        })
    return rows


def gen_od_travel_time_reliability(net: str) -> list[dict]:
    """OD pair with worst planning time index.
    Decision: which corridor needs reliability improvements."""
    n_obj = load_net(net)
    edge_ff: dict[str, float] = {}
    for e in n_obj.getEdges():
        eid = e.getID()
        if not eid.startswith(":"):
            edge_ff[eid] = e.getLength() / e.getSpeed() if e.getSpeed() > 0 else 0

    rows = []
    for i in range(SAMPLES_PER_TYPE):
        rou = load_rou_s(net, i)
        ti = load_tripinfo_s(net, i)

        od_durations: dict[tuple, list[float]] = defaultdict(list)
        od_ff: dict[tuple, float] = {}
        for v in rou:
            info = ti.get(v["id"])
            if info is None or not v["route"]:
                continue
            origin = v["route"][0]
            dest = v["route"][-1]
            od = (origin, dest)
            od_durations[od].append(info["duration"])
            if od not in od_ff:
                od_ff[od] = sum(edge_ff.get(e, 0) for e in v["route"])

        best_od = None
        best_pti = -1.0
        for od, durs in od_durations.items():
            if len(durs) < 3 or od_ff.get(od, 0) <= 0:
                continue
            sorted_d = sorted(durs)
            idx = min(math.ceil(0.95 * len(sorted_d)) - 1, len(sorted_d) - 1)
            pti = sorted_d[idx] / od_ff[od]
            if pti > best_pti or (pti == best_pti
                                  and (best_od is None or od < best_od)):
                best_pti = pti
                best_od = od

        if best_od is None:
            continue
        rows.append({
            "question": (
                "Which OD pair has the least reliable travel times? "
                "Consider the planning time index across completed "
                "trips. Only include OD pairs with at least 3 "
                "completed vehicles. "
                "Answer format: <origin_edge>, <destination_edge>"
            ),
            "ground_truth": f"{best_od[0]}, {best_od[1]}",
            "files_used": f"net,rou_s{i},tripinfo_s{i}",
        })
    return rows


def gen_speed_limit_review(net: str) -> list[dict]:
    """Edge with largest gap between speed limit and 85th percentile speed.
    Decision: where to raise or lower speed limits."""
    n_obj = load_net(net)
    edge_speed_limit: dict[str, float] = {}
    for e in n_obj.getEdges():
        eid = e.getID()
        if not eid.startswith(":"):
            edge_speed_limit[eid] = e.getSpeed()

    rows = []
    for i in range(SAMPLES_PER_TYPE):
        rou = load_rou_s(net, i)
        edge_veh_count: dict[str, int] = defaultdict(int)
        for v in rou:
            for eid in v["route"]:
                edge_veh_count[eid] += 1

        edge_speeds: dict[str, list[float]] = defaultdict(list)
        for time, lane_vehicles in iter_fcd_timesteps(fcd_path_s(net, i)):
            for lane, vehs in lane_vehicles.items():
                edge = lane.rsplit("_", 1)[0]
                for vid, pos, speed in vehs:
                    edge_speeds[edge].append(speed)

        best_edge = None
        best_gap = -1.0
        for eid, speeds in edge_speeds.items():
            if edge_veh_count.get(eid, 0) < 10:
                continue
            if eid not in edge_speed_limit:
                continue
            sorted_s = sorted(speeds)
            idx = min(int(0.85 * len(sorted_s)), len(sorted_s) - 1)
            p85 = sorted_s[idx]
            gap = abs(edge_speed_limit[eid] - p85)
            if gap > best_gap or (gap == best_gap
                                  and (best_edge is None or eid < best_edge)):
                best_gap = gap
                best_edge = eid

        if best_edge is None:
            continue
        rows.append({
            "question": (
                "Which road segment's posted speed limit is most "
                "mismatched with actual driving speeds? Use the 85th "
                "percentile speed methodology. Only include edges with "
                "at least 10 vehicles in their planned routes. "
                "Answer format: <edge_id>"
            ),
            "ground_truth": best_edge,
            "files_used": f"net,rou_s{i},fcd_s{i}",
        })
    return rows


def gen_transit_corridor(net: str) -> list[dict]:
    """Edge serving most distinct OD pairs among congested edges.
    Decision: where to place a bus route."""
    n_obj = load_net(net)
    edge_speed_limit: dict[str, float] = {}
    for e in n_obj.getEdges():
        eid = e.getID()
        if not eid.startswith(":"):
            edge_speed_limit[eid] = e.getSpeed()

    rows = []
    for i in range(SAMPLES_PER_TYPE):
        rou = load_rou_s(net, i)
        ti = load_tripinfo_s(net, i)
        completed = {v["id"] for v in rou if v["id"] in ti}

        edge_od_pairs: dict[str, set[tuple]] = defaultdict(set)
        edge_veh_count: dict[str, int] = defaultdict(int)
        for v in rou:
            if v["id"] not in completed or not v["route"]:
                continue
            origin = v["route"][0]
            dest = v["route"][-1]
            od = (origin, dest)
            for eid in v["route"]:
                edge_od_pairs[eid].add(od)
                edge_veh_count[eid] += 1

        edge_speed_sum: dict[str, float] = defaultdict(float)
        edge_speed_n: dict[str, int] = defaultdict(int)
        for time, lane_vehicles in iter_fcd_timesteps(fcd_path_s(net, i)):
            for lane, vehs in lane_vehicles.items():
                edge = lane.rsplit("_", 1)[0]
                for vid, pos, speed in vehs:
                    edge_speed_sum[edge] += speed
                    edge_speed_n[edge] += 1

        best_edge = None
        best_od_count = -1
        best_veh_count = 0
        for eid, od_set in edge_od_pairs.items():
            if eid not in edge_speed_limit or edge_speed_n.get(eid, 0) == 0:
                continue
            avg_speed = edge_speed_sum[eid] / edge_speed_n[eid]
            if avg_speed >= 0.5 * edge_speed_limit[eid]:
                continue
            n_od = len(od_set)
            n_veh = edge_veh_count[eid]
            if (n_od > best_od_count
                    or (n_od == best_od_count and n_veh > best_veh_count)
                    or (n_od == best_od_count and n_veh == best_veh_count
                        and (best_edge is None or eid < best_edge))):
                best_od_count = n_od
                best_edge = eid
                best_veh_count = n_veh

        if best_edge is None:
            continue
        rows.append({
            "question": (
                "Which congested road segment would benefit most from "
                "a new bus route? Consider edges with high travel "
                "demand diversity that also experience significant "
                "congestion. Only count completed vehicles. "
                "Answer format: <edge_id>"
            ),
            "ground_truth": best_edge,
            "files_used": f"net,rou_s{i},tripinfo_s{i},fcd_s{i}",
        })
    return rows


def gen_intersection_safety(net: str) -> list[dict]:
    """Signalized intersection with most high-speed conflict timesteps.
    Decision: which intersection needs protected phases or redesign."""
    tls_edges = load_tls_controlled_edges(net)
    if not tls_edges:
        return []
    n_obj = load_net(net)

    junction_incoming: dict[str, dict[str, float]] = {}
    for tls_id, edges in tls_edges.items():
        incoming: dict[str, float] = {}
        for eid in edges:
            incoming[eid] = n_obj.getEdge(eid).getLength()
        if len(incoming) >= 2:
            junction_incoming[tls_id] = incoming

    if not junction_incoming:
        return []

    edge_to_tls: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for tls_id, edges in junction_incoming.items():
        for eid, elen in edges.items():
            edge_to_tls[eid].append((tls_id, elen))

    rows = []
    for i in range(SAMPLES_PER_TYPE):
        tls_conflict_counts: dict[str, int] = defaultdict(int)

        for time, lane_vehicles in iter_fcd_timesteps(fcd_path_s(net, i)):
            tls_active: dict[str, set[str]] = defaultdict(set)
            for lane, vehs in lane_vehicles.items():
                edge = lane.rsplit("_", 1)[0]
                if edge not in edge_to_tls:
                    continue
                for tls_id, elen in edge_to_tls[edge]:
                    for vid, pos, speed in vehs:
                        if pos >= elen - 30.0 and speed > 5.0:
                            tls_active[tls_id].add(edge)
                            break

            for tls_id, active in tls_active.items():
                if len(active) >= 2:
                    tls_conflict_counts[tls_id] += 1

        if not tls_conflict_counts or max(tls_conflict_counts.values()) == 0:
            continue
        best_tls = None
        best_count = -1
        for tls_id, count in tls_conflict_counts.items():
            if count > best_count or (count == best_count
                                      and (best_tls is None or tls_id < best_tls)):
                best_count = count
                best_tls = tls_id

        rows.append({
            "question": (
                "Which signalized intersection has the highest risk "
                "of vehicle conflicts? Consider simultaneous "
                "high-speed approaches from multiple directions. "
                "Answer format: <tls_id>"
            ),
            "ground_truth": best_tls,
            "files_used": f"net,add,fcd_s{i}",
        })
    return rows


def gen_tls_queue_dissipation_time(net: str) -> list[dict]:
    """Which TLS has the slowest queue dissipation?

    For each signalized junction:
    1. Count queued vehicles (speed < 0.1 m/s) on incoming edges per second
    2. Find the earliest timestep with the peak queue count
    3. Scan forward to find the first second where the queue drops
       strictly below 50% of the peak
    4. dissipation_time = that second − peak second
       (if it never drops below 50%, use last_simulation_second − peak)
    5. Only consider TLS with peak queue >= 4
    6. Report the TLS with the longest dissipation time
    """
    tls_edges = load_tls_controlled_edges(net)
    if not tls_edges:
        return []
    approach_set: set[str] = set()
    for edges in tls_edges.values():
        approach_set.update(edges)

    rows = []
    for i in range(SAMPLES_PER_TYPE):
        tls_ts_queue: dict[str, dict[int, int]] = {tid: {} for tid in tls_edges}

        for time, lane_vehicles in iter_fcd_timesteps(fcd_path_s(net, i)):
            t_int = int(time)
            ts_queue: dict[str, int] = defaultdict(int)
            for lane, vehs in lane_vehicles.items():
                edge = lane.rsplit("_", 1)[0]
                if edge not in approach_set:
                    continue
                for vid, pos, speed in vehs:
                    if speed < 0.1:
                        for tls_id, edges in tls_edges.items():
                            if edge in edges:
                                ts_queue[tls_id] += 1
            for tls_id in tls_edges:
                tls_ts_queue[tls_id][t_int] = ts_queue.get(tls_id, 0)

        best_tls = None
        best_dissipation = -1
        best_peak = 0
        for tls_id, ts_queue in tls_ts_queue.items():
            if not ts_queue:
                continue
            peak_count = max(ts_queue.values())
            if peak_count < 4:
                continue
            threshold = peak_count * 0.5
            peak_time = min(t for t, c in ts_queue.items() if c == peak_count)
            sorted_after = sorted(t for t in ts_queue if t > peak_time)
            dissipation = None
            for t in sorted_after:
                if ts_queue[t] < threshold:
                    dissipation = t - peak_time
                    break
            if dissipation is None:
                last_t = max(ts_queue)
                dissipation = last_t - peak_time
            if (dissipation > best_dissipation
                    or (dissipation == best_dissipation and peak_count > best_peak)
                    or (dissipation == best_dissipation and peak_count == best_peak
                        and (best_tls is None or tls_id < best_tls))):
                best_dissipation = dissipation
                best_tls = tls_id
                best_peak = peak_count

        if best_tls is None:
            continue
        rows.append({
            "question": (
                "Which signalized junction has the slowest queue dissipation? "
                "For each TLS, count queued vehicles (speed < 0.1 m/s) on its "
                "incoming edges at each simulation second. Find the earliest "
                "timestep with the peak queue count. Then scan forward to find "
                "the first subsequent second where the queue count drops "
                "strictly below 50%% of the peak. The dissipation time is "
                "that second minus the peak second. If the queue never drops "
                "below 50%% of the peak, use the last simulation second minus "
                "the peak second. Only consider TLS with peak queue >= 4 "
                "vehicles. Report the TLS with the longest dissipation time. "
                "Break ties by higher peak count, then lexicographic TLS id. "
                "Answer format: <tls_id>"
            ),
            "ground_truth": best_tls,
            "files_used": f"net,add,fcd_s{i}",
        })
    return rows


# ===================== Registry =====================

QUESTION_TYPES: dict[str, dict] = {
    # Retrieval (12)
    "both_junctions":              {"fn": gen_both_junctions,              "files": ["net"],                     "kind": "retrieval"},
    "num_lanes":                   {"fn": gen_num_lanes,                   "files": ["net"],                     "kind": "retrieval"},
    "junction_coord":              {"fn": gen_junction_coord,              "files": ["net"],                     "kind": "retrieval"},
    "vehicle_depart_time":         {"fn": gen_vehicle_depart_time,         "files": ["rou"],                     "kind": "retrieval"},
    "vehicle_depart_edge":         {"fn": gen_vehicle_depart_edge,         "files": ["rou"],                     "kind": "retrieval"},
    "vehicle_route":               {"fn": gen_vehicle_route,               "files": ["rou"],                     "kind": "retrieval"},
    "vehicles_with_same_origin":   {"fn": gen_vehicles_with_same_origin,   "files": ["rou"],                     "kind": "retrieval"},
    "vehicle_travel_time":         {"fn": gen_vehicle_travel_time,         "files": ["tripinfo"],                "kind": "retrieval"},
    "vehicle_arrival_time":        {"fn": gen_vehicle_arrival_time,        "files": ["tripinfo"],                "kind": "retrieval"},
    "vehicle_speed_at_time":       {"fn": gen_vehicle_speed_at_time,       "files": ["fcd"],                     "kind": "retrieval"},
    "tls_phase_count":             {"fn": gen_tls_phase_count,             "files": ["add"],                     "kind": "retrieval"},
    "tls_longest_green_phase":     {"fn": gen_tls_longest_green_phase,     "files": ["add"],                     "kind": "retrieval"},
    "nearest_vehicle_depart":      {"fn": gen_nearest_vehicle_depart,      "files": ["rou"],                     "kind": "retrieval"},
    # Reasoning — single-file (10)
    "shortest_path_full":          {"fn": gen_shortest_path_full,          "files": ["net"],                     "kind": "reasoning"},
    "shortest_path_edge_removal":  {"fn": gen_shortest_path_edge_removal,  "files": ["net"],                     "kind": "reasoning"},
    "node_removal_connectivity":   {"fn": gen_node_removal_connectivity,   "files": ["net"],                     "kind": "reasoning"},
    "vehicles_passing_edge":       {"fn": gen_vehicles_passing_edge,       "files": ["rou"],                     "kind": "reasoning"},
    "avg_route_length_in_window":  {"fn": gen_avg_route_length_in_window,  "files": ["rou"],                     "kind": "reasoning"},
    "vehicle_highest_timeloss":    {"fn": gen_vehicle_highest_timeloss,    "files": ["tripinfo"],                "kind": "reasoning"},
    "avg_trip_duration":           {"fn": gen_avg_trip_duration,           "files": ["tripinfo"],                "kind": "reasoning"},
    "vehicle_max_speed":           {"fn": gen_vehicle_max_speed,           "files": ["fcd"],                     "kind": "reasoning"},
    "edge_peak_vehicle_count":     {"fn": gen_edge_peak_vehicle_count,     "files": ["fcd"],                     "kind": "reasoning"},
    "tls_total_cycle_time":        {"fn": gen_tls_total_cycle_time,        "files": ["add"],                     "kind": "reasoning"},
    "tls_green_phase_count":       {"fn": gen_tls_green_phase_count,       "files": ["add"],                     "kind": "reasoning"},
    "stop_and_go_count":           {"fn": gen_stop_and_go_count,           "files": ["fcd"],                     "kind": "reasoning"},
    "speed_percentile":            {"fn": gen_speed_percentile,            "files": ["fcd"],                     "kind": "reasoning"},
    "bottleneck_edge":             {"fn": gen_bottleneck_edge,             "files": ["net"],                     "kind": "reasoning"},
    "route_jaccard_pair":          {"fn": gen_route_jaccard_pair,          "files": ["rou"],                     "kind": "reasoning"},
    "route_weighted_jaccard_pair": {"fn": gen_route_weighted_jaccard_pair, "files": ["rou"],                     "kind": "reasoning"},
    "route_edit_distance_pair":    {"fn": gen_route_edit_distance_pair,    "files": ["rou"],                     "kind": "reasoning"},
    "route_alignment_pair":        {"fn": gen_route_alignment_pair,        "files": ["rou"],                     "kind": "reasoning"},
    "route_overlap_count":         {"fn": gen_route_overlap_count,         "files": ["rou"],                     "kind": "reasoning"},
    "max_speed_drop":              {"fn": gen_max_speed_drop,              "files": ["fcd"],                     "kind": "reasoning"},
    "congestion_onset_count":      {"fn": gen_congestion_onset_count,      "files": ["fcd"],                     "kind": "reasoning"},
    "network_diameter":            {"fn": gen_network_diameter,            "files": ["net"],                     "kind": "reasoning"},
    "critical_junction":           {"fn": gen_critical_junction,           "files": ["net"],                     "kind": "reasoning"},
    "path_flow_potential":         {"fn": gen_path_flow_potential,         "files": ["net"],                     "kind": "reasoning"},
    # Multi-step reasoning — multiple files (10)
    "edge_removal_route_count":          {"fn": gen_edge_removal_route_count,          "files": ["net", "rou"],            "kind": "multi-step"},
    "vehicle_route_distance_meters":     {"fn": gen_vehicle_route_distance_meters,     "files": ["net", "rou"],            "kind": "multi-step"},
    "worst_congestion_od":               {"fn": gen_worst_congestion_od,               "files": ["net", "rou", "tripinfo"],"kind": "multi-step"},
    "gap_violations":                    {"fn": gen_gap_violations,                    "files": ["net", "rou", "fcd"],     "kind": "multi-step"},
    "tls_delay":                         {"fn": gen_tls_delay,                         "files": ["net", "add", "fcd"],     "kind": "multi-step"},
    "peak_offpeak_degradation":          {"fn": gen_peak_offpeak_degradation,          "files": ["rou", "tripinfo"],       "kind": "multi-step"},
    "lane_utilisation":                  {"fn": gen_lane_utilisation,                   "files": ["net", "fcd"],            "kind": "multi-step"},
    "incomplete_od":                     {"fn": gen_incomplete_od,                     "files": ["rou", "tripinfo"],       "kind": "multi-step"},
    "junction_conflict":                 {"fn": gen_junction_conflict,                 "files": ["net", "rou", "fcd"],     "kind": "multi-step"},
    "junction_blocked":                  {"fn": gen_junction_blocked,                  "files": ["net", "fcd"],            "kind": "multi-step"},
    "junction_inflow_cv":                {"fn": gen_junction_inflow_cv,                "files": ["net", "fcd"],            "kind": "multi-step"},
    "edge_lane_entropy":                 {"fn": gen_edge_lane_entropy,                 "files": ["net", "fcd"],            "kind": "multi-step"},
    "vehicle_freeflow_ratio":            {"fn": gen_vehicle_freeflow_ratio,            "files": ["net", "rou", "tripinfo"],"kind": "multi-step"},
    "tls_approach_queue":                {"fn": gen_tls_approach_queue,                "files": ["net", "add", "fcd"],     "kind": "multi-step"},
    "tls_vehicle_delay":                 {"fn": gen_tls_vehicle_delay,                 "files": ["net", "rou", "tripinfo", "fcd", "add"], "kind": "multi-step"},
    "tls_phase_demand_imbalance":        {"fn": gen_tls_phase_demand_imbalance,        "files": ["net", "rou", "tripinfo", "fcd", "add"], "kind": "multi-step"},
    "tls_queue_dissipation_time":        {"fn": gen_tls_queue_dissipation_time,        "files": ["net", "add", "fcd"],     "kind": "multi-step"},
    # Decision-oriented questions
    "signal_retiming_priority":          {"fn": gen_signal_retiming_priority,          "files": ["net", "add", "fcd"],     "kind": "multi-step"},
    "volume_to_capacity_ratio":          {"fn": gen_volume_to_capacity_ratio,          "files": ["net", "fcd"],            "kind": "multi-step"},
    "od_travel_time_reliability":        {"fn": gen_od_travel_time_reliability,        "files": ["net", "rou", "tripinfo"],"kind": "multi-step"},
    "speed_limit_review":                {"fn": gen_speed_limit_review,                "files": ["net", "rou", "fcd"],     "kind": "multi-step"},
    "transit_corridor":                  {"fn": gen_transit_corridor,                  "files": ["net", "rou", "tripinfo", "fcd"], "kind": "multi-step"},
    "intersection_safety":               {"fn": gen_intersection_safety,               "files": ["net", "add", "fcd"],     "kind": "multi-step"},
}


# ===================== CSV writer =====================

def write_csv(network: str, type_name: str, rows: list[dict], files_used: list[str]) -> Path:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    out = QA_DIR / f"{network}_{type_name}.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["network", "type", "sample_id", "question", "ground_truth", "files_used"])
        for i, r in enumerate(rows):
            row_files = r.get("files_used", ",".join(files_used))
            w.writerow([network, type_name, i, r["question"], r["ground_truth"], row_files])
    return out


# ===================== Main =====================

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--network", default="all", help="grid_8x8 / random / times_square / all")
    p.add_argument("--types", default="all", help="comma-separated type names, or 'all'")
    args = p.parse_args()

    networks = NETWORKS if args.network == "all" else [args.network]
    if args.types == "all":
        type_names = list(QUESTION_TYPES.keys())
    else:
        type_names = args.types.split(",")
        bad = [t for t in type_names if t not in QUESTION_TYPES]
        if bad:
            print(f"ERROR: unknown types {bad}", file=sys.stderr)
            sys.exit(1)

    total_files = 0
    for net in networks:
        print(f"\n=== {net} ===")
        for t in type_names:
            spec = QUESTION_TYPES[t]
            try:
                rows = spec["fn"](net)
            except Exception as exc:
                print(f"  FAIL {t}: {type(exc).__name__}: {exc}", file=sys.stderr)
                raise
            if not rows:
                print(f"  {t}: SKIP (no data for {net})")
                continue
            out = write_csv(net, t, rows, spec["files"])
            total_files += 1
            print(f"  {t} ({spec['kind']}, files={spec['files']}) -> {out.name} ({len(rows)} rows)")
    print(f"\nDone. {total_files} CSV files in {QA_DIR}")


if __name__ == "__main__":
    main()
