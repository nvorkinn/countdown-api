"""Generates the countdown_api package into src/countdown_api from openapi.yaml.

    uv sync --frozen --no-install-project
    uv run --frozen --no-sync python generate.py

Runs openapi-codegen on openapi.yaml, then copies the contract into the package next to an __init__.py.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = ROOT / "openapi.yaml"
OUT = ROOT / "src" / "countdown_api"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    codegen = shutil.which("openapi-codegen") or "openapi-codegen"
    subprocess.run([codegen, str(SPEC), "--out", str(OUT)], check=True)
    shutil.copy(SPEC, OUT / "openapi.yaml")
    (OUT / "__init__.py").touch(exist_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
