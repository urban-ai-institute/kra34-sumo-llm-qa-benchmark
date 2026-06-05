"""
Shared utilities: file paths, model name, Anthropic client.

Path conventions:
  data/network/<net>.net.xml             — SUMO network
  data/network/<net>_adjacency.json      — pre-computed adjacency view (used by Preprocessed scaffolding)
  data/network/<net>_tls.add.xml         — traffic light signal definitions
  data/trips/<net>.rou.xml               — vehicle demand
  data/output/<net>_tripinfo.xml         — per-vehicle trip outcomes
  data/output/<net>_fcd.xml              — floating car data (per-timestep vehicle positions)

`FILE_PATHS` maps question-CSV `files_used` tags to network→Path dicts so
that scaffolding methods can route inputs by tag.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from agentsumo import AgentSUMOConfig

import anthropic

DATA_DIR = Path(__file__).parent.parent / "data"
NETWORK_DIR = DATA_DIR / "network"
TRIPS_DIR = DATA_DIR / "trips"
OUTPUT_DIR = DATA_DIR / "output"

NETWORKS = ["grid_8x8", "random", "random_large", "times_square"]

NET_FILES = {n: NETWORK_DIR / f"{n}.net.xml" for n in NETWORKS}
ADJ_FILES = {n: NETWORK_DIR / f"{n}_adjacency.json" for n in NETWORKS}
ROUTE_FILES = {n: TRIPS_DIR / f"{n}.rou.xml" for n in NETWORKS}
TRIPINFO_FILES = {n: OUTPUT_DIR / f"{n}_tripinfo.xml" for n in NETWORKS}
# Map question 'files_used' tags to filesystem paths.
FILE_PATHS = {
    "net": NET_FILES,
    "rou": ROUTE_FILES,
    "tripinfo": TRIPINFO_FILES,
}

FCD_FILES = {n: OUTPUT_DIR / f"{n}_fcd.xml" for n in NETWORKS}
FILE_PATHS["fcd"] = FCD_FILES
TLS_ADD_FILES = {n: NETWORK_DIR / f"{n}_tls.add.xml" for n in NETWORKS}
FILE_PATHS["add"] = TLS_ADD_FILES

for _si in range(5):
    FILE_PATHS[f"rou_s{_si}"] = {n: TRIPS_DIR / f"{n}_s{_si}.rou.xml" for n in NETWORKS}
    FILE_PATHS[f"tripinfo_s{_si}"] = {n: OUTPUT_DIR / f"{n}_s{_si}_tripinfo.xml" for n in NETWORKS}
    FILE_PATHS[f"fcd_s{_si}"] = {n: OUTPUT_DIR / f"{n}_s{_si}_fcd.xml" for n in NETWORKS}
    FILE_PATHS[f"add_s{_si}"] = {n: NETWORK_DIR / f"{n}_s{_si}_tls.add.xml" for n in NETWORKS}

DEFAULT_MODEL = "claude-sonnet-4-6"


def get_client():
    """Return a cross-provider client with an Anthropic-compatible
    `messages.create` interface. Dispatches by model name (claude*/gpt*/gemini*)."""
    from llm_client import get_unified_client
    return get_unified_client()
