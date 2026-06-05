"""
Scaffolding condition: JSON view.

Each required SUMO file is rendered as JSONL --- one JSON record per
line --- and injected into the system prompt. For net.xml the JSON
view additionally exposes pre-computed adjacency (outgoing_edges,
neighbor_junctions, next_edges).

Files are read from data/preprocessed/<network>_<file>.jsonl, pre-built
once by scripts/build_jsonl.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import DEFAULT_MODEL, get_client

PREP_DIR = Path(__file__).resolve().parents[2] / "data" / "preprocessed"

MAX_TOKENS = 1024

FILE_HINTS = {
    "net": """Network (net.xml) view: JSONL with two record kinds.
- Junctions: {"_kind":"junction", "id":..., "x":..., "y":..., "type":..., "outgoing_edges":[...], "neighbor_junctions":[...]}
- Edges: {"_kind":"edge", "id":..., "from":..., "to":..., "length":..., "speed":..., "lanes":..., "type":..., "next_edges":[...]}
- 'outgoing_edges' / 'next_edges' are pre-extracted adjacency.""",
    "rou": """Demand (rou.xml) view: JSONL with one vehicle per line.
- {"id":..., "depart":..., "type":..., "route":[edge_ids]}""",
    "tripinfo": """Trip info view: JSONL with one trip per line.
- {"id":..., "depart":..., "arrival":..., "duration":..., "route_length":..., "depart_lane":..., "waiting_time":...}
- Vehicles that did not arrive are absent.""",
    "edgedata": """Edge data view: JSONL with one (edge, period) record per line.
- {"edge":..., "period":..., "sampledSeconds":..., "density":..., "speed":..., "entered":...}
- 'period' is one of first/second/.../sixth; the simulation has six 10-minute periods covering [0, 3600] seconds. 'speed' is null if no traffic.""",
}

FILE_HINTS["fcd"] = """FCD (Floating Car Data) view: JSONL with one vehicle-observation per line.
- {"time":..., "id":..., "lane":..., "pos":..., "speed":..., "type":...}
- lane format: edgeID_laneIndex; pos is meters along lane from start"""
FILE_HINTS["add"] = """Traffic light view: JSONL with signal program and connection records.
- {"_kind":"tlLogic", "id":..., "type":..., "phases":[{"duration":..., "state":...}]}
- {"_kind":"connection", "from":..., "to":..., "tl":..., "linkIndex":...}"""

FILE_HEADERS = {
    "net": "Network (net.xml):",
    "rou": "Demand (rou.xml):",
    "tripinfo": "Trip info (tripinfo.xml):",
    "edgedata": "Edge data (netstate.xml):",
    "fcd": "FCD (fcd.xml):",
    "add": "Traffic lights (tls.add.xml):",
}

for _si in range(5):
    FILE_HINTS[f"fcd_s{_si}"] = FILE_HINTS["fcd"]
    FILE_HINTS[f"rou_s{_si}"] = FILE_HINTS["rou"]
    FILE_HINTS[f"tripinfo_s{_si}"] = FILE_HINTS["tripinfo"]
    FILE_HEADERS[f"fcd_s{_si}"] = FILE_HEADERS["fcd"]
    FILE_HEADERS[f"rou_s{_si}"] = FILE_HEADERS["rou"]
    FILE_HEADERS[f"tripinfo_s{_si}"] = FILE_HEADERS["tripinfo"]

BASE_PROMPT = """You are an expert in traffic network analysis specializing in SUMO simulations.
You are given one or more SUMO files rendered as JSONL (one JSON object per line) and a question about the simulation.

Time convention: the simulation runs from 0 to 3600 seconds, divided into six 10-minute periods (first: 0-600s, second: 600-1200s, ..., sixth: 3000-3600s).

{file_hints}

Answer the question with ONLY the final value. Do NOT explain your reasoning. Do NOT show your work.
If multiple answers are tied, report ALL of them.
If no answer exists, respond with 'None'.

{file_blocks}"""


def _build_system_prompt(network: str, files_used: list[str]) -> str:
    hints = "\n\n".join(FILE_HINTS[f] for f in files_used)
    blocks = []
    for f in files_used:
        view = (PREP_DIR / f"{network}_{f}.jsonl").read_text(encoding="utf-8")
        blocks.append(f"{FILE_HEADERS[f]}\n\n{view}")
    file_blocks = "\n\n".join(blocks)
    return BASE_PROMPT.format(file_hints=hints, file_blocks=file_blocks)


def ask(network: str, question: str, files_used: list[str],
        model: str = DEFAULT_MODEL) -> str:
    client = get_client()
    system_text = _build_system_prompt(network, files_used)
    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=[{
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": f"Question: {question}"}],
    )
    return response.content[0].text.strip()
