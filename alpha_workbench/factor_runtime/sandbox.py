"""Host-side isolated execution boundary for generated factor plugins."""

from __future__ import annotations

import json
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Mapping

from alpha_workbench.factor_runtime.context import FactorContext
from alpha_workbench.factor_runtime.registry import PluginRegistry
from alpha_workbench.factor_runtime.runner import validate_factor_result
from alpha_workbench.factor_runtime.sandbox_protocol import frame_from_payload, frame_to_payload


class FactorSandboxError(RuntimeError):
    """Raised when an isolated factor calculation cannot complete safely."""


class SandboxedFactorExecutor:
    def __init__(self, *, timeout_seconds: float = 60.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        plugin_dir: str | Path,
        context: FactorContext,
        params: Mapping[str, Any] | None = None,
        *,
        lookback_days: int = 0,
    ):
        bwrap = shutil.which("bwrap")
        if bwrap is None:
            raise FactorSandboxError("factor execution requires bubblewrap (bwrap)")
        directory = Path(plugin_dir).expanduser().resolve()
        if not directory.is_dir() or directory.is_symlink():
            raise FactorSandboxError("factor plugin directory must be a regular directory")
        if (directory / "promotion.json").exists():
            try:
                PluginRegistry(directory.parents[3]).verify(directory)
            except (IndexError, ValueError) as exc:
                raise FactorSandboxError(f"promoted plugin integrity check failed: {exc}") from exc
        if any(not isinstance(symbol, str) for symbol in context.symbols):
            raise FactorSandboxError("sandboxed factor symbols must be strings")

        payload = {
            "fields": {
                name: frame_to_payload(context.field(name))
                for name in sorted(context.field_names)
            },
            "trading_dates": [value.isoformat() for value in context.trading_dates],
            "symbols": context.symbols,
            "params": dict(params or {}),
        }
        with tempfile.TemporaryDirectory(prefix="alpha-factor-run-") as exchange_name:
            exchange = Path(exchange_name)
            input_path = exchange / "input.json"
            output_path = exchange / "output.json"
            input_path.write_text(
                json.dumps(payload, ensure_ascii=True, allow_nan=False),
                encoding="utf-8",
            )
            with (
                tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stdout_file,
                tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stderr_file,
            ):
                completed = subprocess.run(
                    self._command(bwrap, directory, exchange),
                    stdout=stdout_file,
                    stderr=stderr_file,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                    shell=False,
                    preexec_fn=_limit_worker_resources,
                )
                worker_log = _read_log_tail(stderr_file) or _read_log_tail(stdout_file)
            if not output_path.is_file() or output_path.is_symlink():
                detail = worker_log or "no worker output"
                raise FactorSandboxError(f"factor sandbox produced no result: {detail[-2000:]}")
            if output_path.stat().st_size > 100 * 1024 * 1024:
                raise FactorSandboxError("factor sandbox output exceeds 100 MiB")
            try:
                response = json.loads(output_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise FactorSandboxError("factor sandbox returned invalid JSON") from exc
        if not isinstance(response, dict) or not isinstance(response.get("status"), str):
            raise FactorSandboxError("factor sandbox returned an invalid response object")
        if completed.returncode != 0 or response["status"] != "passed":
            raise FactorSandboxError(
                f"factor sandbox failed: {response.get('error_type', 'WorkerError')}: "
                f"{response.get('error', 'unknown error')}"
            )
        if set(response) != {"status", "result"} or not isinstance(response["result"], dict):
            raise FactorSandboxError("factor sandbox passed response has invalid fields")
        try:
            result = frame_from_payload(response["result"])
            return validate_factor_result(result, context, lookback_days=lookback_days)
        except (KeyError, TypeError, ValueError) as exc:
            raise FactorSandboxError(f"factor sandbox result protocol is invalid: {exc}") from exc

    @staticmethod
    def _command(bwrap: str, plugin_dir: Path, exchange: Path) -> list[str]:
        runtime_root = Path(__file__).resolve().parents[2]
        venv_root = Path(sys.prefix).absolute()
        return [
            bwrap,
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
            "--ro-bind",
            "/",
            "/",
            "--tmpfs",
            "/home",
            "--tmpfs",
            "/root",
            "--tmpfs",
            "/tmp",
            "--tmpfs",
            "/mnt",
            "--dir",
            "/mnt/runtime",
            "--ro-bind",
            str(runtime_root / "alpha_workbench"),
            "/mnt/runtime/alpha_workbench",
            "--ro-bind",
            str(venv_root),
            "/mnt/venv",
            "--ro-bind",
            str(plugin_dir),
            "/mnt/plugin",
            "--bind",
            str(exchange),
            "/mnt/exchange",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--chdir",
            "/mnt/plugin",
            "--clearenv",
            "--setenv",
            "PATH",
            "/mnt/venv/bin:/usr/bin:/bin",
            "--setenv",
            "HOME",
            "/tmp",
            "--setenv",
            "PYTHONPATH",
            "/mnt/runtime",
            "--setenv",
            "PYTHONNOUSERSITE",
            "1",
            "--setenv",
            "PYTHONDONTWRITEBYTECODE",
            "1",
            "/mnt/venv/bin/python",
            "-m",
            "alpha_workbench.factor_runtime.sandbox_worker",
            "/mnt/plugin",
            "/mnt/exchange/input.json",
            "/mnt/exchange/output.json",
        ]


def _limit_worker_resources() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 1024**2, 128 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))


def _read_log_tail(stream, limit: int = 16_384) -> str:
    stream.flush()
    size = stream.tell()
    stream.seek(max(0, size - limit))
    return stream.read(limit).strip()
