"""Minimal config shim for the standalone SUMO-SimQA repo.

Only the Claude (Anthropic) API-key helper used by the experiment code is
vendored here. The key is read from ``claude_api.txt`` at the repo root or,
failing that, from the ``ANTHROPIC_API_KEY`` / ``CLAUDE_API_KEY`` environment
variable.
"""

from pathlib import Path
import os

__all__ = ["AgentSUMOConfig"]


class AgentSUMOConfig:
    """Global configuration for SUMO-SimQA experiments."""

    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    DATA_DIR = PROJECT_ROOT / "data"
    OUTPUT_DIR = PROJECT_ROOT / "data" / "output"

    CLAUDE_API_KEY_FILE = PROJECT_ROOT / "claude_api.txt"

    DEFAULT_MODEL = "claude-sonnet-4-6"

    @classmethod
    def get_claude_api_key(cls) -> str:
        if cls.CLAUDE_API_KEY_FILE.exists():
            key = cls.CLAUDE_API_KEY_FILE.read_text().strip()
            if key:
                return key
        for var in ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY"):
            val = os.environ.get(var)
            if val:
                return val
        raise FileNotFoundError(
            f"Claude API key not found: create {cls.CLAUDE_API_KEY_FILE} or set "
            f"ANTHROPIC_API_KEY")
