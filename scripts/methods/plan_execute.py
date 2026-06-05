"""
Setup: Plan-Execute (PE).

Two-phase approach:
  Phase 1 — The LLM receives file paths (not content) and produces a
            step-by-step reasoning plan WITHOUT tool access.
  Phase 2 — The plan is fed back and the LLM executes it using the
            `run_python` tool in a persistent Python session.

This tests whether explicit planning before code execution improves
accuracy on cross-file traffic QA, compared to the freestyle `react`
condition.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import DEFAULT_MODEL, FILE_PATHS, get_client
from .react import (
    PersistentPython, TOOLS, FILE_DESCRIPTIONS,
    _format_feedback, CODE_TIMEOUT,
)


PLAN_MAX_TOKENS = 1024
MAX_TOKENS = 4096
MAX_EXEC_TURNS = 10


PLAN_PROMPT = """\
You are an expert in traffic network analysis specializing in SUMO simulations.

You will be given a question about SUMO simulation data. Your task is to \
create a detailed step-by-step plan for answering this question using Python \
code. Do NOT execute any code — only plan.

Time convention: the simulation runs from 0 to 3600 seconds, divided into \
six 10-minute periods (first: 0-600s, second: 600-1200s, ..., sixth: 3000-3600s).

Files available for this question (you will use these paths when executing the plan):
{file_paths}

Create a numbered plan that specifies:
1. Which file(s) to read and what to extract from each
2. What data structures to build (e.g., dictionaries, graphs)
3. What computations or algorithms to apply
4. How to combine results if multiple files are involved
5. What the expected output format should be

Be specific about XML element names, attribute names, and any edge cases \
to handle (e.g., internal edges starting with ':' should be skipped)."""

EXECUTE_PROMPT = """\
You are an expert in traffic network analysis specializing in SUMO simulations.

You have access to a `run_python` tool that executes Python code in a persistent session.
Variables and imports from previous calls are preserved.
Available: Python standard library only.

Time convention: the simulation runs from 0 to 3600 seconds, divided into \
six 10-minute periods (first: 0-600s, second: 600-1200s, ..., sixth: 3000-3600s).

Files available for this question (use the provided paths to read them with Python):
{file_paths}

You previously created the following plan for answering this question. \
Execute it step by step:

--- PLAN ---
{plan}
--- END PLAN ---

Follow the plan closely. If you encounter an error or discover the plan \
needs adjustment, adapt accordingly.
Once you obtain a definitive answer from code execution, respond immediately \
with ONLY the final value. Nothing else.
If multiple answers are tied, report ALL of them.
If no answer exists, respond with 'None'."""


def _build_file_paths_block(network: str, files_used: list[str]) -> str:
    lines = []
    for f in files_used:
        path = str(FILE_PATHS[f][network].resolve())
        desc = FILE_DESCRIPTIONS[f]
        lines.append(f"  {f}: {path}\n    {desc}")
    return "\n".join(lines)


def ask(network: str, question: str, files_used: list[str],
        model: str = DEFAULT_MODEL) -> str:
    client = get_client()
    file_paths_block = _build_file_paths_block(network, files_used)

    # ── Phase 1: Planning (single turn, no tools) ──
    plan_system = [{
        "type": "text",
        "text": PLAN_PROMPT.format(file_paths=file_paths_block),
        "cache_control": {"type": "ephemeral"},
    }]
    plan_response = client.messages.create(
        model=model,
        max_tokens=PLAN_MAX_TOKENS,
        system=plan_system,
        messages=[{"role": "user", "content": f"Question: {question}"}],
    )
    plan_text = plan_response.content[0].text if plan_response.content else ""

    trace: list[dict] = [{"role": "plan", "text": plan_text}]

    # ── Phase 2: Execution (agentic loop with run_python) ──
    exec_system = [{
        "type": "text",
        "text": EXECUTE_PROMPT.format(file_paths=file_paths_block, plan=plan_text),
        "cache_control": {"type": "ephemeral"},
    }]
    messages = [{"role": "user", "content": f"Question: {question}"}]

    session = PersistentPython(timeout=CODE_TIMEOUT)
    try:
        for _ in range(MAX_EXEC_TURNS):
            response = client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=exec_system,
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
