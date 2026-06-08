#!/usr/bin/env python3
"""
Run SUMO simulations to (re)generate the simulation-output files
(tripinfo, fcd) from the existing network and route files.

Every route scenario in configuration_files/rou/ is simulated — the base
{network}.rou.xml and the seed variants {network}_s0..s4.rou.xml — writing:
  SUMO_dataset/output_files/tripinfo/{tag}_tripinfo.xml
  SUMO_dataset/output_files/fcd/{tag}_fcd.xml
(18 files each in total).

All scenarios use the traffic-signal logic embedded in the network. The base
scenario runs with SUMO seed 42 and variant _sN with seed 42+N, matching the
pipeline that produced the original dataset.

Auxiliary SUMO files (sumocfg, edgeData dumps, vehicle_types.add.xml) go to a
scratch dir at SUMO_dataset/output_files/_work/.

Settings: 0-3600s, fcd-output with geo coordinates,
device.emissions.probability=1.0. Exact reproduction of the published
outputs requires SUMO 1.25.0.
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree

# ── Paths ──
# Reuse the canonical dataset path constants from scripts/utils.py so this
# script stays in lockstep with the rest of the repo. utils.py imports only
# pathlib at module top (get_client is lazy), so importing it has no side effects.
sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from utils import NET_DIR, ROU_DIR, TRIPINFO_DIR, FCD_DIR  # noqa: E402

NETWORK_DIR = NET_DIR                          # configuration_files/net  (inputs)
ROUTE_DIR = ROU_DIR                            # configuration_files/rou  (base .rou.xml output)
WORK_DIR = TRIPINFO_DIR.parent / "_work"       # output_files/_work  (gitignored scratch)
# tripinfo / fcd are written to their own official dirs: TRIPINFO_DIR, FCD_DIR.

# ── SUMO tool/binary paths (resolved from $SUMO_HOME) ──
SUMO_HOME = os.environ.get("SUMO_HOME")
if not SUMO_HOME:
    raise RuntimeError("Set $SUMO_HOME to your SUMO installation directory.")

def _binary(name: str) -> str:
    return os.path.join(SUMO_HOME, "bin", name)

# ── Simulation settings ──
SEED = 42
BEGIN = 0               # first vehicle depart time (s)
END = 3600              # last vehicle depart time (s)
DURATION = 3600         # total simulated time (s)
EDGEDATA_FREQ = 600     # 10-minute aggregation window



def run_simulation(net_file: Path, route_file: Path,
                   tripinfo_dir: Path, fcd_dir: Path, work_dir: Path, tag: str,
                   seed: int = SEED):
    """
    Run SUMO simulation.

    The two published outputs (tripinfo, fcd) are written to their own official
    directories via absolute paths. All auxiliary artifacts (edgeData netstate
    dumps, additional.add.xml, vehicle_types.add.xml, sumocfg) go to a scratch
    work_dir so they do not pollute the published dataset directories.

    Traffic signals: all scenarios use the <tlLogic> definitions embedded in
    the network.
    """
    tripinfo_dir.mkdir(parents=True, exist_ok=True)
    fcd_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    # ── Output filenames ──
    # Published outputs -> absolute paths into their separate official dirs.
    tripinfo_file = str((tripinfo_dir / f"{tag}_tripinfo.xml").absolute())
    fcd_file = str((fcd_dir / f"{tag}_fcd.xml").absolute())
    # Auxiliary edgeData dumps -> scratch (not one of the 5 published types).
    netstate_file = str((work_dir / f"{tag}_netstate.xml").absolute())
    netstate_emission_file = str((work_dir / f"{tag}_netstate_emission.xml").absolute())

    # ── vehicle_types.add.xml: the 2-vType setup (electric / gasoline) used by
    # the routes. Written once into the scratch dir if not already present.
    vtype_dst = work_dir / "vehicle_types.add.xml"
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
    add_file = work_dir / f"{tag}_additional.add.xml"
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
    cfg_file = work_dir / f"{tag}.sumocfg"
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
        "--seed", str(seed),
        "--device.emissions.probability", "1.0",
        "--no-warnings",
    ]
    print(f"  SUMO: duration={DURATION}s ...")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(work_dir), timeout=600)

    if result.returncode != 0:
        print(f"  WARNING SUMO stderr: {result.stderr[:500]}")
    else:
        print(f"  Simulation completed successfully")

    # Report outputs (these are now absolute path strings)
    for fpathstr in [tripinfo_file, fcd_file, netstate_file, netstate_emission_file]:
        fpath = Path(fpathstr)
        if fpath.exists():
            size_mb = fpath.stat().st_size / (1024 * 1024)
            print(f"    {fpath.name}: {size_mb:.1f} MB")
        else:
            print(f"    {fpath.name}: NOT FOUND")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate trips and run SUMO simulations.")
    parser.add_argument("--network", default=None, help="Network name (e.g. times_square). If not specified, runs all networks.")
    args = parser.parse_args()

    scenarios = sorted(ROUTE_DIR.glob("*.rou.xml"))
    if args.network:
        scenarios = [r for r in scenarios
                     if r.stem.removesuffix(".rou") == args.network
                     or r.stem.startswith(args.network + "_s")]
    if not scenarios:
        print("ERROR: No route scenarios found in", ROUTE_DIR,
              f"for network {args.network!r}" if args.network else "")
        return 1

    print(f"Found {len(scenarios)} route scenario(s): "
          f"{[r.stem.removesuffix('.rou') for r in scenarios]}")
    print(f"Settings: begin={BEGIN}, end={END}, duration={DURATION}")

    TRIPINFO_DIR.mkdir(parents=True, exist_ok=True)
    FCD_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    for route_file in scenarios:
        tag = route_file.stem.removesuffix(".rou")  # e.g. grid_8x8, grid_8x8_s0
        m = re.match(r"^(.+)_s(\d+)$", tag)
        if m:                                       # seed variant scenario
            net_name = m.group(1)
            seed = SEED + int(m.group(2))
        else:                                       # base scenario
            net_name, seed = tag, SEED

        net_file = NETWORK_DIR / f"{net_name}.net.xml"
        if not net_file.exists():
            print(f"ERROR: Network file not found: {net_file}")
            return 1

        print(f"\n{'='*60}")
        print(f"Scenario: {tag} (network={net_name}, seed={seed})")
        print(f"{'='*60}")

        # Run SUMO on the existing network + route files to produce tripinfo/fcd.
        # The route file is an INPUT and is not regenerated.
        run_simulation(net_file, route_file, TRIPINFO_DIR, FCD_DIR,
                       WORK_DIR / tag, tag, seed=seed)

    print(f"\n{'='*60}")
    print("All done!")
    print(f"  (routes read from: {ROUTE_DIR})")
    print(f"  Tripinfo: {TRIPINFO_DIR}")
    print(f"  FCD:      {FCD_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
