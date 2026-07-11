"""Validated loading of factor plugin directories."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from alpha_workbench.factor_runtime.context import FactorContext
from alpha_workbench.factor_runtime.contracts import FactorPluginManifest
from alpha_workbench.factor_runtime.validators import validate_plugin_file


class PluginLoadError(ValueError):
    """Raised when a plugin directory cannot be loaded safely."""


FactorCalculate = Callable[[FactorContext, dict[str, Any]], Any]
_MANIFEST_SIZE_LIMIT = 256 * 1024
_FACTOR_SOURCE_SIZE_LIMIT = 2 * 1024 * 1024


@dataclass(frozen=True)
class LoadedFactorPlugin:
    directory: Path
    manifest: FactorPluginManifest
    module: ModuleType
    calculate: FactorCalculate


class PluginLoader:
    """Load a plugin only after its manifest and source pass validation."""

    def __init__(self, plugin_dir: str | Path | None = None) -> None:
        self.plugin_dir = Path(plugin_dir) if plugin_dir is not None else None

    def _load_in_process(self, plugin_dir: str | Path | None = None) -> LoadedFactorPlugin:
        """Import inside the isolated worker; never call from the API process."""

        directory, manifest, factor_path = self.inspect(plugin_dir)
        module = self._import_module(factor_path)
        calculate = getattr(module, "calculate", None)
        if not callable(calculate):
            raise PluginLoadError("factor.py must define callable calculate(ctx, params)")

        return LoadedFactorPlugin(
            directory=directory,
            manifest=manifest,
            module=module,
            calculate=calculate,
        )

    def inspect(
        self, plugin_dir: str | Path | None = None
    ) -> tuple[Path, FactorPluginManifest, Path]:
        """Validate plugin files without importing or executing generated code."""

        directory = Path(plugin_dir) if plugin_dir is not None else self.plugin_dir
        if directory is None:
            raise PluginLoadError("a plugin directory is required")
        if directory.is_symlink():
            raise PluginLoadError(f"plugin directory cannot be a symbolic link: {directory}")
        if not directory.is_dir():
            raise PluginLoadError(f"plugin directory does not exist: {directory}")

        manifest_path = directory / "manifest.json"
        factor_path = directory / "factor.py"
        if not manifest_path.is_file():
            raise PluginLoadError(f"missing plugin manifest: {manifest_path}")
        if not factor_path.is_file():
            raise PluginLoadError(f"missing plugin source: {factor_path}")
        if manifest_path.is_symlink() or factor_path.is_symlink():
            raise PluginLoadError("plugin manifest and source must be regular files, not symlinks")
        if manifest_path.stat().st_size > _MANIFEST_SIZE_LIMIT:
            raise PluginLoadError("plugin manifest exceeds 256 KiB")
        if factor_path.stat().st_size > _FACTOR_SOURCE_SIZE_LIMIT:
            raise PluginLoadError("plugin source exceeds 2 MiB")

        manifest = FactorPluginManifest.from_json(manifest_path)
        if manifest.entrypoint != "factor:calculate":
            raise PluginLoadError(
                "plugin entrypoint must be exactly 'factor:calculate', "
                f"got {manifest.entrypoint!r}"
            )

        validate_plugin_file(factor_path)
        return directory.resolve(), manifest, factor_path.resolve()

    @staticmethod
    def _import_module(factor_path: Path) -> ModuleType:
        digest = hashlib.sha256(str(factor_path.resolve()).encode()).hexdigest()[:16]
        module_name = f"_alpha_workbench_factor_{digest}"
        spec = importlib.util.spec_from_file_location(module_name, factor_path)
        if spec is None or spec.loader is None:
            raise PluginLoadError(f"cannot create import spec for {factor_path}")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            raise PluginLoadError(f"failed to import plugin {factor_path}: {exc}") from exc
        return module
