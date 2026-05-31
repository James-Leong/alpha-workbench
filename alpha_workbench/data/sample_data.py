"""
Sample Data Loader for AlphaWorkbench Role 5
样例数据加载工具
"""
import numpy as np
import pandas as pd
from typing import Tuple, Optional, List
from datetime import datetime, timedelta


DEFAULT_SAMPLE_SECURITIES = [
    "000001.XSHE", "000002.XSHE", "000063.XSHE", "000100.XSHE", "000157.XSHE",
    "000166.XSHE", "000333.XSHE", "000338.XSHE", "000425.XSHE", "000538.XSHE",
    "000568.XSHE", "000596.XSHE", "000625.XSHE", "000651.XSHE", "000725.XSHE",
    "000776.XSHE", "000858.XSHE", "000876.XSHE", "000895.XSHE", "000938.XSHE",
    "000963.XSHE", "001979.XSHE", "002001.XSHE", "002007.XSHE", "002027.XSHE",
    "002049.XSHE", "002142.XSHE", "002179.XSHE", "002230.XSHE", "002241.XSHE",
    "002304.XSHE", "002311.XSHE", "002352.XSHE", "002371.XSHE", "002410.XSHE",
    "002415.XSHE", "002466.XSHE", "002475.XSHE", "002594.XSHE", "002714.XSHE",
    "600000.XSHG", "600009.XSHG", "600010.XSHG", "600011.XSHG", "600015.XSHG",
    "600016.XSHG", "600018.XSHG", "600019.XSHG", "600025.XSHG", "600028.XSHG",
    "600029.XSHG", "600030.XSHG", "600031.XSHG", "600036.XSHG", "600048.XSHG",
    "600050.XSHG", "600061.XSHG", "600104.XSHG", "600111.XSHG", "600150.XSHG",
    "600176.XSHG", "600276.XSHG", "600309.XSHG", "600340.XSHG", "600346.XSHG",
    "600406.XSHG", "600436.XSHG", "600438.XSHG", "600519.XSHG", "600585.XSHG",
    "600600.XSHG", "600660.XSHG", "600690.XSHG", "600703.XSHG", "600745.XSHG",
    "600760.XSHG", "600795.XSHG", "600809.XSHG", "600837.XSHG", "600887.XSHG",
]


def generate_sample_security_codes(n_stocks: int) -> List[str]:
    """
    Generate Mercury-compatible sample security identifiers.

    Mercury order inputs expect sec_uiq_code as ticker.exchange, for example
    000001.XSHE or 600000.XSHG. The local sample data uses the same identifiers
    so local backtests and Mercury runs refer to the same assets.
    """
    if n_stocks <= len(DEFAULT_SAMPLE_SECURITIES):
        return DEFAULT_SAMPLE_SECURITIES[:n_stocks]

    codes = DEFAULT_SAMPLE_SECURITIES.copy()
    next_sz = 300001
    next_sh = 601000

    while len(codes) < n_stocks:
        if len(codes) % 2 == 0:
            codes.append(f"{next_sz:06d}.XSHE")
            next_sz += 1
        else:
            codes.append(f"{next_sh:06d}.XSHG")
            next_sh += 1

    return codes


def generate_sample_data(
    n_stocks: int = 50,
    n_days: int = 252,
    start_date: Optional[str] = None,
    seed: int = 42
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    生成样例回测数据
    
    Args:
        n_stocks: 股票数量
        n_days: 交易日数量
        start_date: 开始日期，默认一年前
        seed: 随机种子
        
    Returns:
        (factor_data, price_data, returns_data)
    """
    np.random.seed(seed)
    
    # 生成日期索引
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=n_days)).strftime('%Y-%m-%d')
    
    dates = pd.date_range(start=start_date, periods=n_days, freq='B')  # 工作日
    stocks = generate_sample_security_codes(n_stocks)
    
    # 生成价格数据（随机游走）
    price_data = pd.DataFrame(index=dates, columns=stocks)
    for stock in stocks:
        returns = np.random.normal(0.0005, 0.02, n_days)  # 日收益
        prices = 100 * np.exp(np.cumsum(returns))
        price_data[stock] = prices
    
    # 生成因子数据（与收益有一定相关性）
    factor_data = pd.DataFrame(index=dates, columns=stocks)
    for i, date in enumerate(dates[:-1]):  # 最后一天没有下一期收益
        next_returns = price_data.iloc[i+1] / price_data.iloc[i] - 1
        # 因子值 = 未来收益的噪声版本
        noise = np.random.normal(0, 0.01, n_stocks)
        factor_values = next_returns.values + noise
        factor_data.loc[date] = factor_values
    
    # 最后一天填充NaN
    factor_data.iloc[-1] = np.nan
    factor_data = factor_data.iloc[:-1]
    
    # 计算收益率
    returns_data = price_data.pct_change().shift(-1).iloc[:-1]
    price_data = price_data.iloc[:-1]
    
    # 添加一些缺失值模拟真实数据
    mask = np.random.random(factor_data.shape) < 0.05  # 5%缺失率
    factor_data = factor_data.mask(mask)
    
    return factor_data, price_data, returns_data


def generate_momentum_factor(
    price_data: pd.DataFrame,
    lookback: int = 20
) -> pd.DataFrame:
    """
    生成动量因子
    
    Args:
        price_data: 价格数据
        lookback: 回看周期
        
    Returns:
        动量因子DataFrame
    """
    # 过去N日收益率作为动量因子
    momentum = price_data.pct_change(lookback)
    return momentum


def generate_reversal_factor(
    price_data: pd.DataFrame,
    lookback: int = 5
) -> pd.DataFrame:
    """
    生成反转因子
    
    Args:
        price_data: 价格数据
        lookback: 回看周期
        
    Returns:
        反转因子DataFrame
    """
    # 过去N日收益的负值作为反转因子
    reversal = -price_data.pct_change(lookback)
    return reversal


def generate_volatility_factor(
    price_data: pd.DataFrame,
    lookback: int = 20
) -> pd.DataFrame:
    """
    生成波动率因子
    
    Args:
        price_data: 价格数据
        lookback: 回看周期
        
    Returns:
        波动率因子DataFrame
    """
    # 计算日收益的波动率
    returns = price_data.pct_change()
    volatility = returns.rolling(lookback).std()
    return volatility


def load_sample_backtest_data(
    factor_type: str = "momentum",
    n_stocks: int = 50,
    n_days: int = 252
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    加载样例回测数据（便捷函数）
    
    Args:
        factor_type: 因子类型 ('momentum', 'reversal', 'volatility')
        n_stocks: 股票数量
        n_days: 交易日数量
        
    Returns:
        (factor_data, price_data, returns_data)
    """
    # 根据因子类型确定最小所需天数
    min_days_map = {
        "momentum": 25,      # 20日动量 + 缓冲
        "reversal": 10,      # 5日反转 + 缓冲
        "volatility": 25     # 20日波动率 + 缓冲
    }
    min_days = min_days_map.get(factor_type, 25)
    
    # 确保天数足够
    if n_days < min_days:
        print(f"  ⚠️  n_days={n_days} 太小，自动调整为 {min_days} 以满足因子计算需求")
        n_days = min_days
    
    # 生成基础数据（额外生成一些天数用于计算因子）
    buffer_days = 30  # 额外缓冲天数
    factor_data, price_data, returns_data = generate_sample_data(
        n_stocks=n_stocks,
        n_days=n_days + buffer_days
    )
    
    # 根据类型生成因子
    if factor_type == "momentum":
        factor_data = generate_momentum_factor(price_data)
    elif factor_type == "reversal":
        factor_data = generate_reversal_factor(price_data)
    elif factor_type == "volatility":
        factor_data = generate_volatility_factor(price_data)
    
    # 去除NaN
    factor_data = factor_data.dropna()
    
    # 限制回测天数
    if len(factor_data) > n_days:
        factor_data = factor_data.iloc[-n_days:]
    
    common_dates = factor_data.index
    price_data = price_data.loc[common_dates]
    returns_data = returns_data.loc[common_dates]
    
    return factor_data, price_data, returns_data


def create_mock_factorspec(factor_type: str = "momentum") -> dict:
    """
    创建Mock FactorSpec字典
    
    Args:
        factor_type: 因子类型
        
    Returns:
        FactorSpec字典
    """
    factor_configs = {
        "momentum": {
            "factor_id": "MOM_20D",
            "factor_name": "20日动量因子",
            "formula_latex": r"r_{t-20:t} = \frac{P_t - P_{t-20}}{P_{t-20}}",
            "description": "过去20个交易日的收益率，反映股票的短期趋势"
        },
        "reversal": {
            "factor_id": "REV_5D",
            "factor_name": "5日反转因子",
            "formula_latex": r"REV = -r_{t-5:t}",
            "description": "过去5个交易日收益的负值，捕捉短期反转效应"
        },
        "volatility": {
            "factor_id": "VOL_20D",
            "factor_name": "20日波动率因子",
            "formula_latex": r"\sigma_{20} = \sqrt{\frac{1}{20}\sum_{i=1}^{20}(r_i - \bar{r})^2}",
            "description": "过去20个交易日的收益率标准差"
        }
    }
    
    config = factor_configs.get(factor_type, factor_configs["momentum"])
    
    return {
        "factor_id": config["factor_id"],
        "factor_name": config["factor_name"],
        "formula_latex": config["formula_latex"],
        "expression_tree": None,
        "description": config["description"]
    }


# 便捷函数
get_sample_data = generate_sample_data
get_momentum_factor = generate_momentum_factor
get_reversal_factor = generate_reversal_factor
get_volatility_factor = generate_volatility_factor
