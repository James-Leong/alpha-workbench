"""
Expression Evaluator for AlphaWorkbench
表达式执行器 - 解析和执行 expression_tree
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, Union
import warnings

from alpha_workbench.schemas.backtest_schemas import ExpressionTree, NodeType, DataField


class ExpressionEvaluator:
    """
    表达式执行器
    
    将 expression_tree 转换为 Pandas 操作并执行
    支持时序操作（ts_*）和横截面操作（cs_*）
    """
    
    def __init__(self):
        """初始化执行器"""
        # 注册操作符函数
        self._binary_ops = {
            '+': lambda a, b: a + b,
            '-': lambda a, b: a - b,
            '*': lambda a, b: a * b,
            '/': lambda a, b: a / b,
            '**': lambda a, b: a ** b,
            'pow': lambda a, b: a ** b,
        }
        
        self._unary_ops = {
            'abs': lambda x: x.abs(),
            'log': lambda x: np.log(x),
            'exp': lambda x: np.exp(x),
            'sign': lambda x: np.sign(x),
            'sqrt': lambda x: np.sqrt(x),
            'neg': lambda x: -x,
        }
        
        # 时序操作函数
        self._ts_funcs = {
            'pct_change': self._ts_pct_change,
            'ts_mean': self._ts_mean,
            'ts_std': self._ts_std,
            'ts_max': self._ts_max,
            'ts_min': self._ts_min,
            'ts_sum': self._ts_sum,
            'ts_rank': self._ts_rank,
            'ts_corr': self._ts_corr,
            'ts_delta': self._ts_delta,
            'ts_delay': self._ts_delay,
            'ts_zscore': self._ts_zscore,
        }
        
        # 横截面操作函数
        self._cs_funcs = {
            'cs_rank': self._cs_rank,
            'cs_zscore': self._cs_zscore,
            'cs_percentile': self._cs_percentile,
            'cs_neutralize': self._cs_neutralize,
        }
        
        # 合并所有函数
        self._all_funcs = {
            **self._ts_funcs,
            **self._cs_funcs,
        }
    
    def evaluate(
        self,
        expression: ExpressionTree,
        data: Dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """
        执行表达式树
        
        Args:
            expression: 表达式树
            data: 原始数据字典，key为字段名（如'close', 'volume'）
        
        Returns:
            计算结果的 DataFrame
        """
        return self._eval_node(expression, data)
    
    def _eval_node(
        self,
        node: ExpressionTree,
        data: Dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """递归执行节点"""
        if node is None:
            raise ValueError("Expression tree node cannot be None")
        
        node_type = node.type
        
        if node_type == NodeType.VARIABLE:
            return self._eval_variable(node, data)
        
        elif node_type == NodeType.CONSTANT:
            return self._eval_constant(node, data)
        
        elif node_type == NodeType.BINARY:
            return self._eval_binary(node, data)
        
        elif node_type == NodeType.UNARY:
            return self._eval_unary(node, data)
        
        elif node_type == NodeType.FUNCTION:
            return self._eval_function(node, data)
        
        elif node_type == NodeType.CROSS_SECTIONAL:
            return self._eval_cross_sectional(node, data)
        
        else:
            raise ValueError(f"Unknown node type: {node_type}")
    
    def _eval_variable(
        self,
        node: ExpressionTree,
        data: Dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """执行变量节点"""
        var_name = node.name
        if isinstance(var_name, DataField):
            var_name = var_name.value
        
        if var_name not in data:
            raise KeyError(f"Variable '{var_name}' not found in data. "
                          f"Available: {list(data.keys())}")
        
        return data[var_name].copy()
    
    def _eval_constant(
        self,
        node: ExpressionTree,
        data: Dict[str, pd.DataFrame]
    ) -> Union[pd.DataFrame, int, float]:
        """执行常量节点"""
        const_value = node.value
        
        # 如果常量是数值类型，直接返回标量值
        if isinstance(const_value, (int, float)):
            return const_value
        
        # 如果是其他类型（如字符串），获取DataFrame模板并填充
        template_df = next(iter(data.values()))
        result = pd.DataFrame(
            const_value,
            index=template_df.index,
            columns=template_df.columns
        )
        return result
    
    def _eval_binary(
        self,
        node: ExpressionTree,
        data: Dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """执行二元操作节点"""
        operator = node.operator
        
        if operator not in self._binary_ops:
            raise ValueError(f"Unknown binary operator: {operator}")
        
        left_val = self._eval_node(node.left, data)
        right_val = self._eval_node(node.right, data)
        
        # 处理除零警告
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = self._binary_ops[operator](left_val, right_val)
        
        return result
    
    def _eval_unary(
        self,
        node: ExpressionTree,
        data: Dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """执行一元操作节点"""
        operator = node.operator
        
        if operator not in self._unary_ops:
            raise ValueError(f"Unknown unary operator: {operator}")
        
        operand_val = self._eval_node(node.operand, data)
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = self._unary_ops[operator](operand_val)
        
        return result
    
    def _eval_function(
        self,
        node: ExpressionTree,
        data: Dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """执行函数节点"""
        func_name = node.operator
        
        if func_name not in self._all_funcs:
            raise ValueError(f"Unknown function: {func_name}. "
                           f"Available: {list(self._all_funcs.keys())}")
        
        # 执行参数
        arg_values = []
        if node.args:
            for arg in node.args:
                arg_values.append(self._eval_node(arg, data))
        
        # 执行函数
        func = self._all_funcs[func_name]
        
        # 获取窗口参数
        window = node.window
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # 特殊处理 pct_change：第二个参数是 periods（整数）
            if func_name == 'pct_change' and len(arg_values) >= 2:
                df = arg_values[0]
                periods = arg_values[1] if isinstance(arg_values[1], (int, float)) else 1
                result = self._ts_pct_change(df, int(periods))
            elif window is not None:
                result = func(*arg_values, window=window)
            else:
                result = func(*arg_values)
        
        return result
    
    def _eval_cross_sectional(
        self,
        node: ExpressionTree,
        data: Dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """执行横截面操作节点"""
        func_name = node.operator
        
        if func_name not in self._cs_funcs:
            raise ValueError(f"Unknown cross-sectional function: {func_name}")
        
        # 执行操作数
        operand_val = self._eval_node(node.operand, data)
        
        func = self._cs_funcs[func_name]
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = func(operand_val)
        
        return result
    
    # ========== 时序操作函数 ==========
    
    def _ts_pct_change(self, df: pd.DataFrame, window: int = 1) -> pd.DataFrame:
        """计算百分比变化"""
        return df.pct_change(periods=window)
    
    def _ts_mean(self, df: pd.DataFrame, window: int) -> pd.DataFrame:
        """时序均值"""
        return df.rolling(window=window, min_periods=1).mean()
    
    def _ts_std(self, df: pd.DataFrame, window: int) -> pd.DataFrame:
        """时序标准差"""
        return df.rolling(window=window, min_periods=2).std()
    
    def _ts_max(self, df: pd.DataFrame, window: int) -> pd.DataFrame:
        """时序最大值"""
        return df.rolling(window=window, min_periods=1).max()
    
    def _ts_min(self, df: pd.DataFrame, window: int) -> pd.DataFrame:
        """时序最小值"""
        return df.rolling(window=window, min_periods=1).min()
    
    def _ts_sum(self, df: pd.DataFrame, window: int) -> pd.DataFrame:
        """时序求和"""
        return df.rolling(window=window, min_periods=1).sum()
    
    def _ts_rank(self, df: pd.DataFrame, window: int) -> pd.DataFrame:
        """时序排名（每天在所有股票中排名）"""
        return df.rank(axis=1, pct=True)
    
    def _ts_corr(self, df1: pd.DataFrame, df2: pd.DataFrame, window: int) -> pd.DataFrame:
        """时序相关系数"""
        return df1.rolling(window=window).corr(df2)
    
    def _ts_delta(self, df: pd.DataFrame, window: int = 1) -> pd.DataFrame:
        """时序差分"""
        return df.diff(periods=window)
    
    def _ts_delay(self, df: pd.DataFrame, window: int) -> pd.DataFrame:
        """时序延迟"""
        return df.shift(periods=window)
    
    def _ts_zscore(self, df: pd.DataFrame, window: int) -> pd.DataFrame:
        """时序Z-score标准化"""
        mean = df.rolling(window=window, min_periods=1).mean()
        std = df.rolling(window=window, min_periods=2).std()
        return (df - mean) / std.replace(0, np.nan)
    
    # ========== 横截面操作函数 ==========
    
    def _cs_rank(self, df: pd.DataFrame) -> pd.DataFrame:
        """横截面排名（每天在所有股票中排名，归一化到0-1）"""
        return df.rank(axis=1, pct=True, method='average')
    
    def _cs_zscore(self, df: pd.DataFrame) -> pd.DataFrame:
        """横截面Z-score标准化（每天独立计算）"""
        mean = df.mean(axis=1)
        std = df.std(axis=1)
        return df.sub(mean, axis=0).div(std.replace(0, np.nan), axis=0)
    
    def _cs_percentile(self, df: pd.DataFrame) -> pd.DataFrame:
        """横截面百分位数"""
        return df.rank(axis=1, pct=True, method='average')
    
    def _cs_neutralize(self, df: pd.DataFrame, group_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """横截面中性化（行业/市值中性化）"""
        # 简化实现：只进行横截面去均值
        mean = df.mean(axis=1)
        return df.sub(mean, axis=0)
    
    def validate_expression(self, expression: ExpressionTree) -> bool:
        """
        验证表达式树是否有效
        
        Args:
            expression: 表达式树
            
        Returns:
            是否有效
        """
        try:
            self._validate_node(expression)
            return True
        except Exception as e:
            print(f"Expression validation failed: {e}")
            return False
    
    def _validate_node(self, node: ExpressionTree) -> None:
        """递归验证节点"""
        if node is None:
            raise ValueError("Node cannot be None")
        
        node_type = node.type
        
        if node_type == NodeType.VARIABLE:
            if node.name is None:
                raise ValueError("Variable node must have a name")
        
        elif node_type == NodeType.CONSTANT:
            if node.value is None:
                raise ValueError("Constant node must have a value")
        
        elif node_type == NodeType.BINARY:
            if node.operator not in self._binary_ops:
                raise ValueError(f"Unknown binary operator: {node.operator}")
            if node.left is None or node.right is None:
                raise ValueError("Binary node must have left and right children")
            self._validate_node(node.left)
            self._validate_node(node.right)
        
        elif node_type == NodeType.UNARY:
            if node.operator not in self._unary_ops:
                raise ValueError(f"Unknown unary operator: {node.operator}")
            if node.operand is None:
                raise ValueError("Unary node must have an operand")
            self._validate_node(node.operand)
        
        elif node_type == NodeType.FUNCTION:
            if node.operator not in self._all_funcs:
                raise ValueError(f"Unknown function: {node.operator}")
            if node.args:
                for arg in node.args:
                    self._validate_node(arg)
        
        elif node_type == NodeType.CROSS_SECTIONAL:
            if node.operator not in self._cs_funcs:
                raise ValueError(f"Unknown cross-sectional function: {node.operator}")
            if node.operand is None:
                raise ValueError("Cross-sectional node must have an operand")
            self._validate_node(node.operand)
