"""
Scaffolding methods for NetTrafficQA.

Three conditions, each exposing SUMO files to the LLM in a different way:

- xml  : Verbatim XML in prompt
- json : JSONL view (one record per line) in prompt
- tool : Path-only + Python execution tool

Each `ask` function has the same signature:
    ask(network: str, question: str, files_used: list[str], model: str) -> str
"""

from functools import partial

from .xml_view import ask as ask_xml
from .json_view import ask as ask_json
from .tool_use import ask as ask_tool
from .tool_revise import ask as ask_tool_revise
from .plan_execute import ask as ask_plan_execute
from .plan_execute_revise import ask as ask_plan_execute_revise
from .tool_continuation import ask as ask_tool_continuation
from .naive import ask as ask_naive

METHODS = {
    "xml": ask_xml,
    "json": ask_json,
    "tool": ask_tool,
    "tool_revise": ask_tool_revise,
    "tool_revise_1r": partial(ask_tool_revise, max_rounds=1),
    "tool_revise_3r": partial(ask_tool_revise, max_rounds=3),
    "plan_execute": ask_plan_execute,
    "plan_execute_revise": ask_plan_execute_revise,
    "plan_execute_revise_1r": partial(ask_plan_execute_revise, max_router_turns=1),
    "plan_execute_revise_3r": partial(ask_plan_execute_revise, max_router_turns=3),
    "plan_execute_revise_5r": partial(ask_plan_execute_revise, max_router_turns=5),
    "plan_execute_revise_10r": partial(ask_plan_execute_revise, max_router_turns=10),
    "tool_continuation": ask_tool_continuation,
    "naive": ask_naive,
}
