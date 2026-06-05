"""
Scaffolding condition: Naive baseline.

The LLM receives file *paths* and structural descriptions (identical to
the tool condition) but is given NO tools. It cannot read files or
execute code. This tests what the model can answer from the question
text and file metadata alone, serving as a lower bound.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import DEFAULT_MODEL, FILE_PATHS, get_client
from .tool_use import FILE_DESCRIPTIONS


MAX_TOKENS = 1024

BASE_PROMPT = """\
You are an expert in traffic network analysis specializing in SUMO simulations.

Time convention: the simulation runs from 0 to 3600 seconds, divided into \
six 10-minute periods (first: 0-600s, second: 600-1200s, ..., sixth: 3000-3600s).

The following files are associated with this question, but you do NOT have \
access to read them:
{file_paths}

Answer the question with ONLY the final value based on your best judgment.
If multiple answers are tied, report ALL of them.
If no answer exists, respond with 'None'."""


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
