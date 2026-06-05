"""
Scaffolding condition: Verbatim XML.

The full text of each requested SUMO file is injected into the system
prompt. This is the most direct (and most token-heavy) way to expose
file content; it serves as a controlled baseline that mirrors prior
work (TrafficNetQA).

Files for each question are routed via the `files_used` argument coming
from the QA CSV — one of:
  ["net"], ["rou"], ["tripinfo"], ["edgedata"]
or cross-file combinations such as ["net", "rou"] or ["rou", "edgedata"].

The system prompt only includes structural hints for files that are
present, to avoid biasing the LLM with descriptions of files it cannot
see.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import DEFAULT_MODEL, FILE_PATHS, get_client

MAX_TOKENS = 1024

# Per-file structural hints. We only inject hints for the files actually
# included in this prompt (so the LLM is not primed about files it
# cannot read).
FILE_HINTS = {
    "net": """SUMO .net.xml structure:
- <edge id="..." from="junction_id" to="junction_id"> contains <lane> elements
- <lane id="..." length="..." speed="..."/> defines lane properties
- <junction id="..." type="..." x="..." y="..."/> defines junction properties
- Edges with IDs starting with ':' are internal (junction) edges — ignore them
- Junction types include: traffic_light, priority, right_before_left, dead_end""",
    "rou": """SUMO .rou.xml structure:
- <vehicle id="..." depart="..." type="..."> contains <route edges="space-separated edge ids"/>
- vType ids are "electric" or "gasoline" in this benchmark""",
    "tripinfo": """SUMO tripinfo.xml structure:
- <tripinfo id="..." depart="..." arrival="..." duration="..." routeLength="..." departLane="..." waitingTime="..."/>
- Vehicles that did not arrive within the simulation are absent.""",
    "edgedata": """SUMO edgedata (netstate) structure:
- <interval begin="..." end="..."> contains <edge id="..." sampledSeconds="..." density="..." speed="..." entered="..."/>
- Six 10-minute intervals cover [0,3600]: first=[0,600], second=[600,1200], ..., sixth=[3000,3600]
- 'speed' is mean speed in m/s; 'sampledSeconds' is total vehicle-seconds; 'entered' is the count of vehicles that entered the edge in that interval.""",
}

FILE_HINTS["fcd"] = """SUMO FCD (Floating Car Data) structure:
- <timestep time="..."> contains <vehicle id="..." speed="..." pos="..." lane="..." type="..."/>
- lane format: edgeID_laneIndex; pos is meters along the lane from start
- One timestep per second (0.00 to 3599.00)"""
FILE_HINTS["add"] = """SUMO traffic light additional file:
- <tlLogic id="..." type="..." programID="..."> with <phase duration="..." state="..."/>
- <connection from="..." to="..." tl="..." linkIndex="..."/> maps edges to their controlling TLS"""

FILE_HEADERS = {
    "net": "Network file (net.xml):",
    "rou": "Route / demand file (rou.xml):",
    "tripinfo": "Trip info file (tripinfo.xml):",
    "edgedata": "Edge data file (netstate.xml):",
    "fcd": "FCD file (fcd.xml):",
    "add": "Traffic light definitions (tls.add.xml):",
}

for _si in range(5):
    FILE_HINTS[f"fcd_s{_si}"] = FILE_HINTS["fcd"]
    FILE_HINTS[f"rou_s{_si}"] = FILE_HINTS["rou"]
    FILE_HINTS[f"tripinfo_s{_si}"] = FILE_HINTS["tripinfo"]
    FILE_HEADERS[f"fcd_s{_si}"] = FILE_HEADERS["fcd"]
    FILE_HEADERS[f"rou_s{_si}"] = FILE_HEADERS["rou"]
    FILE_HEADERS[f"tripinfo_s{_si}"] = FILE_HEADERS["tripinfo"]

BASE_PROMPT = """You are an expert in traffic network analysis specializing in SUMO simulations.
You are given the raw content of one or more SUMO files and a question about the simulation.

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
        path = FILE_PATHS[f][network]
        content = path.read_text(encoding="utf-8")
        blocks.append(f"{FILE_HEADERS[f]}\n{content}")
    file_blocks = "\n\n".join(blocks)
    return BASE_PROMPT.format(file_hints=hints, file_blocks=file_blocks)


def ask(network: str, question: str, files_used: list[str],
        model: str = DEFAULT_MODEL) -> str:
    client = get_client()
    system_text = _build_system_prompt(network, files_used)
    try:
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
    except Exception as e:
        err = str(e).lower()
        if any(k in err for k in ("too long", "too many", "token",
                                   "maximum size", "request_too_large", "413")):
            return "n/a"
        raise
    return response.content[0].text.strip()
