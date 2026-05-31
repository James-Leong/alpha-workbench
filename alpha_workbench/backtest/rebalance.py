"""
调仓模块
根据因子数据进行持仓调整和订单生成

功能：
- 基于因子值排序选股
- 生成目标持仓权重
- 计算调仓订单
- 生成Mercury服务可用的订单格式
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple, Union
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class WeightingMethod(Enum):
    """权重分配方法"""
    EQUAL = "equal"           # 等权重
    FACTOR_WEIGHTED = "factor" # 因子加权
    MARKET_CAP = "market_cap"  # 市值加权
    RANK_WEIGHTED = "rank"     # 排名加权


class SelectionMethod(Enum):
    """选股方法"""
    TOP_N = "top_n"           # 选前N只
    TOP_PCT = "top_pct"       # 选前百分之N
    QUANTILE = "quantile"     # 分位数选股
    THRESHOLD = "threshold"   # 阈值选股


@dataclass
class RebalanceConfig:
    """调仓配置"""
    # 选股参数
    selection_method: SelectionMethod = SelectionMethod.TOP_N
    top_n: int = 20                          # 选前N只
    top_pct: float = 0.2                     # 选前20%
    quantile_threshold: float = 0.8          # 选前20%分位数
    factor_threshold: Optional[float] = None # 因子值阈值
    
    # 权重参数
    weighting_method: WeightingMethod = WeightingMethod.EQUAL
    long_short: bool = False                 # 是否多空
    long_quantile: int = 5                   # 多头分位数
    short_quantile: int = 1                  # 空头分位数
    
    # 调仓参数
    rebalance_freq: str = "daily"            # 调仓频率: daily/weekly/monthly
    trade_time: str = "09:30:00"             # 交易时间
    
    # 风控参数
    max_position_pct: float = 0.1            # 单票最大仓位
    min_position_pct: float = 0.0            # 单票最小仓位


@dataclass
class Position:
    """持仓信息"""
    stock_code: str
    weight: float
    shares: int
    market_value: float
    entry_date: str
    entry_price: float


@dataclass
class Order:
    """订单信息"""
    stock_code: str
    side: str                                # buy/sell
    quantity: int
    order_type: str                          # market/limit
    limit_price: Optional[float] = None
    order_date: str = ""
    order_time: str = "09:30:00"


@dataclass
class RebalanceResult:
    """调仓结果"""
    date: str
    target_positions: Dict[str, float]       # 目标持仓权重
    current_positions: Dict[str, float]      # 当前持仓权重
    orders: List[Order]                      # 调仓订单
    turnover: float                          # 换手率
    long_positions: Dict[str, float]         # 多头持仓
    short_positions: Dict[str, float]        # 空头持仓（如适用）


class FactorRebalancer:
    """
    基于因子的调仓器
    
    根据因子数据生成调仓决策和订单
    """
    
    def __init__(self, config: Optional[RebalanceConfig] = None):
        """
        初始化调仓器
        
        Args:
            config: 调仓配置
        """
        self.config = config or RebalanceConfig()
    
    def select_stocks(
        self,
        factor_data: pd.Series,
        selection_method: Optional[SelectionMethod] = None
    ) -> List[str]:
        """
        根据因子值选股
        
        Args:
            factor_data: 单期因子数据 (index=stock_code, values=factor_value)
            selection_method: 选股方法
            
        Returns:
            List[str]: 选中的股票代码列表
        """
        method = selection_method or self.config.selection_method
        factor_data = factor_data.dropna().sort_values(ascending=False)
        
        if method == SelectionMethod.TOP_N:
            # 选前N只
            selected = factor_data.head(self.config.top_n).index.tolist()
            
        elif method == SelectionMethod.TOP_PCT:
            # 选前百分之N
            n = int(len(factor_data) * self.config.top_pct)
            selected = factor_data.head(max(n, 1)).index.tolist()
            
        elif method == SelectionMethod.QUANTILE:
            # 分位数选股
            threshold = factor_data.quantile(self.config.quantile_threshold)
            selected = factor_data[factor_data >= threshold].index.tolist()
            
        elif method == SelectionMethod.THRESHOLD:
            # 阈值选股
            if self.config.factor_threshold is None:
                raise ValueError("使用阈值选股时需要设置 factor_threshold")
            selected = factor_data[factor_data >= self.config.factor_threshold].index.tolist()
            
        else:
            raise ValueError(f"未知的选股方法: {method}")
        
        return selected
    
    def calculate_weights(
        self,
        factor_data: pd.Series,
        selected_stocks: List[str],
        weighting_method: Optional[WeightingMethod] = None
    ) -> Dict[str, float]:
        """
        计算持仓权重
        
        Args:
            factor_data: 单期因子数据
            selected_stocks: 选中的股票列表
            weighting_method: 权重分配方法
            
        Returns:
            Dict[str, float]: 股票权重字典
        """
        method = weighting_method or self.config.weighting_method
        selected_factors = factor_data[selected_stocks].dropna()
        
        if len(selected_factors) == 0:
            return {}
        
        if method == WeightingMethod.EQUAL:
            # 等权重
            weights = {stock: 1.0 / len(selected_stocks) for stock in selected_stocks}
            
        elif method == WeightingMethod.FACTOR_WEIGHTED:
            # 因子加权（因子值越大权重越高）
            factor_values = selected_factors.abs()
            weights = (factor_values / factor_values.sum()).to_dict()
            
        elif method == WeightingMethod.RANK_WEIGHTED:
            # 排名加权（排名越靠前权重越高）
            ranks = selected_factors.rank(ascending=False)
            weights = (ranks / ranks.sum()).to_dict()
            
        else:
            raise ValueError(f"未知的权重方法: {method}")
        
        # 应用仓位限制
        weights = self._apply_position_limits(weights)
        
        # 归一化
        total_weight = sum(weights.values())
        if total_weight > 0:
            weights = {k: v / total_weight for k, v in weights.items()}
        
        return weights
    
    def _apply_position_limits(self, weights: Dict[str, float]) -> Dict[str, float]:
        """应用仓位限制"""
        max_pct = self.config.max_position_pct
        min_pct = self.config.min_position_pct
        
        # 限制最大仓位
        weights = {k: min(v, max_pct) for k, v in weights.items()}
        
        # 过滤最小仓位
        weights = {k: v for k, v in weights.items() if v >= min_pct}
        
        return weights
    
    def generate_orders(
        self,
        target_weights: Dict[str, float],
        current_weights: Dict[str, float],
        prices: pd.Series,
        total_value: float,
        trade_date: str
    ) -> List[Order]:
        """
        生成调仓订单
        
        Args:
            target_weights: 目标权重
            current_weights: 当前权重
            prices: 当前价格
            total_value: 总市值
            trade_date: 交易日期
            
        Returns:
            List[Order]: 订单列表
        """
        orders = []
        all_stocks = set(target_weights.keys()) | set(current_weights.keys())
        
        for stock in all_stocks:
            target_w = target_weights.get(stock, 0)
            current_w = current_weights.get(stock, 0)
            
            # 计算权重变化
            weight_diff = target_w - current_w
            
            if abs(weight_diff) < 0.001:  # 变化太小，忽略
                continue
            
            # 计算股数
            if stock in prices and prices[stock] > 0:
                value_diff = weight_diff * total_value
                shares = int(value_diff / prices[stock])
                
                if shares > 0:
                    orders.append(Order(
                        stock_code=stock,
                        side="buy",
                        quantity=shares,
                        order_type="market",
                        order_date=trade_date,
                        order_time=self.config.trade_time
                    ))
                elif shares < 0:
                    orders.append(Order(
                        stock_code=stock,
                        side="sell",
                        quantity=abs(shares),
                        order_type="market",
                        order_date=trade_date,
                        order_time=self.config.trade_time
                    ))
        
        return orders
    
    def calculate_turnover(
        self,
        target_weights: Dict[str, float],
        current_weights: Dict[str, float]
    ) -> float:
        """
        计算换手率
        
        Args:
            target_weights: 目标权重
            current_weights: 当前权重
            
        Returns:
            float: 换手率
        """
        all_stocks = set(target_weights.keys()) | set(current_weights.keys())
        turnover = 0
        
        for stock in all_stocks:
            target_w = target_weights.get(stock, 0)
            current_w = current_weights.get(stock, 0)
            turnover += abs(target_w - current_w)
        
        return turnover / 2  # 双边换手率 -> 单边换手率
    
    def rebalance(
        self,
        factor_data: pd.Series,
        current_positions: Dict[str, float],
        prices: pd.Series,
        total_value: float,
        trade_date: str
    ) -> RebalanceResult:
        """
        执行调仓
        
        Args:
            factor_data: 单期因子数据
            current_positions: 当前持仓权重
            prices: 当前价格
            total_value: 总市值
            trade_date: 交易日期
            
        Returns:
            RebalanceResult: 调仓结果
        """
        # 1. 选股
        selected_stocks = self.select_stocks(factor_data)
        
        # 2. 计算目标权重
        target_weights = self.calculate_weights(factor_data, selected_stocks)
        
        # 3. 生成订单
        orders = self.generate_orders(
            target_weights, current_positions, prices, total_value, trade_date
        )
        
        # 4. 计算换手率
        turnover = self.calculate_turnover(target_weights, current_positions)
        
        return RebalanceResult(
            date=trade_date,
            target_positions=target_weights,
            current_positions=current_positions,
            orders=orders,
            turnover=turnover,
            long_positions=target_weights,
            short_positions={}
        )
    
    def run_backtest_rebalance(
        self,
        factor_data: pd.DataFrame,
        price_data: pd.DataFrame,
        initial_value: float = 1000000.0,
        rebalance_dates: Optional[List[str]] = None
    ) -> List[RebalanceResult]:
        """
        运行回测调仓序列
        
        Args:
            factor_data: 因子数据 (index=date, columns=stock_code)
            price_data: 价格数据 (index=date, columns=stock_code)
            initial_value: 初始资金
            rebalance_dates: 调仓日期列表 (None表示每日调仓)
            
        Returns:
            List[RebalanceResult]: 调仓结果序列
        """
        results = []
        current_positions = {}
        total_value = initial_value
        
        # 确定调仓日期
        if rebalance_dates is None:
            rebalance_dates = factor_data.index.tolist()
        
        for date in rebalance_dates:
            if date not in factor_data.index:
                continue
            
            # 获取当期数据
            factors = factor_data.loc[date]
            prices = price_data.loc[date] if date in price_data.index else pd.Series()
            
            if len(prices) == 0:
                continue
            
            # 执行调仓
            result = self.rebalance(
                factor_data=factors,
                current_positions=current_positions,
                prices=prices,
                total_value=total_value,
                trade_date=date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else str(date)
            )
            
            results.append(result)
            
            # 更新持仓
            current_positions = result.target_positions
        
        return results


class MercuryOrderConverter:
    """
    Mercury订单格式转换器
    
    将内部订单格式转换为Mercury服务可用的格式
    """
    
    @staticmethod
    def convert_orders(
        orders: List[Order],
        date_format: str = "%Y%m%d"
    ) -> List[Dict]:
        """
        转换订单为Mercury格式
        
        Args:
            orders: 内部订单列表
            date_format: 日期格式
            
        Returns:
            List[Dict]: Mercury格式的订单列表
        """
        mercury_orders = []
        
        for order in orders:
            # 转换日期格式（支持多种格式）
            try:
                # 尝试解析带时间的格式
                date_obj = datetime.strptime(order.order_date, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    # 尝试解析纯日期格式
                    date_obj = datetime.strptime(order.order_date, "%Y-%m-%d")
                except ValueError:
                    # 如果都失败，尝试pandas解析
                    date_obj = pd.to_datetime(order.order_date)
            formatted_date = date_obj.strftime(date_format)
            
            mercury_order = {
                "security_type": "stock",
                "date": formatted_date,
                "sec_uiq_code": order.stock_code,
                "side": order.side,
                "quantity": order.quantity,
                "order_type": order.order_type,
                "currency": "CNY",
                "submit_time": f"{formatted_date} {order.order_time}"
            }
            
            if order.limit_price is not None:
                mercury_order["limit_price"] = order.limit_price
            
            mercury_orders.append(mercury_order)
        
        return mercury_orders
    
    @staticmethod
    def create_mercury_run_spec(
        orders: List[Order],
        start_date: str,
        end_date: str,
        initial_cash: float = 1000000.0,
        transaction_cost_bps: float = 5.0
    ) -> Dict:
        """
        创建Mercury RunSpec
        
        Args:
            orders: 订单列表
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
            initial_cash: 初始资金
            transaction_cost_bps: 交易成本(基点)
            
        Returns:
            Dict: Mercury RunSpec
        """
        mercury_orders = MercuryOrderConverter.convert_orders(orders)
        
        run_spec = {
            "run": {
                "start_date": start_date,
                "end_date": end_date,
                "initial_cash": initial_cash,
                "transaction_cost_bps": transaction_cost_bps
            },
            "inputs": [
                {
                    "kind": "order",
                    "name": "factor_rebalance_strategy",
                    "version": 1,
                    "time_in_force": "day",
                    "orders": mercury_orders
                }
            ]
        }
        
        return run_spec


# 便捷函数
def create_rebalance_strategy(
    top_n: int = 20,
    weighting: WeightingMethod = WeightingMethod.EQUAL,
    long_short: bool = False
) -> FactorRebalancer:
    """
    创建调仓策略
    
    Args:
        top_n: 选股数量
        weighting: 权重方法
        long_short: 是否多空
        
    Returns:
        FactorRebalancer: 调仓器
    """
    config = RebalanceConfig(
        selection_method=SelectionMethod.TOP_N,
        top_n=top_n,
        weighting_method=weighting,
        long_short=long_short
    )
    return FactorRebalancer(config)


def generate_rebalance_orders(
    factor_data: pd.DataFrame,
    price_data: pd.DataFrame,
    top_n: int = 20,
    initial_value: float = 1000000.0
) -> List[RebalanceResult]:
    """
    生成调仓订单序列
    
    Args:
        factor_data: 因子数据
        price_data: 价格数据
        top_n: 选股数量
        initial_value: 初始资金
        
    Returns:
        List[RebalanceResult]: 调仓结果序列
    """
    rebalancer = create_rebalance_strategy(top_n=top_n)
    return rebalancer.run_backtest_rebalance(
        factor_data=factor_data,
        price_data=price_data,
        initial_value=initial_value
    )
