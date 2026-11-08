"""Load the project-root .env when running outside Docker (Docker passes it via env_file).

Existing environment variables always win. Skipped under pytest so the unit tests
never pick up a real key or spend credits.
"""
import os
import sys
from pathlib import Path


def _load_dotenv() -> None:
    if "pytest" in sys.modules or os.environ.get("UDYAM_SKIP_DOTENV"):
        return
    path = Path(__file__).resolve().parents[2] / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


_load_dotenv()
