from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from alpha_workbench.factor_runtime import (
    FactorCodingBrief,
    FactorContext,
    FactorPluginManifest,
    FactorResultValidationError,
    FactorSandboxError,
    LookaheadAuditError,
    PluginLoadError,
    PluginValidationError,
    SandboxedFactorExecutor,
    run_factor,
    run_lookahead_perturbation_audit,
    validate_plugin_source,
)
from alpha_workbench.factor_runtime.plugin_loader import PluginLoader


def _manifest(**overrides: object) -> dict[str, object]:
    manifest: dict[str, object] = {
        "factor_id": "test_factor",
        "factor_name": "Test Factor",
        "version": "0.1.0",
        "entrypoint": "factor:calculate",
        "required_fields": ["close"],
        "lookback_days": 5,
        "frequency": "daily",
        "point_in_time": True,
        "parameters": {"scale": 2.0},
        "data_policy": {"signal_effective_rule": "same_day"},
        "risk_notes": ["test fixture"],
        "status": "generated",
    }
    manifest.update(overrides)
    return manifest


def _write_plugin(
    directory: Path,
    *,
    source: str | None = None,
    manifest: dict[str, object] | None = None,
) -> Path:
    directory.mkdir()
    (directory / "manifest.json").write_text(
        json.dumps(manifest or _manifest()), encoding="utf-8"
    )
    (directory / "factor.py").write_text(
        source
        or """
import pandas as pd

def calculate(ctx, params):
    result = ctx.field("close") * params["scale"]
    return pd.DataFrame(result, index=ctx.trading_dates, columns=ctx.symbols)
""",
        encoding="utf-8",
    )
    return directory


@pytest.fixture
def context() -> FactorContext:
    dates = pd.date_range("2025-01-02", periods=3, freq="B")
    close = pd.DataFrame(
        [[10.0, 20.0], [11.0, 19.0], [12.0, 21.0]],
        index=dates,
        columns=["000001.XSHE", "600000.XSHG"],
    )
    return FactorContext({"close": close})


def test_contracts_validate_brief_and_load_manifest_json(tmp_path: Path):
    brief = FactorCodingBrief(
        factor_id="test_factor",
        idea_summary="Price strength",
        hypothesis="Recent strength persists",
        required_fields=["close"],
        plugin_contract={"entrypoint": "calculate(ctx, params)"},
    )
    assert brief.implementation_target == "python_plugin"

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    manifest = FactorPluginManifest.from_json(manifest_path)

    assert manifest.factor_id == "test_factor"
    assert manifest.parameters == {"scale": 2.0}

    with pytest.raises(ValidationError, match="required_fields must be unique"):
        FactorPluginManifest.model_validate(_manifest(required_fields=["close", "close"]))


def test_context_returns_copies_and_exposes_axes():
    dates = pd.date_range("2025-01-02", periods=2, freq="B")
    original = pd.DataFrame([[1.0], [2.0]], index=dates, columns=["AAA"])
    ctx = FactorContext({"close": original})

    original.iloc[0, 0] = 99.0
    fetched = ctx.field("close")
    fetched.iloc[1, 0] = 88.0

    assert ctx.field("close").iloc[:, 0].tolist() == [1.0, 2.0]
    assert ctx.trading_dates.equals(dates)
    assert ctx.symbols == ["AAA"]
    with pytest.raises(KeyError, match="unknown factor field"):
        ctx.field("missing")


def test_context_rejects_field_axes_that_do_not_match_canonical_axes():
    dates = pd.date_range("2025-01-02", periods=3, freq="B")
    close = pd.DataFrame(1.0, index=dates, columns=["AAA", "BBB"])

    with pytest.raises(ValueError, match="index must match"):
        FactorContext(
            {"close": close.iloc[::-1]},
            trading_dates=dates,
            symbols=["AAA", "BBB"],
        )
    with pytest.raises(ValueError, match="columns must match"):
        FactorContext(
            {"close": close.loc[:, ["BBB", "AAA"]]},
            trading_dates=dates,
            symbols=["AAA", "BBB"],
        )


@pytest.mark.parametrize(
    "module",
    ["uqer", "requests", "socket", "subprocess", "os", "sys", "pathlib"],
)
def test_ast_validation_rejects_forbidden_imports(module: str):
    with pytest.raises(PluginValidationError, match="forbidden"):
        validate_plugin_source(f"import {module}\n")


def test_ast_validation_uses_import_allowlist():
    validate_plugin_source(
        """
from __future__ import annotations
import pandas as pd
import numpy as np
from typing import Protocol, Sequence
from alpha_workbench.factor_runtime import FactorContext
"""
    )

    with pytest.raises(PluginValidationError, match="not allowed"):
        validate_plugin_source("import urllib\n")

    with pytest.raises(PluginValidationError, match="not allowed"):
        validate_plugin_source(
            "from alpha_workbench.code_agent import CodexExecProvider\n"
        )


@pytest.mark.parametrize("name", ["open", "eval", "exec", "compile", "__import__"])
def test_ast_validation_rejects_forbidden_calls(name: str):
    with pytest.raises(PluginValidationError, match=name):
        validate_plugin_source(
            f"def calculate(ctx, params):\n    return {name}('value')\n"
        )


def test_ast_validation_rejects_dunder_attributes():
    with pytest.raises(PluginValidationError, match="dunder attribute"):
        validate_plugin_source("def calculate(ctx, params):\n    return ctx.__class__\n")


def test_ast_validation_rejects_io_and_module_level_execution():
    with pytest.raises(PluginValidationError, match="read_csv"):
        validate_plugin_source(
            "import pandas as pd\n\ndef calculate(ctx, params):\n    return pd.read_csv('x')\n"
        )

    with pytest.raises(PluginValidationError, match="module-level assignments"):
        validate_plugin_source("import pandas as pd\nVALUE = pd.DataFrame()\n")


def test_loader_validates_files_entrypoint_and_calculate(tmp_path: Path):
    valid_dir = _write_plugin(tmp_path / "valid")
    loaded = PluginLoader(valid_dir)._load_in_process()
    assert loaded.manifest.factor_id == "test_factor"
    assert callable(loaded.calculate)

    wrong_entry = _write_plugin(
        tmp_path / "wrong_entry",
        manifest=_manifest(entrypoint="other:calculate"),
    )
    with pytest.raises(PluginLoadError, match="factor:calculate"):
        PluginLoader()._load_in_process(wrong_entry)

    missing_source = tmp_path / "missing_source"
    missing_source.mkdir()
    (missing_source / "manifest.json").write_text(
        json.dumps(_manifest()), encoding="utf-8"
    )
    with pytest.raises(PluginLoadError, match="missing plugin source"):
        PluginLoader(missing_source)._load_in_process()

    no_calculate = _write_plugin(tmp_path / "no_calculate", source="VALUE = 1\n")
    with pytest.raises(PluginLoadError, match="must define callable calculate"):
        PluginLoader(no_calculate)._load_in_process()

    symlinked = _write_plugin(tmp_path / "symlinked")
    real_source = symlinked / "real_factor.py"
    (symlinked / "factor.py").replace(real_source)
    (symlinked / "factor.py").symlink_to(real_source)
    with pytest.raises(PluginLoadError, match="symlinks"):
        PluginLoader(symlinked)._load_in_process()


def test_trusted_runner_uses_manifest_defaults_and_overrides(
    tmp_path: Path, context: FactorContext
):
    plugin_dir = _write_plugin(tmp_path / "plugin")
    loaded = PluginLoader(plugin_dir)._load_in_process()

    default_result = run_factor(
        loaded.calculate,
        context,
        loaded.manifest.parameters,
        lookback_days=loaded.manifest.lookback_days,
    )
    override_result = run_factor(
        loaded.calculate,
        context,
        {**loaded.manifest.parameters, "scale": 3.0},
        lookback_days=loaded.manifest.lookback_days,
    )

    pd.testing.assert_frame_equal(default_result, context.field("close") * 2.0)
    pd.testing.assert_frame_equal(override_result, context.field("close") * 3.0)


@pytest.mark.parametrize(
    ("calculate", "message"),
    [
        (lambda ctx, params: [1, 2], "pandas DataFrame"),
        (
            lambda ctx, params: pd.DataFrame(
                [[1.0, 2.0]], index=["2025-01-02"], columns=ctx.symbols
            ),
            "DatetimeIndex",
        ),
        (
            lambda ctx, params: pd.DataFrame(
                [[1.0, 2.0]],
                index=pd.DatetimeIndex([ctx.trading_dates[0]]),
                columns=ctx.symbols,
            ),
            "context.trading_dates",
        ),
        (
            lambda ctx, params: pd.DataFrame(
                1.0,
                index=ctx.trading_dates,
                columns=list(reversed(ctx.symbols)),
            ),
            "context.symbols",
        ),
    ],
)
def test_runner_rejects_invalid_result_contract(context, calculate, message: str):
    with pytest.raises(FactorResultValidationError, match=message):
        run_factor(calculate, context)


@pytest.mark.parametrize(
    ("calculate", "message"),
    [
        (
            lambda ctx, params: pd.DataFrame(
                "invalid", index=ctx.trading_dates, columns=ctx.symbols
            ),
            "numeric",
        ),
        (
            lambda ctx, params: pd.DataFrame(
                float("inf"), index=ctx.trading_dates, columns=ctx.symbols
            ),
            "infinite",
        ),
        (
            lambda ctx, params: pd.DataFrame(
                float("nan"), index=ctx.trading_dates, columns=ctx.symbols
            ),
            "finite coverage",
        ),
    ],
)
def test_runner_rejects_invalid_factor_values(context, calculate, message: str):
    with pytest.raises(FactorResultValidationError, match=message):
        run_factor(calculate, context)


def test_sandbox_hides_host_files_from_generated_factor(tmp_path, context):
    secret_path = tmp_path / "host-secret.txt"
    secret_path.write_text("not visible", encoding="utf-8")
    plugin_dir = _write_plugin(
        tmp_path / "plugin",
        source=f'''\
def calculate(ctx, params):
    __builtins__["open"]({str(secret_path)!r}).read()
    return ctx.field("close")
''',
    )

    with pytest.raises(FactorSandboxError, match="FileNotFoundError"):
        SandboxedFactorExecutor().run(plugin_dir, context, {"scale": 2.0})


def test_lookahead_audit_passes_for_causal_factor():
    dates = pd.date_range("2025-01-02", periods=10, freq="B")
    close = pd.DataFrame(
        {"AAA": range(10, 20), "BBB": range(20, 30)},
        index=dates,
        dtype=float,
    )
    context = FactorContext({"close": close})

    def calculate(ctx, params):
        return ctx.field("close").pct_change()

    baseline = run_factor(calculate, context)
    report = run_lookahead_perturbation_audit(
        calculate,
        context,
        baseline,
        ["close"],
        cutoff_fraction=0.5,
    )

    assert report["status"] == "passed"
    assert report["changed_cells"] == 0


def test_lookahead_audit_rejects_full_sample_leakage():
    dates = pd.date_range("2025-01-02", periods=10, freq="B")
    close = pd.DataFrame(
        {"AAA": range(10, 20), "BBB": range(20, 30)},
        index=dates,
        dtype=float,
    )
    context = FactorContext({"close": close})

    def calculate(ctx, params):
        source = ctx.field("close")
        return pd.DataFrame(
            [source.mean().to_numpy()] * len(source.index),
            index=source.index,
            columns=source.columns,
        )

    baseline = run_factor(calculate, context)

    with pytest.raises(LookaheadAuditError, match="changed historical"):
        run_lookahead_perturbation_audit(calculate, context, baseline, ["close"])


def test_lookahead_audit_rejects_one_step_future_value():
    dates = pd.date_range("2025-01-02", periods=12, freq="B")
    close = pd.DataFrame(
        {"AAA": range(10, 22), "BBB": range(20, 32)},
        index=dates,
        dtype=float,
    )
    context = FactorContext({"close": close})

    def calculate(ctx, params):
        return ctx.field("close").shift(-1)

    baseline = run_factor(calculate, context)
    with pytest.raises(LookaheadAuditError, match="changed historical"):
        run_lookahead_perturbation_audit(calculate, context, baseline, ["close"])


def test_runner_rejects_duplicate_index_and_columns(context: FactorContext):
    duplicate_dates = pd.DatetimeIndex(
        [context.trading_dates[0], context.trading_dates[0], context.trading_dates[2]]
    )
    duplicate_columns = [context.symbols[0], context.symbols[0]]

    with pytest.raises(FactorResultValidationError, match="index must be unique"):
        run_factor(
            lambda ctx, params: pd.DataFrame(
                1.0, index=duplicate_dates, columns=ctx.symbols
            ),
            context,
        )
    with pytest.raises(FactorResultValidationError, match="columns must be unique"):
        run_factor(
            lambda ctx, params: pd.DataFrame(
                1.0, index=ctx.trading_dates, columns=duplicate_columns
            ),
            context,
        )
