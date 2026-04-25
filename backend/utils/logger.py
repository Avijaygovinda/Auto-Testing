"""Simple logger that appends every API call and response to a log file.
This is critical for prompt iteration — without logs you won't know
which prompt version worked best.
"""
import json
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "api_calls.log"


def log_api_call(model: str, prompt: str, response: str, metadata: dict = None):
    """Append a single API call to the log file."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "prompt_preview": prompt[:300],
        "response_preview": response[:500],
        "prompt_length": len(prompt),
        "response_length": len(response),
        "metadata": metadata or {},
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
