"""Environment helpers for controlled maintenance and development scripts."""

from __future__ import annotations

import os


def required_environment(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise SystemExit(
            f"Configuration error: {name} is required. "
            "Load it from an ignored local environment file."
        )
    return value
