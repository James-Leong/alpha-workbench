"""Filesystem registry for validated and promoted factor plugins."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, Mapping
from uuid import uuid4

from alpha_workbench.factor_runtime.plugin_loader import PluginLoader


class PluginPromotionError(ValueError):
    """Raised when a plugin cannot be promoted into the registry."""


_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_PLUGIN_FILES = ("manifest.json", "factor.py", "test_factor.py")
_REQUIRED_VALIDATION_CHECKS = {
    "manifest",
    "factor_ast",
    "entrypoint",
    "generated_pytest",
    "fixture_smoke",
    "lookahead_perturbation",
}


@dataclass(frozen=True)
class PromotedPlugin:
    registry_id: str
    factor_id: str
    version: str
    source_sha256: str
    manifest_sha256: str
    artifact_sha256: str
    path: Path
    relative_location: str

    def trace_dict(self) -> dict[str, Any]:
        return {
            "status": "promoted",
            "registry_id": self.registry_id,
            "factor_id": self.factor_id,
            "version": self.version,
            "source_sha256": self.source_sha256,
            "manifest_sha256": self.manifest_sha256,
            "artifact_sha256": self.artifact_sha256,
            "location": self.relative_location,
        }


class PluginRegistry:
    """Promote validated plugins into an immutable content-addressed tree."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.promoted_root = self.root / "promoted"

    def promote(
        self,
        plugin_dir: str | Path,
        validation_report: Mapping[str, Any],
    ) -> PromotedPlugin:
        if validation_report.get("status") != "passed":
            raise PluginPromotionError("only plugins with a passed validation report can be promoted")
        checks = validation_report.get("checks")
        if not isinstance(checks, list):
            raise PluginPromotionError("validation report checks must be a list")
        passed_checks = {
            item.get("name")
            for item in checks
            if isinstance(item, Mapping) and item.get("status") == "passed"
        }
        missing_checks = sorted(_REQUIRED_VALIDATION_CHECKS - passed_checks)
        if missing_checks:
            raise PluginPromotionError(
                f"validation report is missing passed checks: {', '.join(missing_checks)}"
            )

        requested_source = Path(plugin_dir).expanduser()
        if requested_source.is_symlink():
            raise PluginPromotionError("plugin source directory cannot be a symbolic link")
        source_dir = requested_source.resolve()
        missing = [name for name in _PLUGIN_FILES if not (source_dir / name).is_file()]
        if missing:
            raise PluginPromotionError(
                f"plugin cannot be promoted; missing files: {', '.join(missing)}"
            )
        if any((source_dir / name).is_symlink() for name in _PLUGIN_FILES):
            raise PluginPromotionError("plugin files cannot be symbolic links")
        _, manifest, _ = PluginLoader(source_dir).inspect()
        factor_id = manifest.factor_id
        version = manifest.version
        if validation_report.get("factor_id") != factor_id:
            raise PluginPromotionError("validation report factor_id does not match manifest")
        self._validate_component(factor_id, "factor_id")
        self._validate_component(version, "version")

        file_hashes = {
            name: hashlib.sha256((source_dir / name).read_bytes()).hexdigest()
            for name in _PLUGIN_FILES
        }
        source_sha = file_hashes["factor.py"]
        manifest_sha = file_hashes["manifest.json"]
        artifact_sha = _json_sha256(file_hashes)
        validation_sha = _json_sha256(validation_report)
        short_sha = artifact_sha[:16]
        relative = Path("promoted") / factor_id / version / short_sha
        target = self.root / relative
        registry_id = f"{factor_id}:{version}:{short_sha}"
        promoted = PromotedPlugin(
            registry_id=registry_id,
            factor_id=factor_id,
            version=version,
            source_sha256=source_sha,
            manifest_sha256=manifest_sha,
            artifact_sha256=artifact_sha,
            path=target,
            relative_location=relative.as_posix(),
        )
        if target.is_symlink():
            raise PluginPromotionError(f"promoted plugin target cannot be a symlink: {target}")
        if target.is_dir():
            self._verify_existing(target, promoted, file_hashes, validation_sha)
            _make_read_only(target)
            return promoted

        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / f".{short_sha}.tmp-{uuid4().hex}"
        try:
            temporary.mkdir()
            for name in _PLUGIN_FILES:
                shutil.copy2(source_dir / name, temporary / name)
            metadata = {
                **promoted.trace_dict(),
                "promoted_at": datetime.now(UTC).isoformat(),
                "validation_sha256": validation_sha,
                "file_sha256": file_hashes,
            }
            (temporary / "promotion.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            os.replace(temporary, target)
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            if target.is_dir():
                self._verify_existing(target, promoted, file_hashes, validation_sha)
                _make_read_only(target)
                return promoted
            raise

        self._verify_existing(target, promoted, file_hashes, validation_sha)
        _make_read_only(target)
        return promoted

    def verify(self, plugin_dir: str | Path) -> PromotedPlugin:
        """Verify a promoted directory immediately before runtime use."""

        target = Path(plugin_dir).expanduser().resolve()
        try:
            relative = target.relative_to(self.root)
            metadata = json.loads((target / "promotion.json").read_text(encoding="utf-8"))
            file_hashes = metadata["file_sha256"]
            validation_sha = metadata["validation_sha256"]
            promoted = PromotedPlugin(
                registry_id=metadata["registry_id"],
                factor_id=metadata["factor_id"],
                version=metadata["version"],
                source_sha256=metadata["source_sha256"],
                manifest_sha256=metadata["manifest_sha256"],
                artifact_sha256=metadata["artifact_sha256"],
                path=target,
                relative_location=relative.as_posix(),
            )
        except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
            raise PluginPromotionError("promoted plugin metadata is invalid") from exc
        if not isinstance(file_hashes, dict) or set(file_hashes) != set(_PLUGIN_FILES):
            raise PluginPromotionError("promoted plugin file hash metadata is invalid")
        expected_id = (
            f"{promoted.factor_id}:{promoted.version}:{promoted.artifact_sha256[:16]}"
        )
        if promoted.registry_id != expected_id:
            raise PluginPromotionError("promoted plugin registry identity is invalid")
        expected_relative = (
            Path("promoted")
            / promoted.factor_id
            / promoted.version
            / promoted.artifact_sha256[:16]
        ).as_posix()
        if promoted.relative_location != expected_relative:
            raise PluginPromotionError("promoted plugin location is not canonical")
        self._verify_existing(target, promoted, file_hashes, validation_sha)
        return promoted

    @staticmethod
    def _validate_component(value: str, field: str) -> None:
        if not _SAFE_COMPONENT.fullmatch(value):
            raise PluginPromotionError(f"unsafe {field} for registry path: {value!r}")

    @staticmethod
    def _verify_existing(
        target: Path,
        expected: PromotedPlugin,
        expected_file_hashes: Mapping[str, str],
        expected_validation_sha: str,
    ) -> None:
        if target.is_symlink():
            raise PluginPromotionError(f"promoted plugin target cannot be a symlink: {target}")
        required_files = (*_PLUGIN_FILES, "promotion.json")
        invalid_files = [
            name
            for name in required_files
            if not (target / name).is_file() or (target / name).is_symlink()
        ]
        if invalid_files:
            raise PluginPromotionError(
                f"promoted plugin is incomplete or unsafe: {', '.join(invalid_files)}"
            )
        actual_hashes = {
            name: hashlib.sha256((target / name).read_bytes()).hexdigest()
            for name in _PLUGIN_FILES
        }
        if actual_hashes != dict(expected_file_hashes):
            raise PluginPromotionError("promoted plugin file hash mismatch")
        if expected.source_sha256 != actual_hashes["factor.py"]:
            raise PluginPromotionError("promoted plugin source hash metadata mismatch")
        if expected.manifest_sha256 != actual_hashes["manifest.json"]:
            raise PluginPromotionError("promoted plugin manifest hash metadata mismatch")
        if expected.artifact_sha256 != _json_sha256(actual_hashes):
            raise PluginPromotionError("promoted plugin artifact hash metadata mismatch")
        try:
            metadata = json.loads((target / "promotion.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PluginPromotionError("promoted plugin metadata is invalid") from exc
        expected_metadata = {
            **expected.trace_dict(),
            "validation_sha256": expected_validation_sha,
            "file_sha256": dict(expected_file_hashes),
        }
        mismatched = [
            key for key, value in expected_metadata.items() if metadata.get(key) != value
        ]
        if mismatched or not _is_sha256(metadata.get("validation_sha256")):
            fields = ", ".join(mismatched or ["validation_sha256"])
            raise PluginPromotionError(f"promoted plugin metadata mismatch: {fields}")
        PluginLoader(target).inspect()


def _json_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _make_read_only(target: Path) -> None:
    for name in (*_PLUGIN_FILES, "promotion.json"):
        (target / name).chmod(0o444)
    target.chmod(0o555)
