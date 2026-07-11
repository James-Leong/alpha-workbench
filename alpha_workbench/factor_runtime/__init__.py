"""Public contracts and execution API for AlphaWorkbench factor plugins."""

from alpha_workbench.factor_runtime.context import FactorContext
from alpha_workbench.factor_runtime.contracts import FactorCodingBrief, FactorPluginManifest
from alpha_workbench.factor_runtime.lookahead_audit import (
    LookaheadAuditError,
    run_lookahead_perturbation_audit,
)
from alpha_workbench.factor_runtime.plugin_loader import PluginLoadError
from alpha_workbench.factor_runtime.runner import (
    FactorResultValidationError,
    run_factor,
    validate_factor_result,
)
from alpha_workbench.factor_runtime.sandbox import FactorSandboxError, SandboxedFactorExecutor
from alpha_workbench.factor_runtime.registry import (
    PluginPromotionError,
    PluginRegistry,
    PromotedPlugin,
)
from alpha_workbench.factor_runtime.validators import (
    PluginValidationError,
    validate_plugin_ast,
    validate_plugin_file,
    validate_plugin_source,
)

__all__ = [
    "FactorCodingBrief",
    "FactorContext",
    "FactorPluginManifest",
    "FactorResultValidationError",
    "FactorSandboxError",
    "LookaheadAuditError",
    "PluginLoadError",
    "PluginPromotionError",
    "PluginRegistry",
    "PluginValidationError",
    "PromotedPlugin",
    "SandboxedFactorExecutor",
    "run_factor",
    "run_lookahead_perturbation_audit",
    "validate_factor_result",
    "validate_plugin_ast",
    "validate_plugin_file",
    "validate_plugin_source",
]
