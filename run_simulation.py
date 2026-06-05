#!/usr/bin/env python3
"""
Generate trips and run SUMO simulations for each network in data/network/.

Uses the same settings and configuration as AgentSUMO's TripGenerator and SimulationRunner:
- randomTrips.py parameters (period, seed, validate, trip-attributes)
- duarouter with --ignore-errors
- vehicle_types.add.xml (electric, gasoline vTypes; randomly assigned per vehicle)
- additional.add.xml with edgeData (netstate + emission)
- fcd-output with geo coordinates
- device.emissions.probability=1.0

For each .net.xml file, this script:
1. Generates random trips using randomTrips.py
2. Converts trips to routes using duarouter
3. Runs SUMO simulation
4. Saves outputs to data/trips/ and data/output/
"""

import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree

# ── Paths ──
DATA_DIR = Path(__file__).parent / "data"
NETWORK_DIR = DATA_DIR / "network"
TRIPS_DIR = DATA_DIR / "trips"
OUTPUT_DIR = DATA_DIR / "output"

# ── SUMO tool/binary paths (resolved from $SUMO_HOME) ──
SUMO_HOME = os.environ.get("SUMO_HOME")
if not SUMO_HOME:
    raise RuntimeError("Set $SUMO_HOME to your SUMO installation directory.")

def _tool(name: str) -> str:
    return os.path.join(SUMO_HOME, "share", "sumo", "tools", name)

def _binary(name: str) -> str:
    return os.path.join(SUMO_HOME, "bin", name)

# ── Simulation settings ──
SEED = 42
BEGIN = 0               # first vehicle depart time (s)
END = 3600              # last vehicle depart time (s)
DURATION = 3600         # total simulated time (s)
EDGEDATA_FREQ = 600     # 10-minute aggregation window



def generate_trips(net_file: Path, trip_file: Path, route_file: Path):
    """
    Generate random trips and convert to routes.
    Mirrors TripGenerator._generate_random_od() and _generate_routes().
    """
    import sumolib

    net = sumolib.net.readNet(str(net_file))
    edge_count = len(net.getEdges())
    vehicle_count = int(edge_count * 0.8)
    period = (END - BEGIN) / vehicle_count

    # ── randomTrips.py ──
    randomTrips_path = _tool("randomTrips.py")
    temp_route = str(trip_file.parent / "temp_validate.rou.xml")

    cmd = [
        sys.executable, randomTrips_path,
        "-n", str(net_file.absolute()),
        "-o", str(trip_file.absolute()),
        "--begin", str(BEGIN),
        "--end", str(END),
        "--period", str(period),
        "--validate",
        "--route-file", temp_route,
        "--seed", str(SEED),
        "--trip-attributes",
        'departLane="free" departSpeed="random" departPos="random_free"',
    ]
    print(f"  randomTrips.py: period={period:.2f}, vehicles≈{vehicle_count}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  WARNING randomTrips stderr: {result.stderr[:500]}")

    # Clean up temp route file (same as TripGenerator)
    temp_path = Path(temp_route)
    if temp_path.exists():
        temp_path.unlink()

    if not trip_file.exists():
        raise RuntimeError(f"Trip file not created: {trip_file}")

    tree = ET.parse(str(trip_file))
    trip_count = len(tree.getroot().findall(".//trip"))
    print(f"  -> {trip_count} trips: {trip_file.name}")

    # ── duarouter ──
    duarouter_path = _binary("duarouter")
    cmd = [
        duarouter_path,
        "-n", str(net_file.absolute()),
        "-t", str(trip_file.absolute()),
        "-o", str(route_file.absolute()),
        "--ignore-errors",
    ]
    print(f"  duarouter ...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  WARNING duarouter stderr: {result.stderr[:500]}")

    if not route_file.exists():
        raise RuntimeError(f"Route file not created: {route_file}")

    # ── Assign random vType (electric / gasoline) to each vehicle ──
    # Deterministic via seed. trips.xml and rou.xml both updated.
    assign_random_vtype(trip_file, "trip")
    assign_random_vtype(route_file, "vehicle")
    print(f"  -> Routes: {route_file.name} (vType randomized: electric/gasoline)")


def generate_od_grouped_trips(net_file: Path, trip_file: Path, route_file: Path):
    """Generate trips where multiple vehicles share the same OD pair.

    Samples 15 unique (origin, destination) pairs and assigns 10-100 vehicles
    to each. Departure times are evenly spaced using a period derived from
    the total vehicle count: period = (END - BEGIN) / total_vehicles.
    Then routes with duarouter and assigns random vTypes.
    """
    import random
    import sumolib

    rng = random.Random(SEED)
    net = sumolib.net.readNet(str(net_file))
    edges = [e for e in net.getEdges() if not e.getID().startswith(":")]
    edge_ids = [e.getID() for e in edges]

    num_od_pairs = 15
    od_pairs: list[tuple[str, str]] = []
    attempts = 0
    while len(od_pairs) < num_od_pairs and attempts < 1000:
        o = rng.choice(edge_ids)
        d = rng.choice(edge_ids)
        if o != d and (o, d) not in od_pairs:
            od_pairs.append((o, d))
        attempts += 1

    net_name = net_file.stem.replace(".net", "")
    if net_name == "grid_8x8":
        od_vehicle_counts = [rng.randint(30, 150) for _ in od_pairs]
    else:
        od_vehicle_counts = [rng.randint(10, 100) for _ in od_pairs]
    total_vehicles = sum(od_vehicle_counts)
    period = (END - BEGIN) / total_vehicles

    all_trips: list[tuple[float, str, str]] = []
    for (o, d), n_vehicles in zip(od_pairs, od_vehicle_counts):
        depart_times = sorted(rng.uniform(BEGIN, END) for _ in range(n_vehicles))
        for depart in depart_times:
            all_trips.append((depart, o, d))

    all_trips.sort(key=lambda t: t[0])

    trips_root = Element("routes")
    for vid, (depart, o, d) in enumerate(all_trips):
        SubElement(trips_root, "trip", {
            "id": f"v_{vid}",
            "depart": f"{depart:.2f}",
            "from": o,
            "to": d,
            "departLane": "free",
            "departSpeed": "random",
            "departPos": "random_free",
        })

    trip_file.parent.mkdir(parents=True, exist_ok=True)
    ElementTree(trips_root).write(str(trip_file), encoding="utf-8", xml_declaration=True)
    print(f"  OD-grouped trips: {len(od_pairs)} OD pairs, {total_vehicles} vehicles "
          f"(period={period:.2f}s) -> {trip_file.name}")

    duarouter_path = _binary("duarouter")
    cmd = [
        duarouter_path,
        "-n", str(net_file.absolute()),
        "-t", str(trip_file.absolute()),
        "-o", str(route_file.absolute()),
        "--ignore-errors",
    ]
    print(f"  duarouter ...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  WARNING duarouter stderr: {result.stderr[:500]}")

    if not route_file.exists():
        raise RuntimeError(f"Route file not created: {route_file}")

    assign_random_vtype(trip_file, "trip")
    assign_random_vtype(route_file, "vehicle")
    print(f"  -> Routes: {route_file.name} (vType randomized: electric/gasoline)")


VTYPE_CHOICES = ["electric", "gasoline"]


def assign_random_vtype(xml_file: Path, element_name: str) -> None:
    """Assign a random vType to each <element_name> in an XML file.

    Deterministic: ordered by element id (or document order if id missing),
    using a fixed Random(SEED).
    """
    import random
    rng = random.Random(SEED)
    tree = ET.parse(str(xml_file))
    root = tree.getroot()
    elements = list(root.iter(element_name))
    # Sort by id for determinism (string-sort across runs).
    elements.sort(key=lambda e: e.get("id", ""))
    for el in elements:
        el.set("type", rng.choice(VTYPE_CHOICES))
    tree.write(str(xml_file), encoding="utf-8", xml_declaration=True)


def run_simulation(net_file: Path, route_file: Path, output_dir: Path, tag: str):
    """
    Run SUMO simulation.
    """
    # ── Output filenames (same pattern as SimulationRunner) ──
    tripinfo_file = f"{tag}_tripinfo.xml"
    fcd_file = f"{tag}_fcd.xml"
    netstate_file = f"{tag}_netstate.xml"
    netstate_emission_file = f"{tag}_netstate_emission.xml"

    # ── vehicle_types.add.xml: prefer the local file (NetTrafficQA-specific
    # 2-vType setup: electric / gasoline). Do NOT overwrite from external
    # source — we maintain our own version.
    vtype_dst = output_dir / "vehicle_types.add.xml"
    if not vtype_dst.exists():
        # Fallback: create inline 2-vType definition.
        vtype_content = """<additional>
    <vType id="electric" vClass="passenger"
           accel="2.5" decel="4.5" sigma="0.5" length="5.0" minGap="2.5" maxSpeed="70"
           color="0,255,0" emissionClass="Energy"/>

    <vType id="gasoline" vClass="passenger"
           accel="2.0" decel="4.0" sigma="0.5" length="5.0" minGap="2.5" maxSpeed="70"
           color="255,0,0" emissionClass="HBEFA3/PC_G_EU4"/>
</additional>
"""
        vtype_dst.write_text(vtype_content)
        print(f"  Created vehicle_types.add.xml (electric/gasoline)")

    # ── additional.add.xml (same as SimulationRunner._generate_additional_file) ──
    add_file = output_dir / f"{tag}_additional.add.xml"
    add_root = Element("additional")
    SubElement(add_root, "edgeData", {
        "id": "dump_output",
        "freq": str(EDGEDATA_FREQ),
        "file": netstate_file,
    })
    SubElement(add_root, "edgeData", {
        "id": "dump_output_emission",
        "freq": str(EDGEDATA_FREQ),
        "file": netstate_emission_file,
        "type": "emissions",
        "excludeEmpty": "true",
    })
    ElementTree(add_root).write(str(add_file), encoding="utf-8", xml_declaration=True)

    # ── sumocfg (same structure as SimulationRunner._generate_config_file) ──
    cfg_file = output_dir / f"{tag}.sumocfg"
    cfg_root = Element("configuration")

    # Input section
    input_tag = SubElement(cfg_root, "input")
    SubElement(input_tag, "net-file", {"value": str(net_file.absolute())})
    SubElement(input_tag, "route-files", {"value": str(route_file.absolute())})
    # Additional files: additional.add.xml + vehicle_types.add.xml (same as SimulationRunner line 183)
    SubElement(input_tag, "additional-files", {
        "value": ",".join([str(add_file.absolute()), str(vtype_dst.absolute())])
    })

    # Time section
    time_tag = SubElement(cfg_root, "time")
    SubElement(time_tag, "begin", {"value": "0"})
    SubElement(time_tag, "end", {"value": str(DURATION)})

    # Output section (same as SimulationRunner._generate_config_file)
    output_tag = SubElement(cfg_root, "output")
    SubElement(output_tag, "tripinfo-output", {"value": tripinfo_file})
    SubElement(output_tag, "fcd-output", {"value": fcd_file})
    SubElement(output_tag, "fcd-output.geo", {"value": "true"})  # geo coordinates (line 200)

    # Report section
    report_tag = SubElement(cfg_root, "report")
    SubElement(report_tag, "verbose", {"value": "true"})
    SubElement(report_tag, "no-step-log", {"value": "true"})

    ElementTree(cfg_root).write(str(cfg_file), encoding="utf-8", xml_declaration=True)

    # ── Run SUMO (same as SimulationRunner._run_simulation_subprocess) ──
    sumo_binary = _binary("sumo")
    cmd = [
        sumo_binary,
        "-c", str(cfg_file),
        "--seed", str(SEED),
        "--device.emissions.probability", "1.0",
        "--no-warnings",
    ]
    print(f"  SUMO: duration={DURATION}s ...")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(output_dir), timeout=600)

    if result.returncode != 0:
        print(f"  WARNING SUMO stderr: {result.stderr[:500]}")
    else:
        print(f"  Simulation completed successfully")

    # Report outputs
    for fname in [tripinfo_file, fcd_file, netstate_file, netstate_emission_file]:
        fpath = output_dir / fname
        if fpath.exists():
            size_mb = fpath.stat().st_size / (1024 * 1024)
            print(f"    {fname}: {size_mb:.1f} MB")
        else:
            print(f"    {fname}: NOT FOUND")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate trips and run SUMO simulations.")
    parser.add_argument("--network", default=None, help="Network name (e.g. times_square). If not specified, runs all networks.")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed. Generates suffixed files (_s0, _s1, ...). "
                             "Default: 42 with no suffix (backward compatible).")
    parser.add_argument("--trip-mode", default="random", choices=["random", "od_grouped"],
                        help="Trip generation mode. 'random' uses randomTrips.py; "
                             "'od_grouped' samples fixed OD pairs with 10-20 vehicles each.")
    args = parser.parse_args()

    global SEED
    if args.seed is not None:
        SEED = args.seed
        suffix = f"_s{args.seed - 42}"
    else:
        suffix = ""

    if args.network:
        net_file = NETWORK_DIR / f"{args.network}.net.xml"
        if not net_file.exists():
            print(f"ERROR: Network file not found: {net_file}")
            return 1
        net_files = [net_file]
    else:
        net_files = sorted(NETWORK_DIR.glob("*.net.xml"))
        if not net_files:
            print("ERROR: No .net.xml files found in", NETWORK_DIR)
            return 1

    print(f"Found {len(net_files)} network(s): {[f.name for f in net_files]}")
    print(f"Settings: seed={SEED}, begin={BEGIN}, end={END}, duration={DURATION}")

    TRIPS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for net_file in net_files:
        base_tag = net_file.stem.replace(".net", "")  # grid_8x8, random
        tag = base_tag + suffix
        print(f"\n{'='*60}")
        print(f"Network: {net_file.name} (tag={tag})")
        print(f"{'='*60}")

        trip_file = TRIPS_DIR / f"{tag}.trips.xml"
        route_file = TRIPS_DIR / f"{tag}.rou.xml"

        # Step 1: Generate trips & routes
        print(f"\n[1/2] Generating trips and routes (mode={args.trip_mode}) ...")
        if args.trip_mode == "od_grouped":
            generate_od_grouped_trips(net_file, trip_file, route_file)
        else:
            generate_trips(net_file, trip_file, route_file)

        # Step 2: Run simulation
        print("\n[2/2] Running simulation ...")
        run_simulation(net_file, route_file, OUTPUT_DIR, tag)

    print(f"\n{'='*60}")
    print("All done!")
    print(f"  Trips:   {TRIPS_DIR}")
    print(f"  Output:  {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
