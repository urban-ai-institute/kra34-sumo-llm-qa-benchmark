"""
Claude (Anthropic) LLM client.

Exposes a single object with an Anthropic-`messages.create`-compatible
interface. Only Claude models (``claude*``) are supported.
"""

import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Claude API key loading
#
# The key is read from ``claude_api.txt`` at the repo root, or failing that
# from the ``ANTHROPIC_API_KEY`` / ``CLAUDE_API_KEY`` environment variable.
# ---------------------------------------------------------------------------

def _get_claude_api_key() -> str:
    # repo root: scripts/llm_client.py -> scripts/ -> SUMO-SimQA/
    key_file = Path(__file__).resolve().parents[1] / "claude_api.txt"
    if key_file.exists():
        key = key_file.read_text().strip()
        if key:
            return key
    for var in ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY"):
        val = os.environ.get(var)
        if val:
            return val
    raise FileNotFoundError(
        f"Claude API key not found: create {key_file} or set ANTHROPIC_API_KEY")


# ---------------------------------------------------------------------------
# Token-usage accounting (module-level accumulator)
#
# Every call records its token usage here so a caller can snapshot the delta
# around a unit of work (e.g. one question). `input` is *uncached* prompt
# tokens; `cached_input` is the cache-read portion (priced separately).
# Anthropic input_tokens already EXCLUDES cache reads.
# ---------------------------------------------------------------------------

_USAGE = {"input": 0, "cached_input": 0, "cache_write": 0, "output": 0, "calls": 0}


def reset_usage():
    for k in _USAGE:
        _USAGE[k] = 0


def get_usage() -> dict:
    return dict(_USAGE)


def _record_usage(usage) -> None:
    if usage is None:
        return
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    cached = getattr(usage, "cache_read_input_tokens", 0) or 0
    # Cache writes are billed at a premium (1.25x), so track separately.
    created = getattr(usage, "cache_creation_input_tokens", 0) or 0
    _USAGE["input"] += inp
    _USAGE["cache_write"] += created
    _USAGE["cached_input"] += cached
    _USAGE["output"] += out
    _USAGE["calls"] += 1


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

class _MessagesNamespace:
    def __init__(self, client):
        self._client = client

    def create(self, *, model, max_tokens, messages, system=None,
               tools=None, tool_choice=None, **kwargs):
        return self._client._create(
            model=model, max_tokens=max_tokens, messages=messages,
            system=system, tools=tools, tool_choice=tool_choice, **kwargs,
        )


class UnifiedClient:
    """Anthropic-`messages.create`-compatible client (Claude only)."""

    def __init__(self):
        self.messages = _MessagesNamespace(self)
        self._anthropic = None

    def _anthropic_client(self):
        if self._anthropic is None:
            import anthropic
            self._anthropic = anthropic.Anthropic(
                api_key=_get_claude_api_key())
        return self._anthropic

    def _create(self, *, model, max_tokens, messages, system,
                tools, tool_choice, **kwargs):
        if not model.startswith("claude"):
            raise ValueError(
                f"Unsupported model '{model}'. Only Claude (claude*) models "
                f"are supported.")
        req = dict(model=model, max_tokens=max_tokens, messages=messages)
        if system is not None:
            req["system"] = system
        if tools is not None:
            req["tools"] = tools
        if tool_choice is not None:
            req["tool_choice"] = tool_choice
        req.update(kwargs)
        resp = self._anthropic_client().messages.create(**req)
        _record_usage(getattr(resp, "usage", None))
        return resp


_INSTANCE = None


def get_unified_client() -> UnifiedClient:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = UnifiedClient()
    return _INSTANCE
