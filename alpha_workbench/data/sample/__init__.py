"""
样例数据模块
提供回测所需的最小样例数据集

包含字段：
- 日期 (date)
- 股票代码 (stock_code)
- 收益率 (returns)
- 行业 (industry)
- 市值 (market_cap)
- 财务字段 (financial fields)
"""
import pandas as pd
import numpy as np
from typing import Tuple, Optional
from pathlib import Path

# 数据文件路径
DATA_DIR = Path(__file__).parent


def load_sample_data(
    data_type: str = "momentum",
    n_stocks: int = 50,
    n_days: int = 252
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    加载样例数据
    
    Args:
        data_type: 数据类型 ('momentum', 'reversal', 'volatility')
        n_stocks: 股票数量
        n_days: 交易日数量
        
    Returns:
        Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
            (factor_data, price_data, returns_data, meta_data)
            
            factor_data: 因子值 (index=date, columns=stock_code)
            price_data: 价格数据 (index=date, columns=stock_code)
            returns_data: 收益率 (index=date, columns=stock_code)
            meta_data: 元数据 (index=date, columns=[industry, market_cap, ...])
    """
    from alpha_workbench.data.sample_data import generate_sample_data
    
    factor_data, price_data, returns_data = generate_sample_data(
        n_stocks=n_stocks,
        n_days=n_days
    )
    
    # 生成元数据
    dates = factor_data.index
    stocks = factor_data.columns
    
    # 行业数据
    industries = ['科技', '金融', '消费', '医药', '能源']
    industry_data = pd.DataFrame(
        np.random.choice(industries, size=(len(dates), len(stocks))),
        index=dates,
        columns=stocks
    )
    
    # 市值数据（随机生成）
    market_cap_data = pd.DataFrame(
        np.random.lognormal(mean=15, sigma=1, size=(len(dates), len(stocks))),
        index=dates,
        columns=stocks
    )
    
    # 合并元数据
    meta_data = pd.concat([
        industry_data.stack().rename('industry'),
        market_cap_data.stack().rename('market_cap')
    ], axis=1).unstack()
    
    return factor_data, price_data, returns_data, meta_data


def get_sample_factor_data(factor_type: str = "momentum") -> pd.DataFrame:
    """
    获取样例因子数据
    
    Args:
        factor_type: 因子类型 ('momentum', 'reversal', 'volatility')
        
    Returns:
        pd.DataFrame: 因子数据
    """
    from alpha_workbench.data.sample_data import (
        generate_momentum_factor,
        generate_reversal_factor,
        generate_volatility_factor,
        generate_sample_data
    )
    
    factor_data, price_data, _ = generate_sample_data()
    
    if factor_type == "momentum":
        return generate_momentum_factor(price_data)
    elif factor_type == "reversal":
        return generate_reversal_factor(price_data)
    elif factor_type == "volatility":
        return generate_volatility_factor(price_data)
    else:
        return factor_data


# 便捷函数
get_factor_data = get_sample_factor_data
load_data = load_sample_data
