from functools import cache
from pathlib import Path

_PROMPT_DIR = Path(__file__).parent


@cache
def load_prompt(name: str) -> str:
    return (_PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8").strip()
