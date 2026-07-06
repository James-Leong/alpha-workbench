"""Minimal factor compiler.

The MVP validates formula trees and returns a compiled descriptor. Real factor
calculation can later attach executable functions behind the same API.
"""

from __future__ import annotations

from typing import Any

from alpha_workbench.factor_engine.expression_evaluator import ExpressionEvaluator
from alpha_workbench.schemas.backtest_schemas import ExpressionTree, NodeType


# 与 expression_evaluator 对齐的操作符集合（同时兼容常见 LLM 别名）
SUPPORTED_OPS = {
    # 二元操作符
    "+",
    "-",
    "*",
    "/",
    "**",
    "pow",
    "add",
    "subtract",
    "multiply",
    "divide",
    # 一元操作符
    "abs",
    "log",
    "exp",
    "sign",
    "sqrt",
    "neg",
    # 时序函数（及别名）
    "pct_change",
    "ts_mean",
    "ts_std",
    "ts_max",
    "ts_min",
    "ts_sum",
    "ts_rank",
    "ts_corr",
    "ts_delta",
    "ts_delay",
    "ts_zscore",
    "ts_pct_change",
    # 横截面函数（及别名）
    "cs_rank",
    "cs_zscore",
    "cs_percentile",
    "cs_neutralize",
    "industry_zscore",
    "zscore",
    "rank",
    "winsorize",
    # 字段引用
    "ref",
}


_BINARY_ALIAS = {
    "add": "+",
    "subtract": "-",
    "multiply": "*",
    "divide": "/",
}

_UNARY_OPS = {"abs", "log", "exp", "sign", "sqrt", "neg"}
_TS_FUNCS = {
    "pct_change",
    "ts_mean",
    "ts_std",
    "ts_max",
    "ts_min",
    "ts_sum",
    "ts_rank",
    "ts_corr",
    "ts_delta",
    "ts_delay",
    "ts_zscore",
    "ts_pct_change",
}
_TS_ALIAS = {
    "pct_change": "pct_change",
    "ts_pct_change": "pct_change",
}
_CS_FUNCS = {
    "cs_rank",
    "cs_zscore",
    "cs_percentile",
    "cs_neutralize",
    "industry_zscore",
    "zscore",
    "rank",
    "winsorize",
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


def formula_tree_to_expression_tree(node: Any) -> ExpressionTree:
    """将 dict 形式的 formula_tree（op/args）转换为 ExpressionTree Pydantic 模型。

    这是 compiler 与 expression_evaluator / factor_calculator 收敛的关键：
    校验通过后即可交给 ExpressionEvaluator 执行。
    """
    if isinstance(node, str):
        return ExpressionTree(type=NodeType.VARIABLE, name=node)
    if isinstance(node, (int, float)):
        return ExpressionTree(type=NodeType.CONSTANT, value=node)
    if not isinstance(node, dict):
        raise ValueError(f"Unsupported formula node: {node!r}")

    op = node.get("op")
    args = node.get("args", [])

    if op in _BINARY_ALIAS or op in {"+", "-", "*", "/", "**", "pow"}:
        if len(args) != 2:
            raise ValueError(f"Binary op {op!r} requires 2 args, got {len(args)}")
        return ExpressionTree(
            type=NodeType.BINARY,
            operator=_BINARY_ALIAS.get(op, op),
            left=formula_tree_to_expression_tree(args[0]),
            right=formula_tree_to_expression_tree(args[1]),
        )

    if op in _UNARY_OPS:
        if len(args) != 1:
            raise ValueError(f"Unary op {op!r} requires 1 arg, got {len(args)}")
        return ExpressionTree(
            type=NodeType.UNARY,
            operator=op,
            operand=formula_tree_to_expression_tree(args[0]),
        )

    if op in _TS_FUNCS:
        return ExpressionTree(
            type=NodeType.FUNCTION,
            operator=_TS_ALIAS.get(op, op),
            args=[formula_tree_to_expression_tree(arg) for arg in args],
        )

    if op in _CS_FUNCS:
        if len(args) < 1:
            raise ValueError(f"Cross-sectional op {op!r} requires at least 1 arg, got {len(args)}")
        return ExpressionTree(
            type=NodeType.CROSS_SECTIONAL,
            operator=op,
            operand=formula_tree_to_expression_tree(args[0]),
        )

    if op == "ref":
        if len(args) != 1:
            raise ValueError(f"ref requires 1 arg, got {len(args)}")
        arg = args[0]
        if not isinstance(arg, str):
            raise ValueError(f"ref arg must be a field name string, got {arg!r}")
        return ExpressionTree(type=NodeType.VARIABLE, name=arg)

    raise ValueError(f"Unsupported formula op during conversion: {op!r}")


def compile_factor(factor_spec: dict[str, Any]) -> dict[str, Any]:
    required = ["factor_id", "factor_name", "formula_tree", "required_fields"]
    missing = [key for key in required if key not in factor_spec]
    if missing:
        return {
            "factor_id": factor_spec.get("factor_id", "unknown"),
            "factor_name": factor_spec.get("factor_name", "unknown"),
            "required_fields": factor_spec.get("required_fields", []),
            "formula_tree": factor_spec.get("formula_tree"),
            "status": "invalid",
            "error": f"FactorSpec missing fields: {missing}",
            "expression_tree_valid": False,
            "expression_tree": None,
        }

    validation_error: str | None = None
    try:
        _validate_node(factor_spec["formula_tree"])
    except Exception as exc:
        validation_error = str(exc)

    # 尝试转换为 ExpressionTree 并复用 ExpressionEvaluator 校验
    expression_tree = None
    evaluator_validation = False
    if validation_error is None:
        try:
            expression_tree = formula_tree_to_expression_tree(factor_spec["formula_tree"])
            evaluator = ExpressionEvaluator()
            evaluator_validation = evaluator.validate_expression(expression_tree)
        except Exception as exc:
            evaluator_validation = False
            expression_tree = None
            validation_error = validation_error or str(exc)

    return {
        "factor_id": factor_spec["factor_id"],
        "factor_name": factor_spec["factor_name"],
        "required_fields": factor_spec["required_fields"],
        "formula_tree": factor_spec["formula_tree"],
        "status": "compiled" if evaluator_validation else "invalid",
        "error": validation_error,
        "expression_tree_valid": evaluator_validation,
        "expression_tree": expression_tree.model_dump(mode="json") if expression_tree is not None else None,
    }


def compile_factors(factor_specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [compile_factor(spec) for spec in factor_specs]
