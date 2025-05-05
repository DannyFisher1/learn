# utils/prompt_loader.py
import os
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent.parent.parent.parent / "prompts"
print(PROMPTS_DIR)

def load_prompt(prompt_name: str) -> str:
    """Loads a prompt template from the prompts directory."""
    prompt_file = PROMPTS_DIR / f"{prompt_name}.prompt"
    if not prompt_file.is_file():
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        raise IOError(f"Error reading prompt file {prompt_file}: {e}")