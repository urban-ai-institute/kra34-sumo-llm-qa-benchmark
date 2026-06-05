"""
Scaffolding condition: Tool-Use with explicit routing.

Same as the `tool` condition — the LLM receives file paths and a
`run_python` tool — but after each execution round a separate router
call decides whether to continue coding or terminate with the answer.

This tests whether an explicit "stop or continue" gate improves
accuracy compared to the freestyle `tool` condition where the LLM
implicitly decides via stop_reason.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import DEFAULT_MODEL, FILE_PATHS, get_client
from .tool_use import (
    PersistentPython, TOOLS, FILE_DESCRIPTIONS,
    _format_feedback, CODE_TIMEOUT,
)


MAX_TOKENS = 4096
ROUTER_MAX_TOKENS = 2048
MAX_ROUNDS = 3
MAX_EXEC_SUB_TURNS = 3


# =====================================================================
# Executor prompt (same as tool condition)
# =====================================================================

EXEC_PROMPT = """\
You are an expert in traffic network analysis specializing in SUMO simulations.

You have access to a `run_python` tool that executes Python code in a \
persistent session. Variables and imports from previous calls are preserved.
Available: Python standard library only.

Time convention: the simulation runs from 0 to 3600 seconds, divided into \
six 10-minute periods (first: 0-600s, second: 600-1200s, ..., sixth: 3000-3600s).

Files available for this question (use the provided paths to read them with Python):
{file_paths}

Once you obtain a definitive answer from code execution, respond immediately \
with ONLY the final value. Nothing else.
If multiple answers are tied, report ALL of them.
If no answer exists, respond with 'None'."""


# =====================================================================
# Router
# =====================================================================

ROUTER_PROMPT = """\
You are a routing agent for a traffic network analysis task. After each \
round of code execution, you decide whether to continue or stop.

Question being answered:
{question}

Execution history so far:
{execution_history}

Choose exactly ONE action by calling the corresponding tool:
- continue_execution: The question is not yet answered or the result needs \
verification. More code execution is needed.
- terminate: The question has been definitively answered. Provide the final answer."""

ROUTER_TOOLS = [
    {
        "name": "continue_execution",
        "description": "More code execution is needed to answer the question.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why more execution is needed",
                }
            },
            "required": ["reason"],
        },
    },
    {
        "name": "terminate",
        "description": "The question has been definitively answered.",
        "input_schema": {
            "type": "object",
            "properties": {
                "final_answer": {
                    "type": "string",
                    "description": "The final answer to the question",
                }
            },
            "required": ["final_answer"],
        },
    },
]


# =====================================================================
# Helpers
# =====================================================================

def _build_file_paths_block(network: str, files_used: list[str]) -> str:
    lines = []
    for f in files_used:
        path = str(FILE_PATHS[f][network].resolve())
        desc = FILE_DESCRIPTIONS[f]
        lines.append(f"  {f}: {path}\n    {desc}")
    return "\n".join(lines)


def _format_execution_history(trace: list[dict]) -> str:
    if not trace:
        return "(no execution history yet)"
    lines = []
    for entry in trace:
        role = entry["role"]
        if role == "tool_call":
            preview = entry["code"][:120].replace("\n", " ")
            lines.append(f"[Code] {preview}...")
        elif role == "execution":
            stdout = (entry.get("stdout") or "")[:200]
            stderr = (entry.get("stderr") or "")[:200]
            if stderr:
                lines.append(f"[Result] stdout={stdout} | stderr={stderr}")
            elif stdout:
                lines.append(f"[Result] {stdout}")
            else:
                lines.append("[Result] (no output)")
        elif role == "assistant":
            text = (entry.get("text") or "")[:150]
            lines.append(f"[Assistant] {text}")
        elif role == "router":
            lines.append(f"[Router] {entry['action']}: {entry.get('reasoning', '')}")
    return "\n".join(lines)


# =====================================================================
# Main
# =====================================================================

def ask(network: str, question: str, files_used: list[str],
        model: str = DEFAULT_MODEL, max_rounds: int = MAX_ROUNDS) -> str:
    client = get_client()
    file_paths_block = _build_file_paths_block(network, files_used)
    trace: list[dict] = []

    exec_system = [{
        "type": "text",
        "text": EXEC_PROMPT.format(file_paths=file_paths_block),
        "cache_control": {"type": "ephemeral"},
    }]

    executor_messages: list[dict] = []
    session = PersistentPython(timeout=CODE_TIMEOUT)

    try:
        for _round in range(max_rounds):
            # ── Execution sub-loop ──
            step_messages = [
                {"role": "user",
                 "content": f"Question: {question}"}
            ] if not executor_messages else []

            if not step_messages:
                step_messages = [
                    {"role": "user",
                     "content": "Continue working on the question. "
                                "Write more code if needed."}
                ]

            for _sub in range(MAX_EXEC_SUB_TURNS):
                response = client.messages.create(
                    model=model,
                    max_tokens=MAX_TOKENS,
                    system=exec_system,
                    messages=executor_messages + step_messages,
                    tools=TOOLS,
                )
                assistant_content = response.content
                step_messages.append({"role": "assistant",
                                      "content": assistant_content})

                for block in assistant_content:
                    if block.type == "text":
                        trace.append({"role": "assistant", "text": block.text})
                    elif block.type == "tool_use":
                        trace.append({"role": "tool_call", "name": block.name,
                                      "code": block.input.get("code", "")})

                if response.stop_reason == "end_turn":
                    break

                if response.stop_reason == "max_tokens":
                    has_tool = any(b.type == "tool_use"
                                   for b in assistant_content)
                    if has_tool:
                        tool_results = []
                        for block in assistant_content:
                            if block.type == "tool_use":
                                trace.append({"role": "execution",
                                              "stdout": "",
                                              "stderr": "max_tokens reached"})
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": ("Error: response was truncated "
                                                 "(max_tokens). Try shorter code."),
                                    "is_error": True,
                                })
                        step_messages.append({"role": "user",
                                              "content": tool_results})
                        continue
                    break

                if response.stop_reason == "tool_use":
                    tool_results = []
                    for block in assistant_content:
                        if block.type == "tool_use":
                            code = block.input.get("code", "")
                            stdout, stderr = session.run(code)
                            trace.append({"role": "execution",
                                          "stdout": stdout, "stderr": stderr})
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": _format_feedback(stdout, stderr),
                            })
                    step_messages.append({"role": "user",
                                          "content": tool_results})

            executor_messages.extend(step_messages)

            # ── Router call: terminate or continue? ──
            exec_history = _format_execution_history(trace)
            router_system = [{
                "type": "text",
                "text": ROUTER_PROMPT.format(
                    question=question,
                    execution_history=exec_history,
                ),
                "cache_control": {"type": "ephemeral"},
            }]

            router_response = client.messages.create(
                model=model,
                max_tokens=ROUTER_MAX_TOKENS,
                system=router_system,
                messages=[{"role": "user",
                           "content": "Decide: terminate or continue?"}],
                tools=ROUTER_TOOLS,
                tool_choice={"type": "any"},
            )

            action, action_input = None, {}
            for block in router_response.content:
                if block.type == "tool_use":
                    action = block.name
                    action_input = block.input
                    break

            if action == "terminate" or action is None:
                final = action_input.get("final_answer", "")
                reasoning = final or ""
                trace.append({"role": "router", "action": "terminate",
                              "reasoning": reasoning})
                trace.append({"role": "final_answer", "text": final})
                break

            reasoning = action_input.get("reason", "")
            trace.append({"role": "router", "action": "continue_execution",
                          "reasoning": reasoning})

    finally:
        session.close()

    return json.dumps(trace, ensure_ascii=False)
