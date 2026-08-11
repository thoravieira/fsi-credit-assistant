"""SDD 06 §4 — prompt loading and versioning.

Prompts live as `.md` files rather than Python string literals for two
reasons. They are demo-facing Portuguese prose that gets read out loud, and
`PROMPT_VERSION` is written into every `decisions_log` entry (SDD 02 §6), so
"which version of the system made this decision?" is answered by a field
rather than by a guess. Bump the version when a prompt changes.
"""

from functools import lru_cache
from pathlib import Path

PROMPT_VERSION = "v1"

_PROMPTS_DIR = Path(__file__).resolve().parent


@lru_cache
def load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
