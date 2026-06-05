"""
Setup: Code execution (ReAct).

The LLM receives only file *paths* (not file content) and a `run_python`
tool. It reads and analyzes the files via Python (standard library only)
on demand, with no upfront plan and no plan revision.

This corresponds to the agent-style deployment used by production
LLM-SUMO systems (ChatSUMO, SUMO-MCP, etc.) where files are not pumped
into the prompt; the agent fetches what it needs.
"""

import io
import json
import sys
import threading
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import DEFAULT_MODEL, FILE_PATHS, get_client


CODE_TIMEOUT = 60
MAX_TURNS = 10
MAX_TOKENS = 4096


# ---------- File path hints (per files_used) ----------

FILE_DESCRIPTIONS = {
    "net": "SUMO network file (.net.xml). Contains <edge>, <lane>, <junction>, <connection>. "
           "Edges with IDs starting with ':' are internal junction edges.",
    "rou": "Vehicle demand file (.rou.xml). Each <vehicle> has id, depart (seconds), type "
           "(electric or gasoline), and a <route edges='space-separated edge ids'/>.",
    "tripinfo": "Per-vehicle trip outcome (tripinfo.xml). Attributes include depart, arrival, "
                "duration, routeLength, departLane, waitingTime. Vehicles that did not arrive "
                "within the simulation are absent.",
    "edgedata": "Per-edge per-period traffic data (netstate.xml). Six <interval> blocks cover "
                "[0,3600] in 600s steps. Each <edge> has sampledSeconds, density, speed (m/s), "
                "entered. The six periods are named first/second/.../sixth.",
}

FILE_DESCRIPTIONS["fcd"] = (
    "Floating Car Data (fcd.xml). <timestep time='...'> contains <vehicle> "
    "elements with id, speed (m/s), pos (meters along lane), lane (format: "
    "edgeID_laneIndex), type, angle, slope."
)
FILE_DESCRIPTIONS["add"] = (
    "Traffic light signal definitions (tls.add.xml). Contains <tlLogic id='...' "
    "type='...' programID='...'> with child <phase duration='...' state='...'/>, "
    "and <connection from='...' to='...' tl='...' linkIndex='...'> showing which "
    "edges/lanes are controlled by each traffic light."
)

for _si in range(5):
    FILE_DESCRIPTIONS[f"rou_s{_si}"] = FILE_DESCRIPTIONS["rou"]
    FILE_DESCRIPTIONS[f"tripinfo_s{_si}"] = FILE_DESCRIPTIONS["tripinfo"]
    FILE_DESCRIPTIONS[f"fcd_s{_si}"] = FILE_DESCRIPTIONS["fcd"]
    FILE_DESCRIPTIONS[f"add_s{_si}"] = FILE_DESCRIPTIONS["add"]

BASE_PROMPT = """You are an expert in traffic network analysis specializing in SUMO simulations.

You have access to a `run_python` tool that executes Python code in a persistent session.
Variables and imports from previous calls are preserved.
Available: Python standard library only.

Time convention: the simulation runs from 0 to 3600 seconds, divided into six 10-minute periods (first: 0-600s, second: 600-1200s, ..., sixth: 3000-3600s).

Files available for this question (use the provided paths to read them with Python):
{file_paths}

Once you obtain a definitive answer from code execution, respond immediately with ONLY the final value. Nothing else.
If multiple answers are tied, report ALL of them.
If no answer exists, respond with 'None'.
"""

TOOLS = [
    {
        "name": "run_python",
        "description": "Execute Python code in a persistent session. Variables from previous "
                       "calls are preserved. Available: Python standard library.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"}
            },
            "required": ["code"],
        },
    }
]

ERROR_HINTS = {
    "NameError": "A variable or function was used before being defined. Check spelling, or make sure to define all variables within this code block.",
    "ModuleNotFoundError": "Only the Python standard library is available.",
    "FileNotFoundError": "Check the file path. Use the path provided in the system prompt.",
    "SyntaxError": "Python syntax error. Check indentation, brackets, or quotes.",
}


def _format_feedback(stdout: str, stderr: str) -> str:
    """Format stdout/stderr with structured error hints."""
    result = ""
    if stdout:
        result += f"stdout:\n{stdout}"
    if stderr:
        if result:
            result += "\n"
        result += f"stderr:\n{stderr}"
        if "timeout" in stderr.lower():
            result += "\nHint: Code exceeded the time limit. Consider a more efficient algorithm or smaller scope."
        else:
            for error_type, hint in ERROR_HINTS.items():
                if error_type in stderr:
                    result += f"\nHint: {hint}"
                    break
    if not result:
        result = "(no output)"
    return result


class PersistentPython:
    """Persistent Python session that preserves variables across calls."""

    def __init__(self, timeout: int = 60):
        self.timeout = timeout
        self._globals: dict = {}

    def run(self, code: str) -> tuple[str, str]:
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        def _exec():
            try:
                with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                    exec(compile(code, "<react>", "exec"), self._globals)
            except Exception as e:
                stderr_buf.write(f"{type(e).__name__}: {e}\n")

        t = threading.Thread(target=_exec, daemon=True)
        t.start()
        t.join(timeout=self.timeout)

        if t.is_alive():
            return stdout_buf.getvalue().strip(), "timeout"
        return stdout_buf.getvalue().strip(), stderr_buf.getvalue().strip()

    def close(self):
        self._globals.clear()


def _build_system_prompt(network: str, files_used: list[str]) -> str:
    lines = []
    for f in files_used:
        path = str(FILE_PATHS[f][network].resolve())
        desc = FILE_DESCRIPTIONS[f]
        lines.append(f"  {f}: {path}\n    {desc}")
    file_paths_block = "\n".join(lines)
    return BASE_PROMPT.format(file_paths=file_paths_block)


def ask(network: str, question: str, files_used: list[str],
        model: str = DEFAULT_MODEL) -> str:
    client = get_client()
    system_text = _build_system_prompt(network, files_used)
    system = [{
        "type": "text",
        "text": system_text,
        "cache_control": {"type": "ephemeral"},
    }]

    trace: list[dict] = []
    messages = [{"role": "user", "content": f"Question: {question}"}]

    session = PersistentPython(timeout=CODE_TIMEOUT)
    try:
        for _ in range(MAX_TURNS):
            response = client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=messages,
                tools=TOOLS,
            )
            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            for block in assistant_content:
                if block.type == "text":
                    trace.append({"role": "assistant", "text": block.text})
                elif block.type == "tool_use":
                    trace.append({"role": "tool_call", "name": block.name,
                                  "code": block.input.get("code", "")})

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason == "max_tokens":
                has_tool_use = any(b.type == "tool_use" for b in assistant_content)
                if has_tool_use:
                    tool_results = []
                    for block in assistant_content:
                        if block.type == "tool_use":
                            trace.append({"role": "execution",
                                          "stdout": "",
                                          "stderr": "max_tokens reached, code truncated"})
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": "Error: response was truncated (max_tokens). Try a shorter approach.",
                                "is_error": True,
                            })
                    messages.append({"role": "user", "content": tool_results})
                    continue
                else:
                    break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in assistant_content:
                    if block.type == "tool_use":
                        code = block.input.get("code", "")
                        stdout, stderr = session.run(code)
                        trace.append({"role": "execution", "stdout": stdout, "stderr": stderr})
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": _format_feedback(stdout, stderr),
                        })
                messages.append({"role": "user", "content": tool_results})
    finally:
        session.close()

    return json.dumps(trace, ensure_ascii=False)
