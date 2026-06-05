"""
Setup methods for SUMO-SimQA.

Five setups, each exposing SUMO files to the LLM in a different way:

- naive               : File paths only, no contents, no code
- xml                 : Verbatim XML in prompt
- tool  (ReAct)       : Path + Python code execution
- plan_execute (PE)   : Plan, then execute as code
- plan_execute_revise (PER) : Plan, execute, and revise

Each `ask` function has the same signature:
    ask(network: str, question: str, files_used: list[str], model: str) -> str
"""

from functools import partial

from .naive import ask as ask_naive
from .xml_view import ask as ask_xml
from .tool_use import ask as ask_tool
from .plan_execute import ask as ask_plan_execute
from .plan_execute_revise import ask as ask_plan_execute_revise

# Core setups reported in the paper.
METHODS = {
    "naive": ask_naive,
    "xml": ask_xml,
    "tool": ask_tool,
    "plan_execute": ask_plan_execute,
    "plan_execute_revise": ask_plan_execute_revise,
}

# Round-budget ablation: PER run with a fixed number of rounds.
ABLATION_METHODS = {
    "plan_execute_revise_1r": partial(ask_plan_execute_revise, max_router_turns=1),
    "plan_execute_revise_3r": partial(ask_plan_execute_revise, max_router_turns=3),
    "plan_execute_revise_5r": partial(ask_plan_execute_revise, max_router_turns=5),
    "plan_execute_revise_10r": partial(ask_plan_execute_revise, max_router_turns=10),
}

# Combined view for dispatch.
ALL_METHODS = {**METHODS, **ABLATION_METHODS}

__all__ = ["METHODS", "ABLATION_METHODS", "ALL_METHODS"]
