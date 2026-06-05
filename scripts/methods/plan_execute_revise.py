"""
Setup: Plan-Execute-Revise agent.

Three-role architecture driven by a router:
  Router  — Decides the next action each turn: revise the plan,
            execute the next step, or terminate with a final answer.
  Planner — Rewrites the plan when the router detects issues.
  Executor — Runs Python code for the current plan step using
             the `run_python` tool in a persistent session.

This tests whether adaptive replanning during execution improves
accuracy compared to the one-shot `plan_execute` condition.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import DEFAULT_MODEL, get_client
from .react import (
    PersistentPython, TOOLS, FILE_DESCRIPTIONS,
    _format_feedback, CODE_TIMEOUT,
)
from .plan_execute import PLAN_PROMPT, _build_file_paths_block


PLAN_MAX_TOKENS = 1024
MAX_TOKENS = 4096
ROUTER_MAX_TOKENS = 2048
MAX_ROUTER_TURNS = 3
MAX_CONSECUTIVE_REVISE = 3
MAX_EXEC_SUB_TURNS = 3

SUBMIT_TOOL = {
    "name": "submit_answer",
    "description": "Submit the final answer. The value must be the raw answer only — "
                   "no markdown, no explanation, no extra text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "description": "The raw final answer value",
            }
        },
        "required": ["answer"],
    },
}


# =====================================================================
# Router
# =====================================================================

ROUTER_PROMPT = """\
You are a routing agent for a traffic network analysis task. Your job is to \
decide the next action based on the current state of problem-solving.

Question being answered:
{question}

Current plan (revision {revision}):
--- PLAN ---
{plan}
--- END PLAN ---

Execution history so far:
{execution_history}

Choose exactly ONE action by calling the corresponding tool:
- revise_plan: The current plan is flawed, incomplete, or needs updating \
based on execution results. Provide a reason for revision.
- execute_code: The plan is sound and the next step(s) should be executed. \
You may batch multiple consecutive steps into a single execute_code action \
(e.g. "Execute steps 1-3") to use router turns efficiently.
- terminate: The question has been definitively answered. Provide the final answer.

Rules:
- If code execution produced errors or unexpected results that suggest the \
plan is wrong, choose revise_plan.
- If code execution is proceeding normally and there are more steps, choose \
execute_code. Prefer batching remaining steps when they are straightforward.
- Before choosing terminate, verify that:
  (a) Ties are resolved — if multiple items share the best score, apply a \
tiebreaker (e.g. higher total count, then lexicographic order).
  (b) The code computed a concrete final value, not just an intermediate table.
  (c) Edge cases were handled (e.g. internal edges starting with ':' excluded, \
division by zero avoided).
  If any of these are uncertain, choose execute_code to verify first.
- Do NOT choose revise_plan more than {max_consecutive_revise} times in a row \
without executing code in between."""

ROUTER_TOOLS = [
    {
        "name": "revise_plan",
        "description": "The current plan needs revision based on new information "
                       "from execution results or recognized errors.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why the plan needs revision",
                }
            },
            "required": ["reason"],
        },
    },
    {
        "name": "execute_code",
        "description": "Execute the next step of the current plan using Python code.",
        "input_schema": {
            "type": "object",
            "properties": {
                "step_description": {
                    "type": "string",
                    "description": "Brief description of what step to execute next",
                }
            },
            "required": ["step_description"],
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
# Replanner
# =====================================================================

REPLAN_PROMPT = """\
You are an expert in traffic network analysis specializing in SUMO simulations.

You previously created a plan to answer a question, but execution revealed \
problems. You must create a REVISED plan.

Time convention: the simulation runs from 0 to 3600 seconds, divided into \
six 10-minute periods (first: 0-600s, second: 600-1200s, ..., sixth: 3000-3600s).

Files available for this question:
{file_paths}

Previous plan (revision {revision}):
--- OLD PLAN ---
{old_plan}
--- END OLD PLAN ---

What happened during execution:
{execution_history}

Reason for revision: {revision_reason}

Create a NEW numbered plan that fixes the issues. You may reuse steps that \
worked and replace or add steps for parts that failed. Be specific about \
XML element names, attribute names, and any edge cases to handle \
(e.g., internal edges starting with ':' should be skipped)."""


# =====================================================================
# Executor
# =====================================================================

EXECUTE_STEP_PROMPT = """\
You are an expert in traffic network analysis specializing in SUMO simulations.

You have access to a `run_python` tool that executes Python code in a \
persistent session. Variables and imports from previous calls are preserved.
Available: Python standard library only.

Time convention: the simulation runs from 0 to 3600 seconds, divided into \
six 10-minute periods (first: 0-600s, second: 600-1200s, ..., sixth: 3000-3600s).

Files available for this question (use the provided paths to read them with Python):
{file_paths}

Current plan (revision {revision}):
--- PLAN ---
{plan}
--- END PLAN ---

Execute the following step(s):
{step_description}

Write Python code to accomplish these step(s). You may combine multiple \
steps into a single code block when they are straightforward. If you \
encounter an error, report what happened — the router will decide whether \
to revise the plan.
Once done, respond with a brief summary of the result."""


# =====================================================================
# Helpers
# =====================================================================

def _format_execution_history(trace: list[dict]) -> str:
    if not trace:
        return "(no execution history yet)"
    lines = []
    for entry in trace:
        role = entry["role"]
        if role == "plan":
            lines.append(f"[Plan v{entry.get('revision', 0)}] Created")
        elif role == "router":
            reasoning = entry.get("reasoning", "")
            lines.append(f"[Router] Action: {entry['action']}"
                         + (f" - {reasoning}" if reasoning else ""))
        elif role == "tool_call":
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
        elif role == "final_answer":
            lines.append(f"[Answer] {entry.get('text', '')}")
    return "\n".join(lines)


# =====================================================================
# Main
# =====================================================================

def ask(network: str, question: str, files_used: list[str],
        model: str = DEFAULT_MODEL,
        max_router_turns: int = MAX_ROUTER_TURNS) -> str:
    client = get_client()
    file_paths_block = _build_file_paths_block(network, files_used)
    trace: list[dict] = []

    # ── Phase 0: Initial planning (no tools) ──
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
    current_plan = plan_response.content[0].text if plan_response.content else ""
    revision = 0
    trace.append({"role": "plan", "text": current_plan, "revision": revision})

    # ── Router-driven loop ──
    session = PersistentPython(timeout=CODE_TIMEOUT)
    consecutive_revise = 0
    executor_messages: list[dict] = []
    exec_system = [{
        "type": "text",
        "text": EXECUTE_STEP_PROMPT.format(
            file_paths=file_paths_block,
            revision=revision,
            plan=current_plan,
            step_description="(pending)",
        ),
        "cache_control": {"type": "ephemeral"},
    }]

    try:
        for _turn in range(max_router_turns):
            # --- Router call ---
            exec_history = _format_execution_history(trace)
            router_system = [{
                "type": "text",
                "text": ROUTER_PROMPT.format(
                    question=question,
                    plan=current_plan,
                    revision=revision,
                    execution_history=exec_history,
                    max_consecutive_revise=MAX_CONSECUTIVE_REVISE,
                ),
                "cache_control": {"type": "ephemeral"},
            }]

            router_response = client.messages.create(
                model=model,
                max_tokens=ROUTER_MAX_TOKENS,
                system=router_system,
                messages=[{"role": "user",
                           "content": f"Question: {question}\nDecide the next action."}],
                tools=ROUTER_TOOLS,
                tool_choice={"type": "any"},
            )

            action, action_input = None, {}
            for block in router_response.content:
                if block.type == "tool_use":
                    action = block.name
                    action_input = block.input
                    break

            if action is None:
                final_text = "".join(
                    b.text for b in router_response.content if b.type == "text"
                )
                trace.append({"role": "final_answer", "text": final_text.strip()})
                break

            reasoning = (action_input.get("reason", "")
                         or action_input.get("step_description", "")
                         or action_input.get("final_answer", ""))
            trace.append({"role": "router", "action": action,
                          "reasoning": reasoning})

            # --- Terminate ---
            if action == "terminate":
                # Ask the Executor to print the answer via code.
                # Code stdout is pure data — no markdown can leak in.
                final_messages = executor_messages + [
                    {"role": "user",
                     "content": (
                         f"Print the final answer using a single print() "
                         f"statement. Output ONLY the raw answer value "
                         f"for: {question}"
                     )}
                ]
                final_response = client.messages.create(
                    model=model,
                    max_tokens=MAX_TOKENS,
                    system=exec_system,
                    messages=final_messages,
                    tools=TOOLS,
                    tool_choice={"type": "tool", "name": "run_python"},
                )
                final_text = ""
                for block in final_response.content:
                    if block.type == "tool_use" and block.name == "run_python":
                        code = block.input.get("code", "")
                        stdout, stderr = session.run(code)
                        final_text = stdout.strip()
                        break
                if not final_text:
                    final_text = action_input.get("final_answer", "")
                trace.append({"role": "final_answer", "text": final_text})
                break

            # --- Revise plan ---
            if action == "revise_plan":
                consecutive_revise += 1
                if consecutive_revise > MAX_CONSECUTIVE_REVISE:
                    trace.append({"role": "router", "action": "execute_code",
                                  "reasoning": "forced: exceeded max consecutive revisions"})
                    action = "execute_code"
                    action_input = {"step_description":
                                    "Execute step 1 of the current plan"}
                else:
                    replan_system = [{
                        "type": "text",
                        "text": REPLAN_PROMPT.format(
                            file_paths=file_paths_block,
                            revision=revision,
                            old_plan=current_plan,
                            execution_history=exec_history,
                            revision_reason=action_input.get("reason", ""),
                        ),
                        "cache_control": {"type": "ephemeral"},
                    }]
                    replan_response = client.messages.create(
                        model=model,
                        max_tokens=PLAN_MAX_TOKENS,
                        system=replan_system,
                        messages=[{"role": "user",
                                   "content": f"Question: {question}"}],
                    )
                    current_plan = (replan_response.content[0].text
                                    if replan_response.content else current_plan)
                    revision += 1
                    trace.append({"role": "plan", "text": current_plan,
                                  "revision": revision})
                    continue

            # --- Execute code ---
            if action == "execute_code":
                consecutive_revise = 0
                step_desc = action_input.get("step_description", "the next step")

                exec_system = [{
                    "type": "text",
                    "text": EXECUTE_STEP_PROMPT.format(
                        file_paths=file_paths_block,
                        revision=revision,
                        plan=current_plan,
                        step_description=step_desc,
                    ),
                    "cache_control": {"type": "ephemeral"},
                }]

                step_messages = [
                    {"role": "user",
                     "content": f"Question: {question}\n\nExecute: {step_desc}"}
                ]

                for _sub in range(MAX_EXEC_SUB_TURNS):
                    exec_response = client.messages.create(
                        model=model,
                        max_tokens=MAX_TOKENS,
                        system=exec_system,
                        messages=executor_messages + step_messages,
                        tools=TOOLS,
                    )
                    assistant_content = exec_response.content
                    step_messages.append({"role": "assistant",
                                          "content": assistant_content})

                    for block in assistant_content:
                        if block.type == "text":
                            trace.append({"role": "assistant",
                                          "text": block.text})
                        elif block.type == "tool_use":
                            trace.append({"role": "tool_call",
                                          "name": block.name,
                                          "code": block.input.get("code", "")})

                    if exec_response.stop_reason == "end_turn":
                        break

                    if exec_response.stop_reason == "max_tokens":
                        has_tool = any(b.type == "tool_use"
                                       for b in assistant_content)
                        if has_tool:
                            tool_results = []
                            for block in assistant_content:
                                if block.type == "tool_use":
                                    trace.append({
                                        "role": "execution",
                                        "stdout": "",
                                        "stderr": "max_tokens reached",
                                    })
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

                    if exec_response.stop_reason == "tool_use":
                        tool_results = []
                        for block in assistant_content:
                            if block.type == "tool_use":
                                code = block.input.get("code", "")
                                stdout, stderr = session.run(code)
                                trace.append({"role": "execution",
                                              "stdout": stdout,
                                              "stderr": stderr})
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": _format_feedback(stdout, stderr),
                                })
                        step_messages.append({"role": "user",
                                              "content": tool_results})

                executor_messages.extend(step_messages)

        else:
            # Loop exhausted MAX_ROUTER_TURNS without terminating.
            # Extract the answer via code as a fallback.
            if executor_messages:
                final_messages = executor_messages + [
                    {"role": "user",
                     "content": (
                         f"Print the final answer using a single print() "
                         f"statement. Output ONLY the raw answer value "
                         f"for: {question}"
                     )}
                ]
                final_response = client.messages.create(
                    model=model,
                    max_tokens=MAX_TOKENS,
                    system=exec_system,
                    messages=final_messages,
                    tools=TOOLS,
                    tool_choice={"type": "tool", "name": "run_python"},
                )
                final_text = ""
                for block in final_response.content:
                    if block.type == "tool_use" and block.name == "run_python":
                        code = block.input.get("code", "")
                        stdout, stderr = session.run(code)
                        final_text = stdout.strip()
                        break
                if final_text:
                    trace.append({"role": "final_answer", "text": final_text})

    finally:
        session.close()

    return json.dumps(trace, ensure_ascii=False)
