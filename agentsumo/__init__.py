"""Minimal AgentSUMO config shim for the standalone SUMO-SimQA repo.

Only the API-key helpers used by the experiment code are vendored here.
Each key is read from a file at the repo root (e.g. ``claude_api.txt``)
or, failing that, from an environment variable.
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
    OPENAI_API_KEY_FILE = PROJECT_ROOT / "openai_api.txt"
    GEMINI_API_KEY_FILE = PROJECT_ROOT / "gemini_api.txt"

    DEFAULT_MODEL = "claude-sonnet-4-6"

    @staticmethod
    def _read(file: Path, *env_vars: str) -> str:
        if file.exists():
            key = file.read_text().strip()
            if key:
                return key
        for var in env_vars:
            val = os.environ.get(var)
            if val:
                return val
        raise FileNotFoundError(
            f"API key not found: create {file} or set one of {list(env_vars)}"
        )

    @classmethod
    def get_claude_api_key(cls) -> str:
        return cls._read(cls.CLAUDE_API_KEY_FILE, "ANTHROPIC_API_KEY", "CLAUDE_API_KEY")

    @classmethod
    def get_openai_api_key(cls) -> str:
        return cls._read(cls.OPENAI_API_KEY_FILE, "OPENAI_API_KEY")

    @classmethod
    def get_gemini_api_key(cls) -> str:
        return cls._read(cls.GEMINI_API_KEY_FILE, "GEMINI_API_KEY", "GOOGLE_API_KEY")
