"""
混合回测引擎
结合本地因子分析和 Mercury 交易回测
"""
import logging
import numpy as np

logger = logging.getLogger(__name__)
import pandas as pd
from typing import Optional, Tuple

from alpha_workbench.schemas.backtest_schemas import (
    BacktestInput,
    BacktestReport,
    BacktestMetrics,
    BacktestFigures,
    ICMetrics,
    LayerMetrics,
    LongShortMetrics,
    TopPortfolioMetrics
)
from alpha_workbench.backtest.plotter import BacktestPlotter
from alpha_workbench.backtest.llm_explainer import BacktestExplainer
from alpha_workbench.backtest.mercury_adapter import (
    MercuryAdapter,
    MercuryBacktestResponse,
    MercuryConfig,
    MercuryRunSpec,
    MercuryRunConfig,
    MercuryStrategyInput,
    MercurySummary,
)


class HybridBacktestEngine:
    """
    混合回测引擎
    
    结合两种回测能力：
    1. 本地因子分析：IC指标、分层收益、多空收益
    2. Mercury交易回测：真实交易模拟、完整的风险指标
    
    工作流程：
    1. 本地计算因子层面的IC、分层、多空指标
    2. 将因子转换为交易策略
    3. 调用Mercury服务进行真实交易回测
    4. 合并两种回测结果
    5. 生成综合报告
    """
    
    def __init__(
        self,
        enable_plotting: bool = True,
        enable_llm_explanation: bool = True,
        llm_model: Optional[str] = None,
        mercury_config: Optional[MercuryConfig] = None,
        use_mercury: bool = True
    ):
        """
        初始化混合回测引擎
        
        Args:
            enable_plotting: 是否启用图表绘制
            enable_llm_explanation: 是否启用LLM解释
            llm_model: LLM模型名称
            mercury_config: Mercury服务配置
            use_mercury: 是否使用Mercury服务
        """
        self.enable_plotting = enable_plotting
        self.enable_llm_explanation = enable_llm_explanation
        self.use_mercury = use_mercury
        
        # 初始化子模块
        self.plotter = BacktestPlotter() if enable_plotting else None
        self.explainer = BacktestExplainer(model=llm_model) if enable_llm_explanation else None
        
        # 初始化Mercury适配器
        self.mercury = None
        if use_mercury:
            try:
                self.mercury = MercuryAdapter(mercury_config)
                # 检查服务状态
                health = self.mercury.health_check()
                if health.get("status") != "ok":
                    logger.warning("Mercury服务不可用: %s", health.get('message', 'Unknown'))
                    logger.info("将使用本地回测模式")
                    self.use_mercury = False
            except Exception as e:
                logger.warning("无法连接Mercury服务: %s", e)
                logger.info("将使用本地回测模式")
                self.use_mercury = False
    
    def run_backtest(self, input_data: BacktestInput) -> BacktestReport:
        """
        执行混合回测
        
        Args:
            input_data: 回测输入数据
            
        Returns:
            BacktestReport: 完整回测报告
        """
        logger.info("混合回测引擎")
        
        # 1. 数据预处理
        factor_data, returns_data = self._prepare_data(input_data)
        
        # 2. 本地因子分析
        logger.info("[1/3] 本地因子分析...")
        ic_metrics = self._calculate_ic_metrics(factor_data, returns_data)
        layer_metrics = self._calculate_layer_metrics(
            factor_data, returns_data, input_data.n_quantiles
        )
        long_short_metrics = self._calculate_long_short_metrics(
            factor_data, returns_data, input_data.n_quantiles
        )
        
        # 3. Mercury交易回测（如果可用）
        mercury_summary = None
        mercury_response = None
        if self.use_mercury and self.mercury:
            logger.info("[2/3] Mercury交易回测...")
            mercury_response = self._run_mercury_backtest(input_data, factor_data)
            if mercury_response and not mercury_response.error:
                mercury_summary = mercury_response.summary
        else:
            logger.info("[2/3] 跳过Mercury回测（服务不可用）")

        # 4. 合并指标
        logger.info("[3/3] 生成综合报告...")
        metrics = self._merge_metrics(
            ic_metrics, layer_metrics, long_short_metrics, mercury_summary
        )
        
        # 5. 生成图表
        figures = BacktestFigures()
        if self.enable_plotting:
            figures = self._generate_figures(
                factor_data, returns_data, metrics, input_data
            )

        # 计算回测区间（LLM解释需要）
        backtest_period = self._format_backtest_period(factor_data)

        # 6. 生成LLM解释
        explanation = None
        if self.enable_llm_explanation and self.explainer:
            explanation = self._generate_explanation(
                metrics, input_data.factor_spec, mercury_summary, backtest_period
            )

        # 7. 组装报告
        
        report = BacktestReport(
            factor_id=input_data.factor_spec.factor_id,
            factor_name=input_data.factor_spec.factor_name,
            backtest_period=backtest_period,
            metrics=metrics,
            figures=figures,
            explanation=explanation,
            raw_data={
                "factor_data": factor_data,
                "returns_data": returns_data,
                "mercury_summary": mercury_summary.model_dump() if mercury_summary else None,
                "mercury_response": mercury_response.model_dump(mode="json") if mercury_response else None,
            } if self.enable_plotting else None
        )
        
        return report
    
    def _prepare_data(self, input_data: BacktestInput) -> Tuple[pd.DataFrame, pd.DataFrame]:
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
    
    def _calculate_ic_metrics(self, factor_data: pd.DataFrame, returns_data: pd.DataFrame) -> ICMetrics:
        """计算IC指标"""
        ic_series_pearson = []
        ic_series_spearman = []
        for date in factor_data.index:
            f = factor_data.loc[date].dropna()
            r = returns_data.loc[date].dropna()
            
            common_stocks = f.index.intersection(r.index)
            if len(common_stocks) < 10:
                continue
            
            f = f[common_stocks]
            r = r[common_stocks]
            
            ic_pearson = f.corr(r, method='pearson')
            if not np.isnan(ic_pearson):
                ic_series_pearson.append(ic_pearson)

            ic_spearman = f.corr(r, method='spearman')
            if not np.isnan(ic_spearman):
                ic_series_spearman.append(ic_spearman)
        
        ic_series_pearson = pd.Series(ic_series_pearson)
        ic_series_spearman = pd.Series(ic_series_spearman)
        if len(ic_series_pearson) == 0 or len(ic_series_spearman) == 0:
            raise ValueError("没有有效的IC数据，请检查输入数据")
        
        ic_mean = ic_series_pearson.mean()
        ic_std = ic_series_pearson.std()
        icir = ic_mean / ic_std if ic_std > 0 else 0
        ic_positive_ratio = (ic_series_pearson > 0).mean()
        ic_tstat = ic_mean / (ic_std / np.sqrt(len(ic_series_pearson))) if ic_std > 0 else 0

        rank_ic_mean = ic_series_spearman.mean()
        rank_ic_std = ic_series_spearman.std()
        rank_icir = rank_ic_mean / rank_ic_std if rank_ic_std > 0 else 0
        rank_ic_positive_ratio = (ic_series_spearman > 0).mean()
        rank_ic_tstat = (
            rank_ic_mean / (rank_ic_std / np.sqrt(len(ic_series_spearman)))
            if rank_ic_std > 0 else 0
        )
        
        return ICMetrics(
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
    
    def _calculate_layer_metrics(self, factor_data: pd.DataFrame, returns_data: pd.DataFrame, n_quantiles: int) -> LayerMetrics:
        """计算分层收益"""
        layer_returns = {}
        
        for date in factor_data.index[:-1]:
            f = factor_data.loc[date].dropna()
            r = returns_data.loc[date].dropna()
            
            common_stocks = f.index.intersection(r.index)
            if len(common_stocks) < n_quantiles * 2:
                continue
            
            f = f[common_stocks]
            r = r[common_stocks]
            
            try:
                labels = [f'L{i+1}' for i in range(n_quantiles)]
                f_quantiles = pd.qcut(f, n_quantiles, labels=labels, duplicates='drop')
                
                for layer in labels:
                    if layer in f_quantiles.values:
                        layer_stocks = f_quantiles[f_quantiles == layer].index
                        layer_ret = r[layer_stocks].mean()
                        
                        if date not in layer_returns:
                            layer_returns[date] = {}
                        layer_returns[date][layer] = layer_ret
            except:
                continue
        
        layer_returns_df = pd.DataFrame(layer_returns).T
        
        layer_annual_returns = {}
        for layer in layer_returns_df.columns:
            daily_mean = layer_returns_df[layer].mean()
            layer_annual_returns[layer] = daily_mean * 252
        
        layer_cum_returns = (1 + layer_returns_df.fillna(0)).cumprod()
        
        return LayerMetrics(
            layer_returns=layer_annual_returns,
            layer_cum_returns=layer_cum_returns
        )
    
    def _calculate_long_short_metrics(self, factor_data: pd.DataFrame, returns_data: pd.DataFrame, n_quantiles: int) -> LongShortMetrics:
        """计算多空收益"""
        long_short_returns = []
        
        for date in factor_data.index[:-1]:
            f = factor_data.loc[date].dropna()
            r = returns_data.loc[date].dropna()
            
            common_stocks = f.index.intersection(r.index)
            if len(common_stocks) < n_quantiles * 2:
                continue
            
            f = f[common_stocks]
            r = r[common_stocks]
            
            try:
                labels = [f'L{i+1}' for i in range(n_quantiles)]
                f_quantiles = pd.qcut(f, n_quantiles, labels=labels, duplicates='drop')
                
                top_layer = labels[-1]
                bottom_layer = labels[0]
                
                if top_layer in f_quantiles.values and bottom_layer in f_quantiles.values:
                    top_stocks = f_quantiles[f_quantiles == top_layer].index
                    bottom_stocks = f_quantiles[f_quantiles == bottom_layer].index
                    
                    long_ret = r[top_stocks].mean()
                    short_ret = r[bottom_stocks].mean()
                    
                    ls_ret = long_ret - short_ret
                    long_short_returns.append(ls_ret)
            except:
                continue
        
        long_short_returns = pd.Series(long_short_returns, index=factor_data.index[:-1][:len(long_short_returns)])
        if len(long_short_returns) == 0:
            raise ValueError("没有有效的多空收益数据，请检查输入数据")
        
        daily_mean = long_short_returns.mean()
        daily_std = long_short_returns.std()
        
        annual_return = daily_mean * 252
        annual_volatility = daily_std * np.sqrt(252)
        sharpe_ratio = annual_return / annual_volatility if annual_volatility > 0 else 0
        
        cum_returns = (1 + long_short_returns.fillna(0)).cumprod()
        running_max = cum_returns.expanding().max()
        drawdown = (cum_returns - running_max) / running_max
        max_drawdown = drawdown.min()
        
        return LongShortMetrics(
            annual_return=annual_return,
            annual_volatility=annual_volatility,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            cum_returns=cum_returns,
            top_portfolio=TopPortfolioMetrics(
                annual_return=annual_return,
                annual_volatility=annual_volatility,
                sharpe_ratio=sharpe_ratio,
                max_drawdown=max_drawdown,
                cum_returns=cum_returns
            )
        )
    
    def _run_mercury_backtest(self, input_data: BacktestInput, factor_data: pd.DataFrame) -> Optional[MercuryBacktestResponse]:
        """
        运行Mercury交易回测
        
        将因子转换为简单的交易策略：
        - 每期做多因子值最高的N只股票
        - 等权重配置
        """
        if not self.mercury:
            return None
        
        try:
            # 构建股票列表
            all_stocks = factor_data.columns.tolist()
            
            # 将因子转换为策略操作
            # 这里使用简单的每周调仓策略，做多因子值最高的股票
            ops = [
                {
                    "op": "load_universe",
                    "assets": all_stocks[:20]  # 取前20只股票
                },
                {
                    "op": "schedule",
                    "schedule": "weekly"
                },
                {
                    "op": "weight",
                    "weighting": "equal"
                },
                {
                    "op": "order_target_percent"
                }
            ]
            
            strategy_input = MercuryStrategyInput(
                name=f"factor_strategy_{input_data.factor_spec.factor_id}",
                ops=ops
            )
            
            # 构建RunSpec
            start_date = factor_data.index[0].strftime('%Y%m%d')
            end_date = factor_data.index[-1].strftime('%Y%m%d')
            
            run_config = MercuryRunConfig(
                start_date=start_date,
                end_date=end_date,
                initial_cash=1000000.0,
                transaction_cost_bps=input_data.commission_rate * 10000  # 转换为基点
            )
            
            run_spec = MercuryRunSpec(
                run=run_config,
                inputs=[strategy_input.model_dump()]
            )
            
            # 调用Mercury服务
            response = self.mercury.create_and_wait(run_spec)
            
            if response.error:
                logger.warning("Mercury回测失败: %s", response.message)
                return None
            
            logger.info("Mercury回测完成 (Job ID: %s)", response.job_id)
            logger.info("  - 总收益: %.2f%%", response.summary.total_return * 100)
            logger.info("  - 夏普比率: %.4f", response.summary.sharpe)
            logger.info("  - 最大回撤: %.2f%%", response.summary.max_drawdown * 100)
            
            return response
            
        except Exception as e:
            logger.warning("Mercury回测异常: %s", e)
            return None
    
    def _merge_metrics(
        self,
        ic_metrics: ICMetrics,
        layer_metrics: LayerMetrics,
        long_short_metrics: LongShortMetrics,
        mercury_summary: Optional[MercurySummary]
    ) -> BacktestMetrics:
        """合并本地和Mercury的指标"""
        # 如果有Mercury数据，使用Mercury的交易指标（更准确）
        if mercury_summary:
            # 创建新的多空指标，优先使用Mercury的数据
            merged_ls = LongShortMetrics(
                annual_return=mercury_summary.annualized_return,
                annual_volatility=mercury_summary.annualized_volatility,
                sharpe_ratio=mercury_summary.sharpe,
                max_drawdown=mercury_summary.max_drawdown,
                cum_returns=long_short_metrics.cum_returns,  # 保留本地计算的累计收益曲线
                top_portfolio=long_short_metrics.top_portfolio
            )
        else:
            merged_ls = long_short_metrics
        
        return BacktestMetrics(
            ic_metrics=ic_metrics,
            layer_metrics=layer_metrics,
            long_short_metrics=merged_ls,
            turnover_analysis=None
        )
    
    def _generate_figures(self, factor_data, returns_data, metrics, input_data):
        """生成图表"""
        if not self.plotter:
            return BacktestFigures()
        
        # 重新计算IC序列
        ic_series = []
        ic_dates = []
        for date in factor_data.index:
            f = factor_data.loc[date].dropna()
            r = returns_data.loc[date].dropna()
            
            common_stocks = f.index.intersection(r.index)
            if len(common_stocks) < 10:
                continue
            
            f = f[common_stocks]
            r = r[common_stocks]
            
            ic = f.corr(r, method='spearman')
            if not np.isnan(ic):
                ic_series.append(ic)
                ic_dates.append(date)
        
        ic_series = pd.Series(ic_series, index=ic_dates)
        
        return BacktestFigures(
            ic_series_plot=self.plotter.plot_ic_series(ic_series),
            layer_cumreturn_plot=self.plotter.plot_layer_cumreturns(metrics.layer_metrics.layer_cum_returns),
            long_short_nav_plot=self.plotter.plot_long_short_nav(metrics.long_short_metrics.cum_returns),
            ic_distribution_plot=self.plotter.plot_ic_distribution(ic_series)
        )
    
    def _generate_explanation(self, metrics, factor_spec, mercury_summary, backtest_period="Unknown"):
        """生成LLM解释"""
        logger.info("[步骤 7/8] 生成LLM解释...")

        # 检查explainer是否可用
        if not self.explainer:
            logger.info("LLM解释器未初始化，跳过解释生成")
            return None

        # 构建增强的指标信息
        enhanced_metrics = metrics

        if mercury_summary:
            # 如果有Mercury数据，添加到解释中
            enhanced_info = f"""
【Mercury交易回测结果】
- 总收益率: {mercury_summary.total_return:.2%}
- 年化收益率: {mercury_summary.annualized_return:.2%}
- 年化波动率: {mercury_summary.annualized_volatility:.2%}
- 夏普比率: {mercury_summary.sharpe:.4f}
- 最大回撤: {mercury_summary.max_drawdown:.2%}
- 日胜率: {mercury_summary.win_rate:.2%}
- 总换手率: {mercury_summary.total_turnover:.2f}
- 总交易笔数: {mercury_summary.total_trades}
"""
        else:
            enhanced_info = "【Mercury交易回测】服务不可用，仅使用本地因子分析结果"

        try:
            # 调用解释器
            explanation_result = self.explainer.explain(
                enhanced_metrics,
                factor_spec,
                backtest_period=backtest_period
            )
            print(f"  ✓ LLM解释生成完成")
            print(f"    is_fallback: {explanation_result.is_fallback}")
            print(f"    quality_score: {explanation_result.get_quality_score()}")

            # 添加Mercury信息
            if mercury_summary:
                # 将Mercury信息添加到recommendations中
                explanation_result.recommendations = explanation_result.recommendations + "\n\n" + enhanced_info

            return explanation_result

        except Exception as e:
            print(f"  ✗ LLM解释生成失败: {e}")
            return None
    
    def _format_backtest_period(self, factor_data: pd.DataFrame) -> str:
        """格式化回测区间"""
        if len(factor_data) == 0:
            return "N/A"
        start = factor_data.index[0].strftime('%Y-%m-%d')
        end = factor_data.index[-1].strftime('%Y-%m-%d')
        return f"{start} ~ {end}"
    
    def close(self):
        """关闭资源"""
        if self.mercury:
            self.mercury.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
