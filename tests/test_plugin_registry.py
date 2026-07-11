from __future__ import annotations

import json
from pathlib import Path

import pytest

from alpha_workbench.factor_runtime import (
    PluginPromotionError,
    PluginRegistry,
)
from alpha_workbench.factor_runtime.plugin_loader import PluginLoader


def _write_plugin(directory: Path, *, factor_id: str = "earnings_surprise") -> Path:
    directory.mkdir()
    manifest = {
        "factor_id": factor_id,
        "factor_name": "Earnings Surprise",
        "version": "0.1.0",
        "entrypoint": "factor:calculate",
        "required_fields": ["close"],
        "lookback_days": 1,
        "frequency": "daily",
        "point_in_time": True,
        "parameters": {},
        "data_policy": {"signal_effective_rule": "next_trade_date"},
        "risk_notes": [],
        "status": "generated",
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (directory / "factor.py").write_text(
        "def calculate(ctx, params):\n    return ctx.field('close')\n",
        encoding="utf-8",
    )
    (directory / "test_factor.py").write_text(
        "def test_placeholder():\n    assert True\n",
        encoding="utf-8",
    )
    return directory


def _passed_report(factor_id: str = "earnings_surprise") -> dict[str, object]:
    return {
        "factor_id": factor_id,
        "status": "passed",
        "checks": [
            {"name": name, "status": "passed"}
            for name in (
                "manifest",
                "factor_ast",
                "entrypoint",
                "generated_pytest",
                "fixture_smoke",
                "lookahead_perturbation",
            )
        ],
    }


def test_registry_promotes_validated_plugin_atomically_and_idempotently(tmp_path):
    plugin_dir = _write_plugin(tmp_path / "generated")
    registry = PluginRegistry(tmp_path / "registry")
    report = _passed_report()

    first = registry.promote(plugin_dir, report)
    second = registry.promote(plugin_dir, report)

    assert first == second
    assert first.registry_id.startswith("earnings_surprise:0.1.0:")
    assert first.relative_location.startswith("promoted/earnings_surprise/0.1.0/")
    assert not first.relative_location.startswith("/")
    assert {path.name for path in first.path.iterdir()} == {
        "manifest.json",
        "factor.py",
        "test_factor.py",
        "promotion.json",
    }
    metadata = json.loads((first.path / "promotion.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "promoted"
    assert metadata["source_sha256"] == first.source_sha256
    assert metadata["manifest_sha256"] == first.manifest_sha256
    assert metadata["artifact_sha256"] == first.artifact_sha256
    assert metadata["file_sha256"]["manifest.json"] == first.manifest_sha256
    assert metadata["validation_sha256"]
    assert PluginLoader(first.path).inspect()[1].factor_id == "earnings_surprise"
    assert registry.verify(first.path) == first
    assert (first.path.stat().st_mode & 0o222) == 0
    assert not list(first.path.parent.glob(".*.tmp-*"))


def test_registry_rejects_failed_validation(tmp_path):
    plugin_dir = _write_plugin(tmp_path / "generated")

    with pytest.raises(PluginPromotionError, match="passed validation"):
        PluginRegistry(tmp_path / "registry").promote(
            plugin_dir,
            {"status": "failed", "checks": []},
        )


def test_registry_rejects_incomplete_passed_validation(tmp_path):
    plugin_dir = _write_plugin(tmp_path / "generated")

    with pytest.raises(PluginPromotionError, match="missing passed checks"):
        PluginRegistry(tmp_path / "registry").promote(
            plugin_dir,
            {"factor_id": "earnings_surprise", "status": "passed", "checks": []},
        )


def test_registry_rejects_unsafe_manifest_path_components(tmp_path):
    plugin_dir = _write_plugin(tmp_path / "generated", factor_id="../escape")

    with pytest.raises(PluginPromotionError, match="unsafe factor_id"):
        PluginRegistry(tmp_path / "registry").promote(
            plugin_dir,
            _passed_report("../escape"),
        )


def test_registry_rejects_tampered_promoted_manifest(tmp_path):
    plugin_dir = _write_plugin(tmp_path / "generated")
    registry = PluginRegistry(tmp_path / "registry")
    report = _passed_report()
    promoted = registry.promote(plugin_dir, report)
    (promoted.path / "manifest.json").chmod(0o644)
    (promoted.path / "manifest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(PluginPromotionError, match="file hash mismatch"):
        registry.promote(plugin_dir, report)


def test_registry_rejects_tampered_promotion_metadata(tmp_path):
    plugin_dir = _write_plugin(tmp_path / "generated")
    registry = PluginRegistry(tmp_path / "registry")
    report = _passed_report()
    promoted = registry.promote(plugin_dir, report)
    metadata_path = promoted.path / "promotion.json"
    metadata_path.chmod(0o644)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["registry_id"] = "tampered"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(PluginPromotionError, match="metadata mismatch"):
        registry.promote(plugin_dir, report)
