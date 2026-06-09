"""
因子回测主模块
整合所有回测功能，提供统一的回测接口

功能：
- 因子数据预处理
- IC/RankIC计算
- 分层收益计算
- 多空组合回测
- 换手率分析
- 结果输出
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Union, List

import pandas as pd
import numpy as np

from alpha_workbench.schemas.backtest_schemas import (
    BacktestInput,
    BacktestReport,
    BacktestMetrics,
    BacktestFigures,
    ICMetrics,
    LayerMetrics,
    LongShortMetrics,
    TurnoverMetrics,
    TopPortfolioMetrics,
    ResearchSpec,
)
from alpha_workbench.backtest.metrics import (
    calculate_ic_metrics,
    calculate_layer_returns,
    calculate_long_short_metrics,
    ICCalculationResult,
    LayerCalculationResult,
    LongShortCalculationResult
)
from alpha_workbench.backtest.plotter import BacktestPlotter
from alpha_workbench.backtest.llm_explainer import BacktestExplainer


class FactorBacktest:
    """
    因子回测类
    
    提供完整的因子回测流程：
    1. 数据验证和预处理
    2. IC/RankIC计算
    3. 分层收益分析
    4. 多空组合回测
    5. 换手率计算
    6. 图表生成
    7. LLM解释生成
    """
    
    def __init__(
        self,
        n_quantiles: int = 5,
        min_samples: int = 10,
        enable_plotting: bool = True,
        enable_llm: bool = True,
        llm_model: Optional[str] = None
    ):
        """
        初始化回测器
        
        Args:
            n_quantiles: 分层数量
            min_samples: 最小样本数
            enable_plotting: 是否生成图表
            enable_llm: 是否启用LLM解释
            llm_model: LLM模型名称
        """
        self.n_quantiles = n_quantiles
        self.min_samples = min_samples
        self.enable_plotting = enable_plotting
        self.enable_llm = enable_llm
        
        self.plotter = BacktestPlotter() if enable_plotting else None
        self.explainer = BacktestExplainer(model=llm_model) if enable_llm else None
    
    def run(self, input_data: BacktestInput) -> BacktestReport:
        """
        执行回测
        
        Args:
            input_data: 回测输入数据
            
        Returns:
            BacktestReport: 回测报告
        """
        # 1. 数据预处理
        factor_data, returns_data = self._prepare_data(input_data)
        
        # 2. 计算IC指标
        ic_result = calculate_ic_metrics(factor_data, returns_data, self.min_samples)
        ic_metrics = ICMetrics(
            ic_mean=ic_result.ic_mean,
            ic_std=ic_result.ic_std,
            icir=ic_result.icir,
            ic_positive_ratio=ic_result.ic_positive_ratio,
            ic_tstat=ic_result.ic_tstat,
            rank_ic_mean=ic_result.rank_ic_mean,
            rank_ic_std=ic_result.rank_ic_std,
            rank_icir=ic_result.rank_icir,
            rank_ic_positive_ratio=ic_result.rank_ic_positive_ratio,
            rank_ic_tstat=ic_result.rank_ic_tstat
        )
        
        # 3. 计算分层收益
        layer_result = calculate_layer_returns(
            factor_data, returns_data, self.n_quantiles, self.min_samples
        )
        layer_metrics = LayerMetrics(
            layer_returns=layer_result.layer_returns,
            layer_cum_returns=layer_result.layer_cum_returns
        )
        
        # 4. 计算多空组合
        ls_result = calculate_long_short_metrics(
            factor_data, returns_data, self.n_quantiles, self.min_samples, True
        )
        
        # 构建换手率指标
        turnover_metrics = None
        if ls_result.turnover:
            turnover_metrics = TurnoverMetrics(
                mean_turnover=ls_result.turnover.mean_turnover,
                max_turnover=ls_result.turnover.max_turnover,
                min_turnover=ls_result.turnover.min_turnover,
                turnover_series=ls_result.turnover.turnover_series
            )
        
        long_short_metrics = LongShortMetrics(
            annual_return=ls_result.annual_return,
            annual_volatility=ls_result.annual_volatility,
            sharpe_ratio=ls_result.sharpe_ratio,
            max_drawdown=ls_result.max_drawdown,
            cum_returns=ls_result.cum_returns,
            turnover=turnover_metrics,
            top_portfolio=TopPortfolioMetrics(
                annual_return=ls_result.annual_return,
                annual_volatility=ls_result.annual_volatility,
                sharpe_ratio=ls_result.sharpe_ratio,
                max_drawdown=ls_result.max_drawdown,
                cum_returns=ls_result.cum_returns
            )
        )
        
        # 5. 组装指标
        metrics = BacktestMetrics(
            ic_metrics=ic_metrics,
            layer_metrics=layer_metrics,
            long_short_metrics=long_short_metrics,
            turnover_analysis=None
        )
        
        # 6. 生成图表
        figures = BacktestFigures()
        if self.enable_plotting and self.plotter:
            figures = self._generate_figures(
                ic_result, layer_result, ls_result, factor_data
            )
        
        # 7. 生成LLM解释
        explanation = None
        if self.enable_llm and self.explainer:
            backtest_period = self._format_backtest_period(factor_data)
            explanation = self.explainer.explain(metrics, input_data.factor_spec, backtest_period)
        
        # 8. 组装报告
        report = BacktestReport(
            factor_id=input_data.factor_spec.factor_id,
            factor_name=input_data.factor_spec.factor_name,
            backtest_period=self._format_backtest_period(factor_data),
            metrics=metrics,
            figures=figures,
            explanation=explanation
        )
        
        return report
    
    def _prepare_data(self, input_data: BacktestInput) -> tuple:
        """数据预处理"""
        factor_data = input_data.factor_data.copy()
        
        if input_data.returns_data is not None:
            returns_data = input_data.returns_data.copy()
        else:
            returns_data = input_data.price_data.pct_change().shift(-1)
        
        # 对齐数据
        common_dates = factor_data.index.intersection(returns_data.index)
        common_stocks = factor_data.columns.intersection(returns_data.columns)
        
        factor_data = factor_data.loc[common_dates, common_stocks]
        returns_data = returns_data.loc[common_dates, common_stocks]
        
        # 过滤日期范围
        if input_data.start_date:
            factor_data = factor_data[factor_data.index >= pd.Timestamp(input_data.start_date)]
            returns_data = returns_data[returns_data.index >= pd.Timestamp(input_data.start_date)]
        
        if input_data.end_date:
            factor_data = factor_data[factor_data.index <= pd.Timestamp(input_data.end_date)]
            returns_data = returns_data[returns_data.index <= pd.Timestamp(input_data.end_date)]
        
        return factor_data, returns_data
    
    def _generate_figures(
        self,
        ic_result: ICCalculationResult,
        layer_result: LayerCalculationResult,
        ls_result: LongShortCalculationResult,
        factor_data: pd.DataFrame
    ) -> BacktestFigures:
        """生成图表"""
        figures = BacktestFigures()
        
        if self.plotter:
            # IC序列图
            figures.ic_series_plot = self.plotter.plot_ic_series(ic_result.rank_ic_series)
            
            # 分层收益图
            figures.layer_cumreturn_plot = self.plotter.plot_layer_cumreturns(
                layer_result.layer_cum_returns
            )
            
            # 多空净值图
            figures.long_short_nav_plot = self.plotter.plot_long_short_nav(
                ls_result.cum_returns
            )
            
            # IC分布图
            figures.ic_distribution_plot = self.plotter.plot_ic_distribution(
                ic_result.rank_ic_series
            )
        
        return figures
    
    def _format_backtest_period(self, factor_data: pd.DataFrame) -> str:
        """格式化回测区间"""
        if len(factor_data) == 0:
            return "N/A"
        start = factor_data.index[0].strftime('%Y-%m-%d')
        end = factor_data.index[-1].strftime('%Y-%m-%d')
        return f"{start} ~ {end}"
    
    def export_report(
        self,
        report: BacktestReport,
        output_dir: Union[str, Path],
        prefix: str = ""
    ) -> Dict[str, Path]:
        """
        导出报告到文件
        
        Args:
            report: 回测报告
            output_dir: 输出目录
            prefix: 文件名前缀
            
        Returns:
            Dict[str, Path]: 导出的文件路径
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_prefix = f"{prefix}_{report.factor_id}_{timestamp}" if prefix else f"{report.factor_id}_{timestamp}"
        
        exported_files = {}
        
        # 1. 导出指标JSON
        metrics_dict = {
            'factor_id': report.factor_id,
            'factor_name': report.factor_name,
            'backtest_period': report.backtest_period,
            'metrics': {
                'ic': {
                    'ic_mean': report.metrics.ic_metrics.ic_mean,
                    'ic_std': report.metrics.ic_metrics.ic_std,
                    'icir': report.metrics.ic_metrics.icir,
                    'ic_positive_ratio': report.metrics.ic_metrics.ic_positive_ratio,
                    'ic_tstat': report.metrics.ic_metrics.ic_tstat,
                    'rank_ic_mean': report.metrics.ic_metrics.rank_ic_mean,
                    'rank_ic_std': report.metrics.ic_metrics.rank_ic_std,
                    'rank_icir': report.metrics.ic_metrics.rank_icir,
                    'rank_ic_positive_ratio': report.metrics.ic_metrics.rank_ic_positive_ratio,
                    'rank_ic_tstat': report.metrics.ic_metrics.rank_ic_tstat
                },
                'layer': {
                    'layer_returns': report.metrics.layer_metrics.layer_returns
                },
                'long_short': {
                    'annual_return': report.metrics.long_short_metrics.annual_return,
                    'annual_volatility': report.metrics.long_short_metrics.annual_volatility,
                    'sharpe_ratio': report.metrics.long_short_metrics.sharpe_ratio,
                    'max_drawdown': report.metrics.long_short_metrics.max_drawdown
                }
            }
        }

        if report.metrics.long_short_metrics.top_portfolio:
            metrics_dict['metrics']['top_portfolio'] = {
                'annual_return': report.metrics.long_short_metrics.top_portfolio.annual_return,
                'annual_volatility': report.metrics.long_short_metrics.top_portfolio.annual_volatility,
                'sharpe_ratio': report.metrics.long_short_metrics.top_portfolio.sharpe_ratio,
                'max_drawdown': report.metrics.long_short_metrics.top_portfolio.max_drawdown
            }
        
        if report.metrics.long_short_metrics.turnover:
            metrics_dict['metrics']['turnover'] = {
                'mean_turnover': report.metrics.long_short_metrics.turnover.mean_turnover,
                'max_turnover': report.metrics.long_short_metrics.turnover.max_turnover,
                'min_turnover': report.metrics.long_short_metrics.turnover.min_turnover
            }
        
        json_path = output_dir / f"{file_prefix}_metrics.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(metrics_dict, f, indent=2, ensure_ascii=False)
        exported_files['metrics_json'] = json_path
        
        # 2. 导出解释Markdown
        if report.explanation:
            explanation_path = output_dir / f"{file_prefix}_explanation.md"
            with open(explanation_path, 'w', encoding='utf-8') as f:
                f.write(f"# 回测报告: {report.factor_name}\n\n")
                f.write(f"**因子ID**: {report.factor_id}\n\n")
                f.write(f"**回测区间**: {report.backtest_period}\n\n")
                f.write("---\n\n")
                f.write(report.explanation)
            exported_files['explanation_md'] = explanation_path
        
        # 3. 导出图表
        if report.figures:
            if report.figures.ic_series_plot:
                ic_path = output_dir / f"{file_prefix}_ic_series.html"
                report.figures.ic_series_plot.write_html(str(ic_path))
                exported_files['ic_chart'] = ic_path
            
            if report.figures.layer_cumreturn_plot:
                layer_path = output_dir / f"{file_prefix}_layer_returns.html"
                report.figures.layer_cumreturn_plot.write_html(str(layer_path))
                exported_files['layer_chart'] = layer_path
            
            if report.figures.long_short_nav_plot:
                nav_path = output_dir / f"{file_prefix}_nav_curve.html"
                report.figures.long_short_nav_plot.write_html(str(nav_path))
                exported_files['nav_chart'] = nav_path
            
            if report.figures.ic_distribution_plot:
                dist_path = output_dir / f"{file_prefix}_ic_distribution.html"
                report.figures.ic_distribution_plot.write_html(str(dist_path))
                exported_files['ic_dist_chart'] = dist_path
        
        return exported_files


# 便捷函数
def run_factor_backtest(
    factor_data: pd.DataFrame,
    returns_data: pd.DataFrame,
    factor_name: str = "Factor",
    factor_id: str = "FACTOR_001",
    n_quantiles: int = 5,
    enable_plotting: bool = True,
    enable_llm: bool = True
) -> BacktestReport:
    """
    便捷函数：快速运行因子回测
    
    Args:
        factor_data: 因子数据
        returns_data: 收益数据
        factor_name: 因子名称
        factor_id: 因子ID
        n_quantiles: 分层数
        enable_plotting: 是否生成图表
        enable_llm: 是否启用LLM
        
    Returns:
        BacktestReport: 回测报告
    """
    from alpha_workbench.schemas.backtest_schemas import FactorSpec
    
    factor_spec = FactorSpec(
        factor_id=factor_id,
        factor_name=factor_name
    )
    
    input_data = BacktestInput(
        factor_spec=factor_spec,
        factor_data=factor_data,
        price_data=pd.DataFrame(),  # 占位
        returns_data=returns_data
    )
    
    backtest = FactorBacktest(
        n_quantiles=n_quantiles,
        enable_plotting=enable_plotting,
        enable_llm=enable_llm
    )
    
    return backtest.run(input_data)


def run_backtest(
    factor_specs: List[Dict[str, Any]],
    research_spec: Dict[str, Any],
    factor_data_dict: Optional[Dict[str, pd.DataFrame]] = None,
    price_data: Optional[pd.DataFrame] = None,
    returns_data: Optional[pd.DataFrame] = None,
    enable_plotting: bool = True,
    enable_llm: bool = False
) -> Dict[str, Any]:
    """
    批量回测接口（符合 team_work_plan.md 规范）
    
    Args:
        factor_specs: 因子规格列表，每个元素是 FactorSpec 字典
        research_spec: 研究配置规格字典
        factor_data_dict: 因子数据字典，key为factor_id，value为DataFrame
        price_data: 价格数据DataFrame（如果factor_data_dict未提供）
        returns_data: 收益数据DataFrame（可选）
        enable_plotting: 是否生成图表
        enable_llm: 是否启用LLM解释
        
    Returns:
        Dict 包含:
        - results: List[BacktestReport] 回测报告列表
        - summary: Dict 汇总统计
        - research_spec: ResearchSpec 研究配置
    """
    from alpha_workbench.schemas.backtest_schemas import FactorSpec
    
    # 解析 ResearchSpec
    rs = ResearchSpec.from_dict(research_spec) if research_spec else ResearchSpec()
    
    # 获取回测配置
    backtest_config = rs.backtest or {}
    n_quantiles = backtest_config.get('groups', 5)
    
    results = []
    errors = []
    
    print(f"开始批量回测: {len(factor_specs)} 个因子")
    print(f"股票池: {rs.universe}")
    print(f"分层数: {n_quantiles}")
    
    for i, factor_dict in enumerate(factor_specs, 1):
        factor_id = factor_dict.get('factor_id', f'FACTOR_{i:03d}')
        factor_name = factor_dict.get('factor_name', f'Factor {i}')
        
        print(f"\n[{i}/{len(factor_specs)}] 回测因子: {factor_id}")
        
        try:
            # 创建 FactorSpec
            factor_spec = FactorSpec.from_dict(factor_dict)
            
            # 获取因子数据
            if factor_data_dict and factor_id in factor_data_dict:
                factor_data = factor_data_dict[factor_id]
            elif factor_data_dict and factor_name in factor_data_dict:
                factor_data = factor_data_dict[factor_name]
            else:
                # 尝试从 price_data 生成（简化处理）
                if price_data is None:
                    raise ValueError(f"未找到因子 {factor_id} 的数据，且未提供 price_data")
                # 使用 sample_data 生成 mock 因子
                from alpha_workbench.data.sample_data import generate_momentum_factor
                factor_data = generate_momentum_factor(price_data)
            
            # 创建回测输入
            input_data = BacktestInput(
                factor_spec=factor_spec,
                factor_data=factor_data,
                price_data=price_data if price_data is not None else pd.DataFrame(),
                returns_data=returns_data,
                research_spec=rs,
                n_quantiles=n_quantiles
            )
            
            # 运行回测
            backtest = FactorBacktest(
                n_quantiles=n_quantiles,
                enable_plotting=enable_plotting,
                enable_llm=enable_llm
            )
            
            report = backtest.run(input_data)
            results.append(report)
            print(f"  ✓ 回测成功: IC={report.metrics.ic_metrics.ic_mean:.4f}, Sharpe={report.metrics.long_short_metrics.sharpe_ratio:.4f}")
            
        except Exception as e:
            error_msg = f"因子 {factor_id} 回测失败: {str(e)}"
            print(f"  ✗ {error_msg}")
            errors.append({
                'factor_id': factor_id,
                'error': str(e)
            })
    
    # 生成汇总
    success_results = [r for r in results if r is not None]
    summary = {
        'total_factors': len(factor_specs),
        'success_count': len(success_results),
        'failed_count': len(errors),
        'universe': rs.universe,
        'filters': rs.filters,
        'backtest_config': backtest_config
    }
    
    if success_results:
        summary['avg_ic_mean'] = np.mean([r.metrics.ic_metrics.ic_mean for r in success_results])
        summary['avg_sharpe'] = np.mean([r.metrics.long_short_metrics.sharpe_ratio for r in success_results])
    
    print(f"\n批量回测完成: {len(success_results)}/{len(factor_specs)} 成功")
    
    return {
        'results': results,
        'errors': errors,
        'summary': summary,
        'research_spec': rs
    }


def mock_run_backtest(
    factor_specs: Optional[List[Dict[str, Any]]] = None,
    research_spec: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Mock 批量回测接口（用于 UI 集成测试）
    
    Args:
        factor_specs: 因子规格列表（可选，使用默认值）
        research_spec: 研究配置规格（可选，使用默认值）
        
    Returns:
        Dict 包含 mock 回测结果
    """
    # 默认 mock 数据
    if factor_specs is None:
        factor_specs = [
            {
                'factor_id': 'MOM_20D',
                'factor_name': '20日动量因子',
                'description': '过去20个交易日的收益率',
                'formula_latex': r'r_{t-20:t} = \frac{P_t - P_{t-20}}{P_{t-20}}'
            },
            {
                'factor_id': 'REV_5D',
                'factor_name': '5日反转因子',
                'description': '过去5个交易日收益的负值',
                'formula_latex': r'REV = -r_{t-5:t}'
            },
            {
                'factor_id': 'VOL_20D',
                'factor_name': '20日波动率因子',
                'description': '过去20个交易日的收益率标准差',
                'formula_latex': r'\sigma_{20} = \sqrt{\frac{1}{20}\sum_{i=1}^{20}(r_i - \bar{r})^2}'
            }
        ]
    
    if research_spec is None:
        research_spec = {
            'universe': 'sample_universe',
            'filters': ['remove_ST', 'remove_new_listed_less_than_120_days'],
            'data_preference': {
                'profit_field': 'net_profit_after_deducting_non_recurring_items'
            },
            'backtest': {
                'rebalance_frequency': 'monthly',
                'holding_period': 20,
                'transaction_cost_bps': 20,
                'groups': 5
            }
        }
    
    # 生成 mock 结果
    results = []
    for factor_dict in factor_specs:
        factor_id = factor_dict['factor_id']
        
        # 生成 mock 回测报告（简化版）
        mock_report = {
            'factor_id': factor_id,
            'factor_name': factor_dict['factor_name'],
            'backtest_period': '2024-01-01 ~ 2024-12-31',
            'metrics': {
                'ic': {
                    'ic_mean': 0.03 + np.random.randn() * 0.01,
                    'ic_std': 0.12,
                    'icir': 0.25,
                    'ic_positive_ratio': 0.55,
                    'rank_ic_mean': 0.04,
                    'rank_ic_std': 0.14,
                    'rank_icir': 0.29
                },
                'layer': {
                    'layer_returns': {
                        'L1': -0.05,
                        'L2': -0.02,
                        'L3': 0.01,
                        'L4': 0.04,
                        'L5': 0.08
                    }
                },
                'long_short': {
                    'annual_return': 0.13,
                    'annual_volatility': 0.15,
                    'sharpe_ratio': 0.87,
                    'max_drawdown': -0.12
                }
            },
            'is_mock': True
        }
        results.append(mock_report)
    
    return {
        'results': results,
        'errors': [],
        'summary': {
            'total_factors': len(factor_specs),
            'success_count': len(factor_specs),
            'failed_count': 0,
            'universe': research_spec.get('universe', 'sample_universe'),
            'avg_ic_mean': 0.035,
            'avg_sharpe': 0.87
        },
        'research_spec': research_spec,
        'is_mock': True
    }
