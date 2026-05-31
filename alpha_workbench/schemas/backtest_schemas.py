"""
Backtest schemas for AlphaWorkbench Role 5
定义回测相关的Pydantic模型
"""
from typing import List, Dict, Any, Optional, Union
from datetime import date
from enum import Enum
from pydantic import BaseModel, Field
import pandas as pd
import plotly.graph_objects as go


class DataField(str, Enum):
    """数据字段枚举"""
    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"
    VOLUME = "volume"
    AMOUNT = "amount"
    VWAP = "vwap"
    TURNOVER = "turnover"


class DataFrequency(str, Enum):
    """数据频率枚举"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class NodeType(str, Enum):
    """表达式树节点类型"""
    BINARY = "binary"
    UNARY = "unary"
    FUNCTION = "function"
    VARIABLE = "variable"
    CONSTANT = "constant"
    CROSS_SECTIONAL = "cross_sectional"


class DataRequirements(BaseModel):
    """数据需求定义"""
    fields: List[DataField] = Field(
        default=[DataField.CLOSE],
        description="需要的字段列表"
    )
    min_lookback: int = Field(
        default=20,
        description="最小回看周期（用于数据加载）",
        ge=1
    )
    frequency: DataFrequency = Field(
        default=DataFrequency.DAILY,
        description="数据频率"
    )
    universe: Optional[str] = Field(
        default=None,
        description="股票池定义"
    )


class ExpressionTree(BaseModel):
    """表达式树节点"""
    type: NodeType = Field(..., description="节点类型")
    operator: Optional[str] = Field(
        default=None,
        description="操作符或函数名"
    )
    left: Optional["ExpressionTree"] = Field(
        default=None,
        description="左子节点（二元操作）"
    )
    right: Optional["ExpressionTree"] = Field(
        default=None,
        description="右子节点（二元操作）"
    )
    operand: Optional["ExpressionTree"] = Field(
        default=None,
        description="单操作数（一元操作）"
    )
    args: Optional[List["ExpressionTree"]] = Field(
        default=None,
        description="函数参数列表"
    )
    value: Optional[Union[float, int, str, bool]] = Field(
        default=None,
        description="常量值"
    )
    name: Optional[Union[DataField, str]] = Field(
        default=None,
        description="变量名"
    )
    window: Optional[int] = Field(
        default=None,
        description="时序窗口大小（用于rolling/ts函数）",
        ge=1
    )

    class Config:
        arbitrary_types_allowed = True


class ValueRange(BaseModel):
    """值范围定义"""
    min: Optional[float] = Field(default=None, description="最小值")
    max: Optional[float] = Field(default=None, description="最大值")


class ICExpectation(BaseModel):
    """IC期望定义"""
    direction: str = Field(
        default="positive",
        description="期望IC方向",
        pattern="^(positive|negative)$"
    )
    min_icir: float = Field(
        default=0.3,
        description="最小可接受ICIR",
        ge=0
    )


class ExpectedBehavior(BaseModel):
    """期望行为特征（用于验证）"""
    value_range: Optional[ValueRange] = Field(
        default=None,
        description="期望的值范围"
    )
    ic_expectation: Optional[ICExpectation] = Field(
        default=None,
        description="IC期望"
    )
    layer_monotonicity: bool = Field(
        default=True,
        description="期望分层收益是否单调"
    )


class FactorSpec(BaseModel):
    """因子规格定义（来自角色4）- 扩展版"""
    factor_id: str = Field(
        ...,
        description="因子唯一标识",
        pattern="^[A-Z][A-Z0-9_]*$"
    )
    factor_name: str = Field(..., description="因子名称")
    formula_latex: Optional[str] = Field(
        default=None,
        description="LaTeX公式表示"
    )
    expression_tree: Optional[ExpressionTree] = Field(
        default=None,
        description="可执行的表达式树"
    )
    description: Optional[str] = Field(
        default=None,
        description="因子描述"
    )
    data_requirements: DataRequirements = Field(
        default_factory=DataRequirements,
        description="数据需求定义"
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="因子参数配置"
    )
    expected_behavior: Optional[ExpectedBehavior] = Field(
        default=None,
        description="期望行为特征"
    )

    class Config:
        arbitrary_types_allowed = True

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于JSON序列化）"""
        return self.model_dump(mode='json')

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FactorSpec":
        """从字典创建FactorSpec"""
        return cls(**data)


class ResearchSpec(BaseModel):
    """研究配置规格（来自 team_work_plan.md）"""
    universe: str = Field(
        default="sample_universe",
        description="股票池定义，如 CSI500, sample_universe"
    )
    filters: List[str] = Field(
        default_factory=list,
        description="过滤规则列表，如 remove_ST, remove_new_listed"
    )
    data_preference: Dict[str, str] = Field(
        default_factory=dict,
        description="数据字段偏好配置"
    )
    custom_rules: List[str] = Field(
        default_factory=list,
        description="自定义规则列表"
    )
    backtest: Dict[str, Any] = Field(
        default_factory=dict,
        description="回测配置参数"
    )

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchSpec":
        """从字典创建ResearchSpec"""
        return cls(**data)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "universe": self.universe,
            "filters": self.filters,
            "data_preference": self.data_preference,
            "custom_rules": self.custom_rules,
            "backtest": self.backtest
        }


class BacktestInput(BaseModel):
    """回测输入模型（支持批量回测）"""
    factor_spec: FactorSpec = Field(..., description="因子规格")
    factor_data: pd.DataFrame = Field(
        ...,
        description="因子值DataFrame，index=date, columns=stock_code"
    )
    price_data: pd.DataFrame = Field(
        ...,
        description="价格数据DataFrame，index=date, columns=stock_code"
    )
    returns_data: Optional[pd.DataFrame] = Field(
        default=None,
        description="收益率数据（可选，会从价格计算）"
    )
    research_spec: Optional[ResearchSpec] = Field(
        default=None,
        description="研究配置规格（可选）"
    )
    start_date: Optional[date] = Field(
        default=None,
        description="回测开始日期"
    )
    end_date: Optional[date] = Field(
        default=None,
        description="回测结束日期"
    )
    n_quantiles: int = Field(
        default=5,
        description="分层数量，默认5层",
        ge=2,
        le=10
    )
    commission_rate: float = Field(
        default=0.001,
        description="手续费率，默认千分之一",
        ge=0,
        le=0.1
    )
    slippage: float = Field(
        default=0.001,
        description="滑点，默认千分之一",
        ge=0,
        le=0.1
    )

    class Config:
        arbitrary_types_allowed = True


class ICMetrics(BaseModel):
    """IC指标（包含IC和RankIC）"""
    # Pearson IC
    ic_mean: float = Field(..., description="IC均值（Pearson）")
    ic_std: float = Field(..., description="IC标准差（Pearson）")
    icir: float = Field(..., description="ICIR（Pearson）")
    ic_positive_ratio: float = Field(..., description="IC为正的比例（Pearson）")
    ic_tstat: float = Field(..., description="IC的t统计量（Pearson）")
    
    # Rank IC (Spearman)
    rank_ic_mean: float = Field(..., description="RankIC均值（Spearman）")
    rank_ic_std: float = Field(..., description="RankIC标准差（Spearman）")
    rank_icir: float = Field(..., description="RankICIR（Spearman）")
    rank_ic_positive_ratio: float = Field(..., description="RankIC为正的比例（Spearman）")
    rank_ic_tstat: float = Field(..., description="RankIC的t统计量（Spearman）")


class LayerMetrics(BaseModel):
    """分层收益指标"""
    layer_returns: Dict[str, float] = Field(
        ...,
        description="各层年化收益"
    )
    layer_cum_returns: pd.DataFrame = Field(
        ...,
        description="各层累计收益曲线"
    )

    class Config:
        arbitrary_types_allowed = True


class TurnoverMetrics(BaseModel):
    """换手率指标"""
    mean_turnover: float = Field(..., description="平均换手率")
    max_turnover: float = Field(..., description="最大换手率")
    min_turnover: float = Field(..., description="最小换手率")
    turnover_series: pd.Series = Field(..., description="换手率序列")
    
    class Config:
        arbitrary_types_allowed = True


class TopPortfolioMetrics(BaseModel):
    """Top组合指标"""
    annual_return: float = Field(..., description="年化收益")
    annual_volatility: float = Field(..., description="年化波动率")
    sharpe_ratio: float = Field(..., description="夏普比率")
    max_drawdown: float = Field(..., description="最大回撤")
    cum_returns: pd.Series = Field(..., description="累计收益序列")
    
    class Config:
        arbitrary_types_allowed = True


class LongShortMetrics(BaseModel):
    """多空收益指标"""
    annual_return: float = Field(..., description="多空组合年化收益")
    annual_volatility: float = Field(..., description="年化波动率")
    sharpe_ratio: float = Field(..., description="夏普比率")
    max_drawdown: float = Field(..., description="最大回撤")
    cum_returns: pd.Series = Field(..., description="累计收益序列")
    turnover: Optional[TurnoverMetrics] = Field(
        default=None,
        description="换手率分析"
    )
    top_portfolio: Optional[TopPortfolioMetrics] = Field(
        default=None,
        description="Top组合指标"
    )

    class Config:
        arbitrary_types_allowed = True


class BacktestMetrics(BaseModel):
    """回测指标集合"""
    ic_metrics: ICMetrics = Field(..., description="IC指标")
    layer_metrics: LayerMetrics = Field(..., description="分层收益指标")
    long_short_metrics: LongShortMetrics = Field(
        ...,
        description="多空收益指标"
    )
    turnover_analysis: Optional[Dict[str, Any]] = Field(
        default=None,
        description="换手率分析"
    )


class BacktestFigures(BaseModel):
    """回测图表集合"""
    ic_series_plot: Optional[go.Figure] = Field(
        default=None,
        description="IC序列图"
    )
    layer_cumreturn_plot: Optional[go.Figure] = Field(
        default=None,
        description="分层累计收益图"
    )
    long_short_nav_plot: Optional[go.Figure] = Field(
        default=None,
        description="多空净值曲线图"
    )
    ic_distribution_plot: Optional[go.Figure] = Field(
        default=None,
        description="IC分布图"
    )

    class Config:
        arbitrary_types_allowed = True


class BacktestExplanationResult(BaseModel):
    """LLM回测解释结构化输出

    包含完整的回测结果解释和元数据：
    - is_fallback: 标记是否为mock/备用模式生成
    - missing_fields: 记录LLM输出中缺失的字段
    - validation_errors: 记录数据验证错误
    """
    summary: str = Field(..., description="总体评价")
    ic_analysis: str = Field(..., description="IC指标分析")
    layer_analysis: str = Field(..., description="分层收益分析")
    long_short_analysis: str = Field(..., description="多空组合分析")
    turnover_analysis: str = Field(default="", description="换手率分析")
    risk_assessment: str = Field(..., description="风险评估")
    recommendations: str = Field(..., description="改进建议")
    is_fallback: bool = Field(..., description="是否为mock模式生成的解释")
    raw_llm_output: Optional[str] = Field(default=None, description="原始LLM输出（调试用）")
    missing_fields: List[str] = Field(default_factory=list, description="缺失的字段列表")
    validation_errors: List[str] = Field(default_factory=list, description="数据验证错误列表")
    generation_metadata: Dict[str, Any] = Field(default_factory=dict, description="生成元数据（时间、模型等）")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于JSON序列化）"""
        return {
            "summary": self.summary,
            "ic_analysis": self.ic_analysis,
            "layer_analysis": self.layer_analysis,
            "long_short_analysis": self.long_short_analysis,
            "turnover_analysis": self.turnover_analysis,
            "risk_assessment": self.risk_assessment,
            "recommendations": self.recommendations,
            "is_fallback": self.is_fallback,
            "raw_llm_output": self.raw_llm_output,
            "missing_fields": self.missing_fields,
            "validation_errors": self.validation_errors,
            "generation_metadata": self.generation_metadata
        }

    def validate_completeness(self) -> Dict[str, Any]:
        """验证解释结果的完整性

        Returns:
            包含验证结果的字典：
            - is_complete: 是否完整
            - missing_fields: 缺失字段列表
            - warnings: 警告信息列表
        """
        required_fields = [
            "summary", "ic_analysis", "layer_analysis",
            "long_short_analysis", "risk_assessment", "recommendations"
        ]
        optional_fields = ["turnover_analysis"]

        missing = []
        warnings = []

        # 检查必需字段
        for field in required_fields:
            value = getattr(self, field, None)
            if not value or (isinstance(value, str) and len(value.strip()) == 0):
                missing.append(field)

        # 检查可选字段
        for field in optional_fields:
            value = getattr(self, field, None)
            if not value or (isinstance(value, str) and len(value.strip()) == 0):
                warnings.append(f"可选字段 '{field}' 为空")

        # 更新 missing_fields
        self.missing_fields = missing

        return {
            "is_complete": len(missing) == 0,
            "missing_fields": missing,
            "warnings": warnings,
            "completeness_score": (len(required_fields) - len(missing)) / len(required_fields)
        }

    def add_validation_error(self, error: str):
        """添加验证错误"""
        if error not in self.validation_errors:
            self.validation_errors.append(error)

    def add_generation_metadata(self, key: str, value: Any):
        """添加生成元数据"""
        self.generation_metadata[key] = value

    def get_quality_score(self) -> float:
        """获取解释质量评分 (0-1)"""
        validation = self.validate_completeness()
        base_score = validation["completeness_score"]

        # 如果是fallback模式，扣分
        if self.is_fallback:
            base_score *= 0.8

        # 如果有验证错误，扣分
        if self.validation_errors:
            base_score *= max(0.5, 1 - len(self.validation_errors) * 0.1)

        return round(base_score, 2)


class BacktestReport(BaseModel):
    """完整回测报告"""
    factor_id: str = Field(..., description="因子ID")
    factor_name: str = Field(..., description="因子名称")
    backtest_period: str = Field(..., description="回测区间")
    metrics: BacktestMetrics = Field(..., description="回测指标")
    figures: BacktestFigures = Field(..., description="图表对象")
    explanation: Optional[Union[str, BacktestExplanationResult]] = Field(
        default=None,
        description="LLM生成的回测解释（字符串或结构化对象）"
    )
    raw_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="原始回测数据（可选，用于调试）"
    )

    class Config:
        arbitrary_types_allowed = True

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于JSON序列化）"""
        explanation_data = None
        if self.explanation is not None:
            if isinstance(self.explanation, BacktestExplanationResult):
                explanation_data = self.explanation.to_dict()
            else:
                explanation_data = self.explanation
        return {
            "factor_id": self.factor_id,
            "factor_name": self.factor_name,
            "backtest_period": self.backtest_period,
            "metrics": self.metrics.model_dump(),
            "explanation": explanation_data
        }


ExpressionTree.model_rebuild()
