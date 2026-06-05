"""
Cross-provider LLM client.

Exposes a single object with an Anthropic-`messages.create`-compatible
interface that dispatches by model name:

  - "claude*"  -> Anthropic native (pass-through)
  - "gpt*"     -> OpenAI Chat Completions
  - "gemini*"  -> Gemini via OpenAI-compatible endpoint

For the OpenAI/Gemini paths, requests built in Anthropic shape
(system=[{type,text,cache_control}], messages with text/tool_use/tool_result
blocks, tools=[{name,description,input_schema}], tool_choice) are translated
to OpenAI Chat Completions shape, and responses are normalized back to
Anthropic-shaped blocks (.type/.text/.name/.input/.id) with a `.stop_reason`.

A single experiment run uses exactly one model, so the message history only
ever contains blocks produced by that same path — round-trips are consistent.
"""

import json

from agentsumo import AgentSUMOConfig

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


# ---------------------------------------------------------------------------
# Token-usage accounting (module-level accumulator)
#
# Every call routed through UnifiedClient records its token usage here so that
# a caller can snapshot the delta around a unit of work (e.g. one question).
# `input` is *uncached* prompt tokens; `cached_input` is the cache-read portion
# (priced separately by both OpenAI and Anthropic). For OpenAI-compatible
# responses prompt_tokens INCLUDES cached, so we subtract; for Anthropic
# input_tokens already EXCLUDES cache reads.
# ---------------------------------------------------------------------------

_USAGE = {"input": 0, "cached_input": 0, "cache_write": 0, "output": 0, "calls": 0}


def reset_usage():
    for k in _USAGE:
        _USAGE[k] = 0


def get_usage() -> dict:
    return dict(_USAGE)


def _record_usage(usage, provider: str) -> None:
    if usage is None:
        return
    if provider == "anthropic":
        inp = getattr(usage, "input_tokens", 0) or 0
        out = getattr(usage, "output_tokens", 0) or 0
        cached = getattr(usage, "cache_read_input_tokens", 0) or 0
        # Cache writes are billed at a premium (1.25x), so track separately.
        created = getattr(usage, "cache_creation_input_tokens", 0) or 0
        _USAGE["input"] += inp
        _USAGE["cache_write"] += created
        _USAGE["cached_input"] += cached
        _USAGE["output"] += out
    else:  # openai-compatible (gpt / gemini)
        inp = getattr(usage, "prompt_tokens", 0) or 0
        out = getattr(usage, "completion_tokens", 0) or 0
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) or 0 if details else 0
        _USAGE["input"] += max(inp - cached, 0)
        _USAGE["cached_input"] += cached
        _USAGE["output"] += out
    _USAGE["calls"] += 1


# ---------------------------------------------------------------------------
# Anthropic-shaped response blocks (for the OpenAI/Gemini paths)
# ---------------------------------------------------------------------------

class _TextBlock:
    type = "text"

    def __init__(self, text: str):
        self.text = text


class _ToolUseBlock:
    type = "tool_use"

    def __init__(self, id: str, name: str, input: dict, extra=None):
        self.id = id
        self.name = name
        self.input = input
        # Provider-specific passthrough (e.g. Gemini's thought_signature,
        # carried in OpenAI-compat `extra_content`). Must be echoed back
        # with the tool call on the next request or Gemini rejects it.
        self._extra = extra


class _Response:
    def __init__(self, content: list, stop_reason: str):
        self.content = content
        self.stop_reason = stop_reason


# ---------------------------------------------------------------------------
# Request translation: Anthropic shape -> OpenAI Chat Completions shape
# ---------------------------------------------------------------------------

def _system_text(system) -> str:
    if system is None:
        return ""
    if isinstance(system, str):
        return system
    return "\n\n".join(
        b["text"] if isinstance(b, dict) else getattr(b, "text", "")
        for b in system
    )


def _block_attr(block, key, default=None):
    """Read a field from a block that may be a dict or an object."""
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def _convert_messages(system, messages: list) -> list:
    out = []
    sys_text = _system_text(system)
    if sys_text:
        out.append({"role": "system", "content": sys_text})

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue

        # content is a list of blocks (dicts or response objects)
        if role == "assistant":
            text_parts = []
            tool_calls = []
            for block in content:
                btype = _block_attr(block, "type")
                if btype == "text":
                    text_parts.append(_block_attr(block, "text", ""))
                elif btype == "tool_use":
                    call = {
                        "id": _block_attr(block, "id"),
                        "type": "function",
                        "function": {
                            "name": _block_attr(block, "name"),
                            "arguments": json.dumps(_block_attr(block, "input", {})),
                        },
                    }
                    extra = _block_attr(block, "_extra")
                    if extra:
                        call["extra_content"] = extra
                    tool_calls.append(call)
            asst = {"role": "assistant",
                    "content": "".join(text_parts) or None}
            if tool_calls:
                asst["tool_calls"] = tool_calls
            out.append(asst)
        else:  # user
            text_parts = []
            for block in content:
                btype = _block_attr(block, "type")
                if btype == "tool_result":
                    tc = _block_attr(block, "content", "")
                    if isinstance(tc, list):
                        tc = "".join(
                            _block_attr(p, "text", "") if _block_attr(p, "type") == "text"
                            else str(p) for p in tc
                        )
                    if _block_attr(block, "is_error"):
                        tc = f"Error: {tc}"
                    out.append({
                        "role": "tool",
                        "tool_call_id": _block_attr(block, "tool_use_id"),
                        "content": tc if tc else "(no output)",
                    })
                elif btype == "text":
                    text_parts.append(_block_attr(block, "text", ""))
            if text_parts:
                out.append({"role": "user", "content": "".join(text_parts)})
    return out


def _convert_tools(tools):
    if not tools:
        return None
    return [{
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t["input_schema"],
        },
    } for t in tools]


def _convert_tool_choice(tool_choice):
    if tool_choice is None:
        return None
    t = tool_choice.get("type")
    if t == "any":
        return "required"
    if t == "auto":
        return "auto"
    if t == "tool":
        return {"type": "function", "function": {"name": tool_choice["name"]}}
    return None


# ---------------------------------------------------------------------------
# Response translation: OpenAI -> Anthropic shape
# ---------------------------------------------------------------------------

_FINISH_MAP = {
    "tool_calls": "tool_use",
    "length": "max_tokens",
    "stop": "end_turn",
    "function_call": "tool_use",
    "content_filter": "end_turn",
}


def _convert_response(completion) -> _Response:
    choice = completion.choices[0]
    msg = choice.message
    blocks = []
    if msg.content:
        blocks.append(_TextBlock(msg.content))
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            extra = (tc.model_extra or {}).get("extra_content")
            blocks.append(_ToolUseBlock(tc.id, tc.function.name, args, extra=extra))
    stop_reason = _FINISH_MAP.get(choice.finish_reason, "end_turn")
    # If the model emitted tool calls, force tool_use so callers run them.
    if tool_calls and stop_reason == "end_turn":
        stop_reason = "tool_use"
    return _Response(blocks, stop_reason)


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
    """Anthropic-`messages.create`-compatible client routing by model name."""

    def __init__(self):
        self.messages = _MessagesNamespace(self)
        self._anthropic = None
        self._openai = None
        self._gemini = None

    # -- lazy provider clients --
    def _anthropic_client(self):
        if self._anthropic is None:
            import anthropic
            self._anthropic = anthropic.Anthropic(
                api_key=AgentSUMOConfig.get_claude_api_key())
        return self._anthropic

    def _openai_client(self):
        if self._openai is None:
            import openai
            self._openai = openai.OpenAI(
                api_key=AgentSUMOConfig.get_openai_api_key())
        return self._openai

    def _gemini_client(self):
        if self._gemini is None:
            import openai
            self._gemini = openai.OpenAI(
                api_key=AgentSUMOConfig.get_gemini_api_key(),
                base_url=GEMINI_BASE_URL)
        return self._gemini

    def _create(self, *, model, max_tokens, messages, system,
                tools, tool_choice, **kwargs):
        if model.startswith("claude"):
            req = dict(model=model, max_tokens=max_tokens, messages=messages)
            if system is not None:
                req["system"] = system
            if tools is not None:
                req["tools"] = tools
            if tool_choice is not None:
                req["tool_choice"] = tool_choice
            req.update(kwargs)
            resp = self._anthropic_client().messages.create(**req)
            _record_usage(getattr(resp, "usage", None), "anthropic")
            return resp

        # OpenAI / Gemini (OpenAI-compatible) path
        is_gpt = model.startswith("gpt")
        client = self._openai_client() if is_gpt else self._gemini_client()

        oai_messages = _convert_messages(system, messages)
        req = {"model": model, "messages": oai_messages}
        # gpt-5.x rejects max_tokens; uses max_completion_tokens.
        if is_gpt:
            req["max_completion_tokens"] = max_tokens
        else:
            req["max_tokens"] = max_tokens
        oai_tools = _convert_tools(tools)
        if oai_tools:
            req["tools"] = oai_tools
            tc = _convert_tool_choice(tool_choice)
            if tc is not None:
                req["tool_choice"] = tc
        completion = client.chat.completions.create(**req)
        _record_usage(getattr(completion, "usage", None), "openai")
        return _convert_response(completion)


_INSTANCE = None


def get_unified_client() -> UnifiedClient:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = UnifiedClient()
    return _INSTANCE
