"""Codex-only factor plugin generation, validation, and calculation workflow."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Protocol

import pandas as pd

from alpha_workbench.code_agent import CodexExecProvider
from alpha_workbench.core.config import settings
from alpha_workbench.data_sdk import make_earnings_surprise_pit_fixture
from alpha_workbench.factor_runtime import (
    FactorCodingBrief,
    FactorContext,
    PluginRegistry,
    SandboxedFactorExecutor,
    run_lookahead_perturbation_audit,
)
from alpha_workbench.factor_runtime.plugin_loader import PluginLoader


class FactorPluginPipelineError(RuntimeError):
    """Raised when a generated plugin cannot be validated or calculated."""


class CodeAgentProvider(Protocol):
    def generate(self, brief: Mapping[str, Any], destination: str | Path) -> Any: ...


@dataclass(frozen=True)
class FactorPluginPipelineResult:
    factor_specs: list[dict[str, Any]]
    factor_data_dict: dict[str, pd.DataFrame]
    price_data: pd.DataFrame
    returns_data: pd.DataFrame
    trace_artifacts: dict[str, Any]


def build_factor_coding_brief(
    factor_spec: Mapping[str, Any],
    idea_spec: Mapping[str, Any],
) -> FactorCodingBrief:
    """Build the deterministic contract passed to Codex for the MVP factor."""

    factor_id = str(factor_spec.get("factor_id") or "earnings_surprise_underreaction")
    description = str(
        factor_spec.get("plain_description")
        or factor_spec.get("factor_name")
        or "Earnings surprise with pre-announcement underreaction"
    )
    hypothesis = str(
        idea_spec.get("core_hypothesis")
        or idea_spec.get("hypothesis")
        or description
    )
    return FactorCodingBrief(
        factor_id=factor_id,
        idea_summary=description,
        hypothesis=hypothesis,
        required_fields=[
            "quarter_net_profit",
            "expected_net_profit",
            "announce_date",
            "price",
        ],
        data_policy={
            "point_in_time_required": True,
            "signal_effective_rule": "next_trade_date_after_announce",
            "input_fields_are_already_point_in_time_aligned": True,
        },
        plugin_contract={
            "entrypoint": "factor:calculate",
            "return_shape": "wide_dataframe",
            "context_api": ["field(name)", "trading_dates", "symbols"],
            "forbidden": [
                "uqer",
                "network",
                "filesystem",
                "subprocess",
                "open",
                "eval",
                "exec",
            ],
        },
        test_requirements=[
            "return a DataFrame indexed by every ctx.trading_dates value",
            "return columns in exactly ctx.symbols order",
            "do not use report period as signal date",
            "do not backfill values before their PIT effective date",
        ],
    )


def run_factor_plugin_pipeline(
    factor_specs: list[dict[str, Any]],
    idea_spec: Mapping[str, Any],
    research_spec: Mapping[str, Any],
    *,
    provider: CodeAgentProvider | None = None,
    job_root: str | Path | None = None,
    registry: PluginRegistry | None = None,
    run_generated_tests: bool = True,
) -> FactorPluginPipelineResult:
    """Generate and execute one selected factor plugin on deterministic PIT data."""

    if not factor_specs:
        raise FactorPluginPipelineError("at least one candidate factor is required")
    selected = dict(factor_specs[0])
    brief = build_factor_coding_brief(selected, idea_spec)
    code_agent = provider or CodexExecProvider(
        timeout_seconds=settings.factor_code_timeout_seconds
    )
    destination = Path(job_root or settings.factor_code_jobs_dir)
    generation = code_agent.generate(brief.model_dump(mode="json"), destination)
    plugin_dir = Path(generation.job_dir)

    validation_checks: list[dict[str, Any]] = []
    attempt_reports: list[dict[str, Any]] = []
    repair = getattr(code_agent, "repair", None)
    max_attempts = 2 if callable(repair) else 1
    for attempt in range(1, max_attempts + 1):
        validation_checks = []
        try:
            _, manifest, _ = PluginLoader(plugin_dir).inspect()
            validation_checks.extend(
                [
                    {"name": "manifest", "status": "passed"},
                    {"name": "factor_ast", "status": "passed"},
                    {"name": "entrypoint", "status": "passed"},
                ]
            )
            if manifest.factor_id != brief.factor_id:
                raise FactorPluginPipelineError(
                    "generated manifest factor_id does not match the coding brief: "
                    f"{manifest.factor_id!r} != {brief.factor_id!r}"
                )
            manifest_fields = set(manifest.required_fields)
            brief_fields = set(brief.required_fields)
            if manifest_fields != brief_fields:
                missing = sorted(brief_fields - manifest_fields)
                extra = sorted(manifest_fields - brief_fields)
                raise FactorPluginPipelineError(
                    "generated manifest required_fields do not match the coding brief: "
                    f"missing={missing}, extra={extra}"
                )
            if (
                manifest.frequency != "daily"
                or not manifest.point_in_time
                or any(
                    manifest.data_policy.get(key) != value
                    for key, value in brief.data_policy.items()
                )
            ):
                raise FactorPluginPipelineError(
                    "generated manifest violates the coding brief PIT/frequency data policy"
                )
            if run_generated_tests:
                _run_generated_plugin_tests(plugin_dir)
                validation_checks.append({"name": "generated_pytest", "status": "passed"})

            sample_window = dict(research_spec.get("sample_window") or {})
            fixture_start = str(sample_window.get("start") or "2024-01-02")
            fixture = make_earnings_surprise_pit_fixture(start_date=fixture_start)
            wide_fields = {name: _long_to_wide(frame) for name, frame in fixture.items()}
            price_data = wide_fields.pop("price").astype(float)
            sample_end = sample_window.get("end")
            if sample_end:
                price_data = price_data.loc[: pd.Timestamp(sample_end)]
                wide_fields = {
                    name: frame.reindex(price_data.index) for name, frame in wide_fields.items()
                }
            if len(price_data.index) < 40:
                raise FactorPluginPipelineError(
                    "research sample window leaves fewer than 40 trading days for plugin validation"
                )
            wide_fields["price"] = price_data
            context = FactorContext(
                wide_fields,
                trading_dates=price_data.index,
                symbols=list(price_data.columns),
            )
            executor = SandboxedFactorExecutor()
            factor_data = executor.run(
                plugin_dir,
                context,
                manifest.parameters,
                lookback_days=manifest.lookback_days,
            )
            validation_checks.append({"name": "fixture_smoke", "status": "passed"})
            lookahead_report = run_lookahead_perturbation_audit(
                lambda audit_context, audit_params: executor.run(
                    plugin_dir,
                    audit_context,
                    audit_params,
                    lookback_days=manifest.lookback_days,
                ),
                context,
                factor_data,
                manifest.required_fields,
                params=manifest.parameters,
            )
            validation_checks.append(lookahead_report)
            attempt_reports.append({"attempt": attempt, "status": "passed"})
            break
        except Exception as exc:
            attempt_reports.append(
                {"attempt": attempt, "status": "failed", "error": str(exc)[-4000:]}
            )
            if attempt < max_attempts:
                try:
                    generation = repair(brief.model_dump(mode="json"), plugin_dir, str(exc))
                except Exception as repair_exc:
                    _cleanup_generated_job(code_agent, plugin_dir)
                    raise FactorPluginPipelineError(
                        f"generated factor plugin repair failed in {plugin_dir}: {repair_exc}"
                    ) from repair_exc
                plugin_dir = Path(generation.job_dir)
                continue
            _cleanup_generated_job(code_agent, plugin_dir)
            raise FactorPluginPipelineError(
                f"generated factor plugin validation failed in {plugin_dir}: {exc}"
            ) from exc

    validation_report = {
        "factor_id": manifest.factor_id,
        "status": "passed",
        "checks": validation_checks,
        "attempts": attempt_reports,
    }
    registry_root = (
        settings.factor_plugin_registry_dir
        if job_root is None
        else destination / "plugin_registry"
    )
    try:
        promoted = (registry or PluginRegistry(registry_root)).promote(
            plugin_dir,
            validation_report,
        )
    finally:
        _cleanup_generated_job(code_agent, plugin_dir)

    returns_data = price_data.pct_change().shift(-1)
    selected.update(
        {
            "factor_id": manifest.factor_id,
            "factor_name": manifest.factor_name,
            "required_fields": manifest.required_fields,
            "implementation_target": "python_plugin",
            "is_mock": False,
            "is_fallback": False,
        }
    )
    factor_manifest = _factor_data_manifest(
        manifest.factor_id,
        manifest.version,
        promoted.path / "factor.py",
        factor_data,
    )
    trace_artifacts = {
        "factor_implementation_mode": "python_plugin",
        "code_agent": {
            "provider": str(generation.provider),
            "version": str(generation.version),
            "summary": str(generation.summary),
            "risks": list(generation.risks),
            "is_mock": bool(generation.is_mock),
        },
        "factor_coding_briefs": [brief.model_dump(mode="json")],
        "factor_plugin_manifests": [manifest.model_dump(mode="json")],
        "codegen_validation_reports": [validation_report],
        "plugin_registry": promoted.trace_dict(),
        "factor_data_manifests": [factor_manifest],
        "data_provider": "deterministic_pit_fixture",
        "pipeline_status": "passed",
        "pipeline_errors": [],
    }
    return FactorPluginPipelineResult(
        factor_specs=[selected],
        factor_data_dict={manifest.factor_id: factor_data},
        price_data=price_data,
        returns_data=returns_data,
        trace_artifacts=trace_artifacts,
    )


def _cleanup_generated_job(provider: object, plugin_dir: Path) -> None:
    cleanup = getattr(provider, "cleanup", None)
    if callable(cleanup):
        cleanup(plugin_dir)


def _long_to_wide(frame: pd.DataFrame) -> pd.DataFrame:
    wide = frame.pivot(index="trade_date", columns="symbol", values="value")
    wide.index = pd.DatetimeIndex(wide.index)
    wide.columns.name = None
    wide.index.name = None
    return wide.sort_index().sort_index(axis=1)


def _run_generated_plugin_tests(plugin_dir: Path) -> None:
    test_path = plugin_dir / "test_factor.py"
    if not test_path.is_file():
        raise FactorPluginPipelineError("generated plugin is missing test_factor.py")
    _validate_generated_test_source(test_path)
    bwrap = shutil.which("bwrap")
    if bwrap is None:
        raise FactorPluginPipelineError(
            "generated plugin tests require bubblewrap (bwrap); refusing unsandboxed execution"
        )
    project_root = settings.base_dir.resolve()
    runtime_package = project_root / "alpha_workbench"
    venv_root = Path(sys.prefix).absolute()
    command = [
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
    ]
    for mount_base in (Path("/home"), Path("/tmp")):
        for target in (project_root, venv_root, plugin_dir.parent):
            _append_sandbox_directories(command, mount_base, target)
    command.extend(
        [
            "--ro-bind",
            str(venv_root),
            str(venv_root),
            "--ro-bind",
            str(runtime_package),
            str(runtime_package),
            "--ro-bind",
            str(plugin_dir),
            str(plugin_dir),
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--chdir",
            str(plugin_dir),
            "--clearenv",
            "--setenv",
            "PATH",
            "/usr/bin:/bin",
            "--setenv",
            "HOME",
            "/tmp",
            "--setenv",
            "PYTHONNOUSERSITE",
            "1",
            "--setenv",
            "PYTHONDONTWRITEBYTECODE",
            "1",
            "--setenv",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
            "1",
            str(Path(sys.executable).absolute()),
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            str(test_path),
        ]
    )
    with (
        tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stdout_file,
        tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stderr_file,
    ):
        completed = subprocess.run(
            command,
            stdout=stdout_file,
            stderr=stderr_file,
            text=True,
            timeout=120,
            check=False,
            shell=False,
            preexec_fn=_limit_generated_test_resources,
        )
        stdout_file.seek(max(0, stdout_file.tell() - 16_384))
        stderr_file.seek(max(0, stderr_file.tell() - 16_384))
        detail = (stdout_file.read() + "\n" + stderr_file.read()).strip()
    if completed.returncode != 0:
        raise FactorPluginPipelineError(f"generated plugin tests failed: {detail[-4000:]}")


def _append_sandbox_directories(
    command: list[str],
    mount_base: Path,
    target: Path,
) -> None:
    if not target.is_relative_to(mount_base):
        return
    current = mount_base
    for component in target.relative_to(mount_base).parts:
        current /= component
        command.extend(["--dir", str(current)])


def _limit_generated_test_resources() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 1024**2, 128 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))


def _validate_generated_test_source(path: Path) -> None:
    """Apply a narrow policy before executing the generated pytest file."""

    if path.stat().st_size > 2 * 1024 * 1024:
        raise FactorPluginPipelineError("generated test_factor.py exceeds 2 MiB")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    allowed_imports = {"factor", "numpy", "pandas", "pytest", "typing"}
    allowed_from_imports = {
        "factor": {"calculate"},
        "alpha_workbench.factor_runtime": {"FactorContext"},
        "typing": {"Any", "Mapping", "Protocol", "Sequence"},
    }
    forbidden_calls = {
        "__import__",
        "compile",
        "eval",
        "exec",
        "getattr",
        "globals",
        "input",
        "locals",
        "open",
        "setattr",
        "vars",
    }
    forbidden_attributes = {
        "ctypeslib",
        "fromfile",
        "io",
        "load",
        "memmap",
        "popen",
        "read_csv",
        "read_excel",
        "read_json",
        "read_parquet",
        "read_pickle",
        "read_sql",
        "save",
        "system",
        "to_csv",
        "to_json",
        "to_parquet",
        "to_pickle",
        "tofile",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = {alias.name for alias in node.names}
            if not modules <= allowed_imports:
                raise FactorPluginPipelineError(
                    f"generated test imports forbidden modules: {modules}"
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported_names = {alias.name for alias in node.names}
            allowed_names = allowed_from_imports.get(module, set())
            if node.level or not imported_names <= allowed_names:
                raise FactorPluginPipelineError(
                    f"generated test imports forbidden names from {module}: {imported_names}"
                )
        elif isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else None
            attr = node.func.attr if isinstance(node.func, ast.Attribute) else None
            if name in forbidden_calls or attr in forbidden_calls | forbidden_attributes:
                raise FactorPluginPipelineError(
                    f"generated test calls forbidden function: {name or attr}"
                )
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise FactorPluginPipelineError(
                f"generated test accesses forbidden dunder attribute: {node.attr}"
            )


def _factor_data_manifest(
    factor_id: str,
    plugin_version: str,
    source_path: Path,
    factor_data: pd.DataFrame,
) -> dict[str, Any]:
    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    value_hash = pd.util.hash_pandas_object(factor_data, index=True).values.tobytes()
    output_sha = hashlib.sha256(value_hash).hexdigest()
    nan_ratio = float(factor_data.isna().to_numpy().mean())
    return {
        "factor_id": factor_id,
        "plugin_version": plugin_version,
        "source_sha256": source_sha,
        "output_sha256": output_sha,
        "row_count": int(factor_data.shape[0]),
        "symbol_count": int(factor_data.shape[1]),
        "date_start": factor_data.index.min().date().isoformat(),
        "date_end": factor_data.index.max().date().isoformat(),
        "nan_ratio": nan_ratio,
    }
