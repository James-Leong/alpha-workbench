"""Entry point executed inside bubblewrap for one factor calculation."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from alpha_workbench.factor_runtime.context import FactorContext
from alpha_workbench.factor_runtime.plugin_loader import PluginLoader
from alpha_workbench.factor_runtime.runner import run_factor
from alpha_workbench.factor_runtime.sandbox_protocol import frame_from_payload, frame_to_payload


def main() -> int:
    if len(sys.argv) != 4:
        return 2
    plugin_dir, input_path, output_path = map(Path, sys.argv[1:])
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        fields = {
            name: frame_from_payload(frame_payload)
            for name, frame_payload in payload["fields"].items()
        }
        context = FactorContext(
            fields,
            trading_dates=pd_dates(payload["trading_dates"]),
            symbols=payload["symbols"],
        )
        loaded = PluginLoader(plugin_dir)._load_in_process()
        result = run_factor(
            loaded.calculate,
            context,
            payload["params"],
            lookback_days=loaded.manifest.lookback_days,
        )
        response = {"status": "passed", "result": frame_to_payload(result)}
    except BaseException as exc:
        response = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)[-4000:],
        }
    output_path.write_text(
        json.dumps(response, ensure_ascii=True, allow_nan=False),
        encoding="utf-8",
    )
    return 0 if response["status"] == "passed" else 1


def pd_dates(values: object):
    import pandas as pd

    return pd.DatetimeIndex(pd.to_datetime(values, errors="raise"))


if __name__ == "__main__":
    raise SystemExit(main())
