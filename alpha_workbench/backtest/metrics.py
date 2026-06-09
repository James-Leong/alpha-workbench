"""
回测指标计算模块
提供因子回测相关的各种指标计算函数

包含指标：
- IC / RankIC（Pearson / Spearman相关系数）
- 分层收益（Quantile Returns）
- 多空组合收益（Long-Short Portfolio）
- 换手率（Turnover）
- 风险指标（Sharpe, Max Drawdown等）
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class ICCalculationResult:
    """IC计算结果"""
    ic_series: pd.Series          # Pearson IC序列
    rank_ic_series: pd.Series     # Rank IC (Spearman)序列
    ic_mean: float                # IC均值
    ic_std: float                 # IC标准差
    icir: float                   # IC信息比率
    ic_positive_ratio: float      # IC为正的比例
    ic_tstat: float               # IC t统计量
    rank_ic_mean: float           # RankIC均值
    rank_ic_std: float            # RankIC标准差
    rank_icir: float              # RankIC信息比率
    rank_ic_positive_ratio: float # RankIC为正的比例
    rank_ic_tstat: float          # RankIC t统计量


@dataclass
class LayerCalculationResult:
    """分层收益计算结果"""
    layer_returns: Dict[str, float]       # 各层年化收益
    layer_cum_returns: pd.DataFrame       # 各层累计收益
    layer_daily_returns: pd.DataFrame     # 各层日收益
    monotonicity_score: float             # 单调性评分


@dataclass
class TurnoverCalculationResult:
    """换手率计算结果"""
    turnover_series: pd.Series    # 换手率序列
    mean_turnover: float          # 平均换手率
    max_turnover: float           # 最大换手率
    min_turnover: float           # 最小换手率


@dataclass
class LongShortCalculationResult:
    """多空组合计算结果"""
    daily_returns: pd.Series      # 日收益序列
    cum_returns: pd.Series        # 累计收益序列
    annual_return: float          # 年化收益
    annual_volatility: float      # 年化波动率
    sharpe_ratio: float           # 夏普比率
    max_drawdown: float           # 最大回撤
    turnover: Optional[TurnoverCalculationResult] = None  # 换手率


def calculate_ic_metrics(
    factor_data: pd.DataFrame,
    returns_data: pd.DataFrame,
    min_samples: int = 10
) -> ICCalculationResult:
    """
    计算IC指标（Pearson IC和Rank IC）
    
    Args:
        factor_data: 因子值DataFrame，index=date, columns=stock
        returns_data: 收益数据DataFrame，index=date, columns=stock
        min_samples: 最小样本数
        
    Returns:
        ICCalculationResult: IC计算结果
    """
    ic_series_pearson = []
    ic_series_spearman = []
    
    for date in factor_data.index:
        f = factor_data.loc[date].dropna()
        r = returns_data.loc[date].dropna()
        
        common_stocks = f.index.intersection(r.index)
        if len(common_stocks) < min_samples:
            continue
        
        f = f[common_stocks]
        r = r[common_stocks]
        
        # Pearson IC
        ic_pearson = f.corr(r, method='pearson')
        if not np.isnan(ic_pearson):
            ic_series_pearson.append(ic_pearson)
        
        # Rank IC (Spearman)
        ic_spearman = f.corr(r, method='spearman')
        if not np.isnan(ic_spearman):
            ic_series_spearman.append(ic_spearman)
    
    ic_series_pearson = pd.Series(ic_series_pearson)
    ic_series_spearman = pd.Series(ic_series_spearman)
    
    # Pearson IC统计量
    ic_mean = ic_series_pearson.mean()
    ic_std = ic_series_pearson.std()
    icir = ic_mean / ic_std if ic_std > 0 else 0
    ic_positive_ratio = (ic_series_pearson > 0).mean()
    ic_tstat = ic_mean / (ic_std / np.sqrt(len(ic_series_pearson))) if ic_std > 0 else 0
    
    # Rank IC统计量
    rank_ic_mean = ic_series_spearman.mean()
    rank_ic_std = ic_series_spearman.std()
    rank_icir = rank_ic_mean / rank_ic_std if rank_ic_std > 0 else 0
    rank_ic_positive_ratio = (ic_series_spearman > 0).mean()
    rank_ic_tstat = rank_ic_mean / (rank_ic_std / np.sqrt(len(ic_series_spearman))) if rank_ic_std > 0 else 0
    
    return ICCalculationResult(
        ic_series=ic_series_pearson,
        rank_ic_series=ic_series_spearman,
        ic_mean=ic_mean,
        ic_std=ic_std,
        icir=icir,
        ic_positive_ratio=ic_positive_ratio,
        ic_tstat=ic_tstat,
        rank_ic_mean=rank_ic_mean,
        rank_ic_std=rank_ic_std,
        rank_icir=rank_icir,
        rank_ic_positive_ratio=rank_ic_positive_ratio,
        rank_ic_tstat=rank_ic_tstat
    )


def calculate_layer_returns(
    factor_data: pd.DataFrame,
    returns_data: pd.DataFrame,
    n_quantiles: int = 5,
    min_samples: int = 10
) -> LayerCalculationResult:
    """
    计算分层收益
    
    Args:
        factor_data: 因子值DataFrame
        returns_data: 收益数据DataFrame
        n_quantiles: 分层数量
        min_samples: 最小样本数
        
    Returns:
        LayerCalculationResult: 分层收益结果
    """
    layer_returns = {}
    layer_daily_returns = []
    
    for date in factor_data.index[:-1]:
        f = factor_data.loc[date].dropna()
        r = returns_data.loc[date].dropna()
        
        common_stocks = f.index.intersection(r.index)
        if len(common_stocks) < min_samples:
            continue
        
        f = f[common_stocks]
        r = r[common_stocks]
        
        try:
            labels = [f'L{i+1}' for i in range(n_quantiles)]
            f_quantiles = pd.qcut(f, n_quantiles, labels=labels, duplicates='drop')
            
            daily_ret = {}
            for layer in labels:
                if layer in f_quantiles.values:
                    layer_stocks = f_quantiles[f_quantiles == layer].index
                    layer_ret = r[layer_stocks].mean()
                    
                    if date not in layer_returns:
                        layer_returns[date] = {}
                    layer_returns[date][layer] = layer_ret
                    daily_ret[layer] = layer_ret
            
            if daily_ret:
                daily_ret['date'] = date
                layer_daily_returns.append(daily_ret)
        except:
            continue
    
    layer_returns_df = pd.DataFrame(layer_returns).T
    layer_daily_df = pd.DataFrame(layer_daily_returns).set_index('date') if layer_daily_returns else pd.DataFrame()
    
    # 计算年化收益
    layer_annual_returns = {}
    for layer in layer_returns_df.columns:
        daily_mean = layer_returns_df[layer].mean()
        layer_annual_returns[layer] = daily_mean * 252
    
    # 计算累计收益
    layer_cum_returns = (1 + layer_returns_df.fillna(0)).cumprod()
    
    # 计算单调性评分（最高层 - 最低层）
    if len(layer_annual_returns) >= 2:
        sorted_returns = sorted(layer_annual_returns.items(), key=lambda x: x[1], reverse=True)
        monotonicity_score = sorted_returns[0][1] - sorted_returns[-1][1]
    else:
        monotonicity_score = 0
    
    return LayerCalculationResult(
        layer_returns=layer_annual_returns,
        layer_cum_returns=layer_cum_returns,
        layer_daily_returns=layer_daily_df,
        monotonicity_score=monotonicity_score
    )


def calculate_turnover(
    portfolio_stocks: List[Dict],
    method: str = 'symmetric_difference'
) -> Optional[TurnoverCalculationResult]:
    """
    计算换手率
    
    Args:
        portfolio_stocks: 持仓股票列表，每项包含 'date' 和 'stocks' (set)
        method: 计算方法，'symmetric_difference' 或 'jaccard'
        
    Returns:
        TurnoverCalculationResult: 换手率结果
    """
    if len(portfolio_stocks) < 2:
        return None
    
    turnovers = []
    
    for i in range(1, len(portfolio_stocks)):
        prev_stocks = portfolio_stocks[i-1]['stocks']
        curr_stocks = portfolio_stocks[i]['stocks']
        
        if method == 'symmetric_difference':
            # 对称差集 / 并集
            union_stocks = prev_stocks.union(curr_stocks)
            if len(union_stocks) == 0:
                continue
            diff_stocks = prev_stocks.symmetric_difference(curr_stocks)
            turnover = len(diff_stocks) / len(union_stocks)
        elif method == 'jaccard':
            # Jaccard距离
            intersection = len(prev_stocks.intersection(curr_stocks))
            union = len(prev_stocks.union(curr_stocks))
            turnover = 1 - intersection / union if union > 0 else 0
        else:
            raise ValueError(f"Unknown method: {method}")
        
        turnovers.append(turnover)
    
    if not turnovers:
        return None
    
    turnover_series = pd.Series(turnovers)
    
    return TurnoverCalculationResult(
        turnover_series=turnover_series,
        mean_turnover=turnover_series.mean(),
        max_turnover=turnover_series.max(),
        min_turnover=turnover_series.min()
    )


def calculate_long_short_metrics(
    factor_data: pd.DataFrame,
    returns_data: pd.DataFrame,
    n_quantiles: int = 5,
    min_samples: int = 10,
    calculate_turnover_flag: bool = True
) -> LongShortCalculationResult:
    """
    计算多空组合指标
    
    Args:
        factor_data: 因子值DataFrame
        returns_data: 收益数据DataFrame
        n_quantiles: 分层数量
        min_samples: 最小样本数
        calculate_turnover_flag: 是否计算换手率
        
    Returns:
        LongShortCalculationResult: 多空组合结果
    """
    long_short_returns = []
    top_portfolio_stocks = []
    
    for date in factor_data.index[:-1]:
        f = factor_data.loc[date].dropna()
        r = returns_data.loc[date].dropna()
        
        common_stocks = f.index.intersection(r.index)
        if len(common_stocks) < min_samples:
            continue
        
        f = f[common_stocks]
        r = r[common_stocks]
        
        try:
            labels = [f'L{i+1}' for i in range(n_quantiles)]
            f_quantiles = pd.qcut(f, n_quantiles, labels=labels, duplicates='drop')
            
            top_layer = labels[-1]
            bottom_layer = labels[0]
            
            if top_layer in f_quantiles.values and bottom_layer in f_quantiles.values:
                top_stocks = f_quantiles[f_quantiles == top_layer].index.tolist()
                bottom_stocks = f_quantiles[f_quantiles == bottom_layer].index.tolist()
                
                # 记录持仓
                if calculate_turnover_flag:
                    top_portfolio_stocks.append({
                        'date': date,
                        'stocks': set(top_stocks)
                    })
                
                long_ret = r[top_stocks].mean()
                short_ret = r[bottom_stocks].mean()
                
                ls_ret = long_ret - short_ret
                long_short_returns.append(ls_ret)
        except:
            continue
    
    long_short_returns = pd.Series(
        long_short_returns,
        index=factor_data.index[:-1][:len(long_short_returns)]
    )
    
    if len(long_short_returns) == 0:
        raise ValueError("没有有效的多空收益数据")
    
    # 计算指标
    daily_mean = long_short_returns.mean()
    daily_std = long_short_returns.std()
    
    annual_return = daily_mean * 252
    annual_volatility = daily_std * np.sqrt(252)
    sharpe_ratio = annual_return / annual_volatility if annual_volatility > 0 else 0
    
    # 计算最大回撤
    cum_returns = (1 + long_short_returns.fillna(0)).cumprod()
    running_max = cum_returns.expanding().max()
    drawdown = (cum_returns - running_max) / running_max
    max_drawdown = drawdown.min()
    
    # 计算换手率
    turnover = None
    if calculate_turnover_flag and top_portfolio_stocks:
        turnover = calculate_turnover(top_portfolio_stocks)
    
    return LongShortCalculationResult(
        daily_returns=long_short_returns,
        cum_returns=cum_returns,
        annual_return=annual_return,
        annual_volatility=annual_volatility,
        sharpe_ratio=sharpe_ratio,
        max_drawdown=max_drawdown,
        turnover=turnover
    )


def calculate_max_drawdown(cum_returns: pd.Series) -> float:
    """
    计算最大回撤
    
    Args:
        cum_returns: 累计收益序列
        
    Returns:
        float: 最大回撤（负值）
    """
    running_max = cum_returns.expanding().max()
    drawdown = (cum_returns - running_max) / running_max
    return drawdown.min()


def calculate_sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    annualization_factor: float = 252
) -> float:
    """
    计算夏普比率
    
    Args:
        returns: 收益序列
        risk_free_rate: 无风险利率
        annualization_factor: 年化因子
        
    Returns:
        float: 夏普比率
    """
    excess_returns = returns - risk_free_rate / annualization_factor
    if excess_returns.std() == 0:
        return 0
    sharpe = excess_returns.mean() / excess_returns.std() * np.sqrt(annualization_factor)
    return sharpe


# 便捷函数
compute_ic = calculate_ic_metrics
compute_layer_returns = calculate_layer_returns
compute_turnover = calculate_turnover
compute_long_short = calculate_long_short_metrics
