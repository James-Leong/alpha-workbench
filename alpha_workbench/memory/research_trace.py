"""Research trace persistence helpers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def save_research_trace(trace: dict[str, Any], output_dir: str | Path = "runs") -> str:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    filename = "research_trace_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
    target = path / filename
    target.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target)
