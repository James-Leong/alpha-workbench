"""Minimal factor compiler.

The MVP validates formula trees and returns a compiled descriptor. Real factor
calculation can later attach executable functions behind the same API.
"""

from __future__ import annotations

from typing import Any


SUPPORTED_OPS = {
    "abs",
    "add",
    "divide",
    "industry_zscore",
    "multiply",
    "ref",
    "subtract",
}


def _validate_node(node: Any) -> None:
    if isinstance(node, (str, int, float)):
        return
    if not isinstance(node, dict):
        raise ValueError(f"Unsupported formula node: {node!r}")
    op = node.get("op")
    args = node.get("args")
    if op not in SUPPORTED_OPS:
        raise ValueError(f"Unsupported formula op: {op!r}")
    if not isinstance(args, list) or not args:
        raise ValueError(f"Formula op {op!r} must have non-empty args.")
    for arg in args:
        _validate_node(arg)


def compile_factor(factor_spec: dict[str, Any]) -> dict[str, Any]:
    required = ["factor_id", "factor_name", "formula_tree", "required_fields"]
    missing = [key for key in required if key not in factor_spec]
    if missing:
        raise ValueError(f"FactorSpec missing fields: {missing}")
    _validate_node(factor_spec["formula_tree"])
    return {
        "factor_id": factor_spec["factor_id"],
        "factor_name": factor_spec["factor_name"],
        "required_fields": factor_spec["required_fields"],
        "formula_tree": factor_spec["formula_tree"],
        "status": "compiled",
    }


def compile_factors(factor_specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [compile_factor(spec) for spec in factor_specs]
