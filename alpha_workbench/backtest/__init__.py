"""Backtest module — factor backtesting, metrics, Mercury integration, and visualization."""

from alpha_workbench.backtest.engine import run_backtest
from alpha_workbench.backtest.factor_backtest import FactorBacktest, mock_run_backtest, run_factor_backtest
from alpha_workbench.backtest.hybrid_engine import HybridBacktestEngine
from alpha_workbench.backtest.mercury_adapter import (
    MercuryAdapter,
    MercuryConfig,
    MercuryRunSpec,
    create_mercury_adapter,
)
from alpha_workbench.backtest.rebalance import (
    FactorRebalancer,
    MercuryOrderConverter,
    RebalanceConfig,
    SelectionMethod,
    WeightingMethod,
    create_rebalance_strategy,
)
