"""
Scaffolding condition: Tool-Use with budget-aware continuation.

Same as the `tool` condition — the LLM receives file paths and a
`run_python` tool — but with a hard cap of MAX_TURNS API calls,
budget alerts, and a formatted execution trace appended to the system
prompt each turn so the model has a concise summary of prior work.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import DEFAULT_MODEL, FILE_PATHS, get_client
from .tool_use import (
    PersistentPython, TOOLS, FILE_DESCRIPTIONS,
    _format_feedback, CODE_TIMEOUT, MAX_TOKENS,
)


MAX_TURNS = 2

BASE_PROMPT = """\
You are an expert in traffic network analysis specializing in SUMO simulations.

You have access to a `run_python` tool that executes Python code in a persistent session.
Variables and imports from previous calls are preserved.
Available: Python standard library only.

Time convention: the simulation runs from 0 to 3600 seconds, divided into six 10-minute periods (first: 0-600s, second: 600-1200s, ..., sixth: 3000-3600s).

Files available for this question (use the provided paths to read them with Python):
{file_paths}

IMPORTANT: You have a LIMITED budget of {remaining} remaining API calls (including this one). Write efficient, consolidated code that does as much work as possible per call.

Once you obtain a definitive answer from code execution, respond immediately with ONLY the final value. Nothing else.
If multiple answers are tied, report ALL of them.
If no answer exists, respond with 'None'."""


def _format_execution_trace(trace: list[dict]) -> str:
    if not trace:
        return ""
    lines = ["Execution history so far:"]
    for entry in trace:
        role = entry["role"]
        if role == "tool_call":
            preview = entry["code"][:200].replace("\n", " ")
            lines.append(f"  [Code] {preview}")
        elif role == "execution":
            stdout = (entry.get("stdout") or "")[:300]
            stderr = (entry.get("stderr") or "")[:200]
            if stderr:
                lines.append(f"  [Result] stdout={stdout} | stderr={stderr}")
            elif stdout:
                lines.append(f"  [Result] {stdout}")
            else:
                lines.append("  [Result] (no output)")
        elif role == "assistant":
            text = (entry.get("text") or "")[:200]
            lines.append(f"  [Assistant] {text}")
    return "\n".join(lines) + "\n\n"


def _build_system_prompt(network: str, files_used: list[str],
                         remaining: int) -> str:
    lines = []
    for f in files_used:
        path = str(FILE_PATHS[f][network].resolve())
        desc = FILE_DESCRIPTIONS[f]
        lines.append(f"  {f}: {path}\n    {desc}")
    file_paths_block = "\n".join(lines)
    return BASE_PROMPT.format(file_paths=file_paths_block,
                              remaining=remaining)


def ask(network: str, question: str, files_used: list[str],
        model: str = DEFAULT_MODEL, max_turns: int = MAX_TURNS) -> str:
    client = get_client()
    trace: list[dict] = []
    messages = [{"role": "user", "content": f"Question: {question}"}]

    session = PersistentPython(timeout=CODE_TIMEOUT)
    try:
        for turn in range(max_turns):
            remaining = max_turns - turn
            system_text = _build_system_prompt(network, files_used,
                                               remaining)

            if remaining <= 2 and messages[-1]["role"] != "user":
                messages.append({
                    "role": "user",
                    "content": (f"WARNING: Only {remaining} API call(s) remaining. "
                                "Compute the final answer NOW."),
                })

            system = [{
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }]

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
