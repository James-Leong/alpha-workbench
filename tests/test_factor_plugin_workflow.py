from __future__ import annotations

import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from alpha_workbench.workflows.factor_plugin_workflow import (
    FactorPluginPipelineError,
    _validate_generated_test_source,
    run_factor_plugin_pipeline,
)


FACTOR_SOURCE = """\
def calculate(ctx, params):
    actual = ctx.field("quarter_net_profit")
    expected = ctx.field("expected_net_profit")
    announce_date = ctx.field("announce_date")
    price = ctx.field("price")
    surprise = (actual - expected) / (expected.abs() + 1.0)
    pre_return = price.pct_change(20).shift(1)
    weight = float(params.get("pre_return_weight", 0.5))
    score = surprise - weight * pre_return
    return score.where(announce_date.notna())
"""


TEST_SOURCE = """\
import pandas as pd

from alpha_workbench.factor_runtime import FactorContext
from factor import calculate


def test_calculate_preserves_context_shape():
    dates = pd.date_range("2024-01-01", periods=25, freq="B")
    symbols = ["A", "B"]
    price = pd.DataFrame(100.0, index=dates, columns=symbols)
    actual = pd.DataFrame(110.0, index=dates, columns=symbols)
    expected = pd.DataFrame(100.0, index=dates, columns=symbols)
    announce = pd.DataFrame(dates[0], index=dates, columns=symbols)
    ctx = FactorContext(
        {
            "price": price,
            "quarter_net_profit": actual,
            "expected_net_profit": expected,
            "announce_date": announce,
        },
        trading_dates=dates,
        symbols=symbols,
    )
    result = calculate(ctx, {"pre_return_weight": 0.5})
    assert result.index.equals(dates)
    assert list(result.columns) == symbols
"""


class FakeCodeAgent:
    def __init__(
        self,
        *,
        manifest_factor_id: str | None = None,
        required_fields: list[str] | None = None,
        point_in_time: bool = True,
    ) -> None:
        self.manifest_factor_id = manifest_factor_id
        self.required_fields = required_fields
        self.point_in_time = point_in_time

    def generate(self, brief, destination):
        job_dir = Path(destination) / "fake-codex-job"
        job_dir.mkdir(parents=True)
        factor_id = self.manifest_factor_id or brief["factor_id"]
        manifest = {
            "factor_id": factor_id,
            "factor_name": "盈利超预期低反应",
            "version": "0.1.0",
            "entrypoint": "factor:calculate",
            "required_fields": self.required_fields or brief["required_fields"],
            "lookback_days": 20,
            "frequency": "daily",
            "point_in_time": self.point_in_time,
            "parameters": {"pre_return_weight": 0.5},
            "data_policy": brief["data_policy"],
            "risk_notes": ["一致预期字段在 fixture 中为确定性样例"],
            "status": "generated",
        }
        (job_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )
        (job_dir / "factor.py").write_text(FACTOR_SOURCE, encoding="utf-8")
        (job_dir / "test_factor.py").write_text(TEST_SOURCE, encoding="utf-8")
        return SimpleNamespace(
            provider="codex_exec",
            version="test",
            job_dir=job_dir,
            files=["manifest.json", "factor.py", "test_factor.py"],
            summary="generated test plugin",
            risks=["fixture data"],
            is_mock=False,
        )


class RepairingFakeCodeAgent(FakeCodeAgent):
    def __init__(self) -> None:
        super().__init__()
        self.validation_errors: list[str] = []

    def generate(self, brief, destination):
        result = super().generate(brief, destination)
        (result.job_dir / "factor.py").write_text(
            "import os\n\ndef calculate(ctx, params):\n    return ctx.field('price')\n",
            encoding="utf-8",
        )
        return result

    def repair(self, brief, job_dir, validation_error):
        self.validation_errors.append(validation_error)
        (Path(job_dir) / "factor.py").write_text(FACTOR_SOURCE, encoding="utf-8")
        (Path(job_dir) / "test_factor.py").write_text(TEST_SOURCE, encoding="utf-8")
        return SimpleNamespace(
            provider="codex_exec",
            version="test-repair",
            job_dir=Path(job_dir),
            files=["manifest.json", "factor.py", "test_factor.py"],
            summary="repaired test plugin",
            risks=[],
            is_mock=False,
        )


def _factor_specs():
    return [
        {
            "factor_id": "earnings_surprise_adj_001",
            "factor_name": "行业中性盈利超预期",
            "plain_description": "盈利超预期且公告前反应不足",
        }
    ]


def test_pipeline_generates_validates_and_calculates_factor(tmp_path):
    result = run_factor_plugin_pipeline(
        _factor_specs(),
        {"core_hypothesis": "公告后存在滞后定价"},
        {"factor_execution": {"mode": "codex"}},
        provider=FakeCodeAgent(),
        job_root=tmp_path,
    )

    factor_id = "earnings_surprise_adj_001"
    factor_data = result.factor_data_dict[factor_id]
    assert factor_data.shape == (80, 20)
    assert factor_data.iloc[:19].isna().all().all()
    assert factor_data.notna().any().any()
    assert result.price_data.shape == (80, 20)
    assert result.returns_data.shape == (80, 20)
    assert result.factor_specs[0]["implementation_target"] == "python_plugin"

    artifacts = result.trace_artifacts
    assert artifacts["code_agent"]["provider"] == "codex_exec"
    assert artifacts["codegen_validation_reports"][0]["status"] == "passed"
    check_names = {
        check["name"] for check in artifacts["codegen_validation_reports"][0]["checks"]
    }
    assert "lookahead_perturbation" in check_names
    assert artifacts["plugin_registry"]["status"] == "promoted"
    assert artifacts["plugin_registry"]["location"].startswith("promoted/")
    assert artifacts["factor_data_manifests"][0]["source_sha256"]
    assert artifacts["factor_data_manifests"][0]["output_sha256"]
    json.dumps(artifacts, ensure_ascii=False)


def test_pipeline_rejects_manifest_for_another_factor(tmp_path):
    with pytest.raises(FactorPluginPipelineError, match="does not match"):
        run_factor_plugin_pipeline(
            _factor_specs(),
            {"core_hypothesis": "公告后存在滞后定价"},
            {"factor_execution": {"mode": "codex"}},
            provider=FakeCodeAgent(manifest_factor_id="wrong_factor"),
            job_root=tmp_path,
            run_generated_tests=False,
        )


def test_pipeline_rejects_manifest_with_incomplete_data_contract(tmp_path):
    with pytest.raises(FactorPluginPipelineError, match="required_fields"):
        run_factor_plugin_pipeline(
            _factor_specs(),
            {"core_hypothesis": "公告后存在滞后定价"},
            {"factor_execution": {"mode": "codex"}},
            provider=FakeCodeAgent(
                required_fields=[
                    "quarter_net_profit",
                    "expected_net_profit",
                    "announce_date",
                ]
            ),
            job_root=tmp_path,
            run_generated_tests=False,
        )


def test_pipeline_rejects_manifest_without_point_in_time_policy(tmp_path):
    with pytest.raises(FactorPluginPipelineError, match="PIT/frequency"):
        run_factor_plugin_pipeline(
            _factor_specs(),
            {"core_hypothesis": "公告后存在滞后定价"},
            {"factor_execution": {"mode": "codex"}},
            provider=FakeCodeAgent(point_in_time=False),
            job_root=tmp_path,
            run_generated_tests=False,
        )


def test_pipeline_cleans_provider_job_after_promotion(tmp_path):
    class CleaningFakeCodeAgent(FakeCodeAgent):
        cleaned: Path | None = None

        def cleanup(self, job_dir):
            self.cleaned = Path(job_dir)
            shutil.rmtree(self.cleaned)

    provider = CleaningFakeCodeAgent()
    run_factor_plugin_pipeline(
        _factor_specs(),
        {"core_hypothesis": "公告后存在滞后定价"},
        {"factor_execution": {"mode": "codex"}},
        provider=provider,
        job_root=tmp_path,
        run_generated_tests=True,
    )

    assert provider.cleaned is not None
    assert not provider.cleaned.exists()


def test_pipeline_repairs_once_then_promotes(tmp_path):
    provider = RepairingFakeCodeAgent()

    result = run_factor_plugin_pipeline(
        _factor_specs(),
        {"core_hypothesis": "公告后存在滞后定价"},
        {
            "sample_window": {"start": "2024-01-02", "end": "2024-05-31"},
            "factor_execution": {"mode": "codex"},
        },
        provider=provider,
        job_root=tmp_path,
    )

    attempts = result.trace_artifacts["codegen_validation_reports"][0]["attempts"]
    assert [attempt["status"] for attempt in attempts] == ["failed", "passed"]
    assert "import of 'os' is forbidden" in provider.validation_errors[0]
    assert result.trace_artifacts["plugin_registry"]["status"] == "promoted"


def test_generated_test_policy_rejects_indirect_process_and_file_access(tmp_path):
    process_test = tmp_path / "test_process.py"
    process_test.write_text(
        "from alpha_workbench.code_agent import CodexExecProvider\n",
        encoding="utf-8",
    )
    with pytest.raises(FactorPluginPipelineError, match="forbidden names"):
        _validate_generated_test_source(process_test)

    file_test = tmp_path / "test_file.py"
    file_test.write_text(
        "import pandas as pd\n\ndef test_read():\n    pd.read_csv('/etc/passwd')\n",
        encoding="utf-8",
    )
    with pytest.raises(FactorPluginPipelineError, match="read_csv"):
        _validate_generated_test_source(file_test)
