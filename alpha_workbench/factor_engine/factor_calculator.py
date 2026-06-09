"""
Factor Calculator for AlphaWorkbench
因子计算器 - 根据 FactorSpec 计算因子值
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional, Union
import pandas as pd
import numpy as np

from alpha_workbench.schemas.backtest_schemas import (
    FactorSpec,
    DataRequirements,
    DataField
)
from alpha_workbench.factor_engine.expression_evaluator import ExpressionEvaluator


class FactorCalculator:
    """
    因子计算器
    
    根据 FactorSpec 中的 expression_tree 和 data_requirements
    计算因子值
    """
    
    def __init__(self):
        """初始化计算器"""
        self.evaluator = ExpressionEvaluator()
    
    def calculate(
        self,
        factor_spec: FactorSpec,
        raw_data: Dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """
        根据 FactorSpec 计算因子值
        
        Args:
            factor_spec: 因子规格
            raw_data: 原始数据字典，key为字段名
        
        Returns:
            因子值 DataFrame
        """
        if factor_spec.expression_tree is None:
            raise ValueError(f"FactorSpec '{factor_spec.factor_id}' has no expression_tree")
        
        # 验证表达式
        if not self.evaluator.validate_expression(factor_spec.expression_tree):
            raise ValueError(f"Invalid expression_tree in FactorSpec '{factor_spec.factor_id}'")
        
        # 验证数据需求
        self._validate_data_requirements(factor_spec.data_requirements, raw_data)
        
        # 执行表达式计算
        factor_data = self.evaluator.evaluate(
            factor_spec.expression_tree,
            raw_data
        )
        
        # 后处理（处理NaN、极值等）
        factor_data = self._post_process(factor_data)
        
        return factor_data
    
    def calculate_from_json(
        self,
        json_path: Union[str, Path],
        raw_data: Dict[str, pd.DataFrame]
    ) -> Dict[str, pd.DataFrame]:
        """
        从 JSON 文件加载 FactorSpec 并计算所有因子
        
        Args:
            json_path: JSON 文件路径
            raw_data: 原始数据字典
        
        Returns:
            因子值字典，key为factor_id
        """
        json_path = Path(json_path)
        
        if not json_path.exists():
            raise FileNotFoundError(f"JSON file not found: {json_path}")
        
        # 加载 JSON
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 解析 FactorSpec 列表
        factors_data = data.get('factors', [])
        if not factors_data:
            raise ValueError(f"No factors found in JSON file: {json_path}")
        
        # 计算每个因子
        results = {}
        for factor_dict in factors_data:
            factor_spec = FactorSpec.from_dict(factor_dict)
            
            print(f"Calculating factor: {factor_spec.factor_id} ({factor_spec.factor_name})")
            
            try:
                factor_data = self.calculate(factor_spec, raw_data)
                results[factor_spec.factor_id] = factor_data
                print(f"  ✓ Success: shape={factor_data.shape}")
            except Exception as e:
                print(f"  ✗ Failed: {e}")
                results[factor_spec.factor_id] = None
        
        return results
    
    def _validate_data_requirements(
        self,
        requirements: DataRequirements,
        raw_data: Dict[str, pd.DataFrame]
    ) -> None:
        """
        验证数据需求是否满足
        
        Args:
            requirements: 数据需求
            raw_data: 原始数据
        """
        required_fields = requirements.fields
        
        for field in required_fields:
            field_name = field.value if isinstance(field, DataField) else field
            if field_name not in raw_data:
                raise KeyError(
                    f"Required field '{field_name}' not found in raw_data. "
                    f"Available: {list(raw_data.keys())}"
                )
    
    def _post_process(self, factor_data: pd.DataFrame) -> pd.DataFrame:
        """
        因子值后处理
        
        - 处理极值（winsorize）
        - 处理NaN
        
        Args:
            factor_data: 原始因子值
        
        Returns:
            处理后的因子值
        """
        # 复制数据避免修改原始值
        result = factor_data.copy()
        
        # Winsorize 极值（1%和99%分位数）
        lower = result.quantile(0.01, axis=1)
        upper = result.quantile(0.99, axis=1)
        
        for col in result.columns:
            result[col] = result[col].clip(lower=lower, upper=upper)
        
        return result
    
    def generate_raw_data(
        self,
        requirements: DataRequirements,
        n_stocks: int = 50,
        n_days: int = 252,
        seed: int = 42
    ) -> Dict[str, pd.DataFrame]:
        """
        根据数据需求生成模拟原始数据
        
        Args:
            requirements: 数据需求
            n_stocks: 股票数量
            n_days: 交易日数量
            seed: 随机种子
        
        Returns:
            原始数据字典
        """
        np.random.seed(seed)
        
        from datetime import datetime, timedelta
        
        # 生成日期索引
        start_date = datetime.now() - timedelta(days=n_days)
        dates = pd.date_range(start=start_date, periods=n_days, freq='B')
        from alpha_workbench.data.sample_data import generate_sample_security_codes

        stocks = generate_sample_security_codes(n_stocks)
        
        raw_data = {}
        
        # 生成价格数据
        if DataField.CLOSE in requirements.fields or \
           DataField.OPEN in requirements.fields or \
           DataField.HIGH in requirements.fields or \
           DataField.LOW in requirements.fields or \
           DataField.VWAP in requirements.fields:
            
            # 生成基础价格（随机游走）
            close_prices = pd.DataFrame(index=dates, columns=stocks)
            for stock in stocks:
                returns = np.random.normal(0.0005, 0.02, n_days)
                prices = 100 * np.exp(np.cumsum(returns))
                close_prices[stock] = prices
            
            raw_data['close'] = close_prices
            
            # 根据close生成其他价格字段
            if DataField.OPEN in requirements.fields:
                # open = close.shift(1) * (1 + small_noise)
                noise = np.random.normal(0, 0.001, (n_days, n_stocks))
                raw_data['open'] = close_prices.shift(1) * (1 + noise)
            
            if DataField.HIGH in requirements.fields:
                # high = max(open, close) * (1 + positive_noise)
                noise = np.abs(np.random.normal(0, 0.005, (n_days, n_stocks)))
                raw_data['high'] = pd.concat([
                    raw_data.get('open', close_prices),
                    close_prices
                ]).max(level=0) * (1 + noise)
            
            if DataField.LOW in requirements.fields:
                # low = min(open, close) * (1 - positive_noise)
                noise = np.abs(np.random.normal(0, 0.005, (n_days, n_stocks)))
                raw_data['low'] = pd.concat([
                    raw_data.get('open', close_prices),
                    close_prices
                ]).min(level=0) * (1 - noise)
            
            if DataField.VWAP in requirements.fields:
                # vwap ≈ (high + low + close) / 3
                if 'high' in raw_data and 'low' in raw_data:
                    raw_data['vwap'] = (raw_data['high'] + raw_data['low'] + close_prices) / 3
                else:
                    raw_data['vwap'] = close_prices * (1 + np.random.normal(0, 0.001, (n_days, n_stocks)))
        
        # 生成成交量数据
        if DataField.VOLUME in requirements.fields:
            volumes = pd.DataFrame(
                np.random.lognormal(15, 0.5, (n_days, n_stocks)),
                index=dates,
                columns=stocks
            )
            raw_data['volume'] = volumes
        
        # 生成成交额数据
        if DataField.AMOUNT in requirements.fields:
            if 'volume' in raw_data and 'close' in raw_data:
                raw_data['amount'] = raw_data['volume'] * raw_data['close']
            else:
                raw_data['amount'] = pd.DataFrame(
                    np.random.lognormal(20, 0.5, (n_days, n_stocks)),
                    index=dates,
                    columns=stocks
                )
        
        # 生成换手率数据
        if DataField.TURNOVER in requirements.fields:
            raw_data['turnover'] = pd.DataFrame(
                np.random.uniform(0.01, 0.1, (n_days, n_stocks)),
                index=dates,
                columns=stocks
            )
        
        # 确保所有需要的字段都存在
        for field in requirements.fields:
            field_name = field.value if isinstance(field, DataField) else field
            if field_name not in raw_data:
                # 如果缺少字段，用随机数据填充
                raw_data[field_name] = pd.DataFrame(
                    np.random.randn(n_days, n_stocks),
                    index=dates,
                    columns=stocks
                )
        
        return raw_data


# 便捷函数
def calculate_factor(
    factor_spec: FactorSpec,
    raw_data: Dict[str, pd.DataFrame]
) -> pd.DataFrame:
    """
    便捷函数：计算单个因子
    
    Args:
        factor_spec: 因子规格
        raw_data: 原始数据
    
    Returns:
        因子值 DataFrame
    """
    calculator = FactorCalculator()
    return calculator.calculate(factor_spec, raw_data)


def calculate_factors_from_json(
    json_path: Union[str, Path],
    raw_data: Dict[str, pd.DataFrame]
) -> Dict[str, pd.DataFrame]:
    """
    便捷函数：从 JSON 计算多个因子
    
    Args:
        json_path: JSON 文件路径
        raw_data: 原始数据
    
    Returns:
        因子值字典
    """
    calculator = FactorCalculator()
    return calculator.calculate_from_json(json_path, raw_data)
