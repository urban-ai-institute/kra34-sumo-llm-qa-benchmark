"""
Shared utilities: file paths, model name, Anthropic client.

Path conventions:
  SUMO_dataset/configuration_files/net/<net>.net.xml      — SUMO network
  SUMO_dataset/configuration_files/add/<net>_tls.add.xml  — traffic light signal definitions
  SUMO_dataset/configuration_files/rou/<net>.rou.xml      — vehicle demand
  SUMO_dataset/output_files/tripinfo/<net>_tripinfo.xml   — per-vehicle trip outcomes
  SUMO_dataset/output_files/fcd/<net>_fcd.xml             — floating car data (per-timestep vehicle positions)

`FILE_PATHS` maps question-CSV `files_used` tags to network→Path dicts so
that setup methods can route inputs by tag.
"""

from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "SUMO_dataset"
CONFIG_DIR = DATA_DIR / "configuration_files"
NET_DIR = CONFIG_DIR / "net"
ROU_DIR = CONFIG_DIR / "rou"
ADD_DIR = CONFIG_DIR / "add"
OUTPUT_DIR = DATA_DIR / "output_files"
TRIPINFO_DIR = OUTPUT_DIR / "tripinfo"
FCD_DIR = OUTPUT_DIR / "fcd"

NETWORKS = ["grid_8x8", "random", "times_square"]

NET_FILES = {n: NET_DIR / f"{n}.net.xml" for n in NETWORKS}
ROUTE_FILES = {n: ROU_DIR / f"{n}.rou.xml" for n in NETWORKS}
TRIPINFO_FILES = {n: TRIPINFO_DIR / f"{n}_tripinfo.xml" for n in NETWORKS}
FCD_FILES = {n: FCD_DIR / f"{n}_fcd.xml" for n in NETWORKS}
TLS_ADD_FILES = {n: ADD_DIR / f"{n}_tls.add.xml" for n in NETWORKS}

# Map question 'files_used' tags to filesystem paths.
FILE_PATHS = {
    "net": NET_FILES,
    "rou": ROUTE_FILES,
    "tripinfo": TRIPINFO_FILES,
    "fcd": FCD_FILES,
    "add": TLS_ADD_FILES,
}

for _si in range(5):
    FILE_PATHS[f"rou_s{_si}"] = {n: ROU_DIR / f"{n}_s{_si}.rou.xml" for n in NETWORKS}
    FILE_PATHS[f"tripinfo_s{_si}"] = {n: TRIPINFO_DIR / f"{n}_s{_si}_tripinfo.xml" for n in NETWORKS}
    FILE_PATHS[f"fcd_s{_si}"] = {n: FCD_DIR / f"{n}_s{_si}_fcd.xml" for n in NETWORKS}
    FILE_PATHS[f"add_s{_si}"] = {n: ADD_DIR / f"{n}_s{_si}_tls.add.xml" for n in NETWORKS}

DEFAULT_MODEL = "claude-sonnet-4-6"


def get_client():
    """Return a Claude client with an Anthropic-compatible
    `messages.create` interface."""
    from llm_client import get_unified_client
    return get_unified_client()
