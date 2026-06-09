"""Research trace persistence helpers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _safe_json_default(obj: Any) -> Any:
    """兜底序列化：让 json.dumps 不因未知类型崩溃。"""
    # Plotly Figure — 用 to_json() 让 Plotly 自己处理内部所有 numpy 类型
    try:
        import plotly.graph_objs as go
        if isinstance(obj, go.Figure):
            return json.loads(obj.to_json())
    except ImportError:
        pass
    # numpy
    try:
        import numpy as np
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
    except ImportError:
        pass
    # 其他一切 → 转字符串，绝不崩溃
    return str(obj)


def save_research_trace(trace: dict[str, Any], output_dir: str | Path = "runs") -> str:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    filename = "research_trace_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
    target = path / filename
    target.write_text(
        json.dumps(trace, ensure_ascii=False, indent=2, default=_safe_json_default),
        encoding="utf-8",
    )
    return str(target)
