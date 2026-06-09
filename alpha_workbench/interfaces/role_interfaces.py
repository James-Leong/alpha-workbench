"""
Role2 和 Role6 接口定义
定义与其他角色的数据交换格式
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


# ==================== Role2 接口（数据层）====================

class DataSourceType(str, Enum):
    """数据源类型"""
    CSV = "csv"
    DATABASE = "database"
    API = "api"
    CACHE = "cache"


class Role2DataRequest(BaseModel):
    """
    Role2 数据请求
    从 Role5 发送到 Role2 的数据请求
    """
    request_id: str = Field(..., description="请求唯一标识")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    # 数据需求
    data_type: str = Field(..., description="数据类型: price/factor/market_data")
    fields: List[str] = Field(default_factory=list, description="需要的字段")
    
    # 时间范围
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")
    
    # 股票范围
    stock_codes: Optional[List[str]] = Field(default=None, description="股票代码列表")
    universe: Optional[str] = Field(default=None, description="股票池名称")
    
    # 频率
    frequency: str = Field(default="daily", description="数据频率: daily/weekly/monthly")
    
    # 数据源偏好
    preferred_source: Optional[DataSourceType] = Field(default=None, description="优先数据源")


class Role2DataResponse(BaseModel):
    """
    Role2 数据响应
    Role2 返回给 Role5 的数据
    """
    request_id: str = Field(..., description="对应请求的ID")
    status: str = Field(..., description="状态: success/error")
    message: Optional[str] = Field(default=None, description="状态信息")
    
    # 数据内容
    data: Optional[Dict[str, Any]] = Field(default=None, description="数据内容")
    data_format: str = Field(default="dataframe", description="数据格式: dataframe/json/csv_path")
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="数据元信息")
    
    # 数据质量
    data_quality: Dict[str, Any] = Field(default_factory=dict, description="数据质量指标")


class Role2BacktestDataQuery(BaseModel):
    """
    Role2 回测数据查询
    专门用于回测的数据查询
    """
    query_id: str = Field(..., description="查询ID")
    
    # 因子数据
    factor_data_path: Optional[str] = Field(default=None, description="因子数据路径")
    factor_id: Optional[str] = Field(default=None, description="因子ID")
    
    # 价格数据
    price_data_path: Optional[str] = Field(default=None, description="价格数据路径")
    price_fields: List[str] = Field(default_factory=lambda: ["close"], description="价格字段")
    
    # 时间范围
    start_date: str = Field(..., description="开始日期")
    end_date: str = Field(..., description="结束日期")
    
    # 股票池
    stock_universe: Optional[str] = Field(default=None, description="股票池")
    
    # 对齐要求
    align_dates: bool = Field(default=True, description="是否对齐日期")
    align_stocks: bool = Field(default=True, description="是否对齐股票")


# ==================== Role6 接口（展示层）====================

class VisualizationType(str, Enum):
    """可视化类型"""
    IC_SERIES = "ic_series"
    LAYER_RETURNS = "layer_returns"
    LONG_SHORT_NAV = "long_short_nav"
    IC_DISTRIBUTION = "ic_distribution"
    FACTOR_DISTRIBUTION = "factor_distribution"
    CORRELATION_HEATMAP = "correlation_heatmap"


class Role6VisualizationRequest(BaseModel):
    """
    Role6 可视化请求
    Role5 请求 Role6 生成可视化
    """
    request_id: str = Field(..., description="请求唯一标识")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    # 可视化类型
    viz_type: VisualizationType = Field(..., description="可视化类型")
    
    # 数据
    data: Dict[str, Any] = Field(..., description="可视化数据")
    
    # 配置
    config: Dict[str, Any] = Field(default_factory=dict, description="可视化配置")
    
    # 输出格式
    output_format: str = Field(default="html", description="输出格式: html/png/svg")
    output_path: Optional[str] = Field(default=None, description="输出路径")


class Role6VisualizationResponse(BaseModel):
    """
    Role6 可视化响应
    """
    request_id: str = Field(..., description="对应请求的ID")
    status: str = Field(..., description="状态: success/error")
    message: Optional[str] = Field(default=None, description="状态信息")
    
    # 输出
    output_path: Optional[str] = Field(default=None, description="输出文件路径")
    output_data: Optional[str] = Field(default=None, description="Base64编码的图像数据")
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="可视化元信息")


class Role6DashboardRequest(BaseModel):
    """
    Role6 仪表板请求
    请求生成完整的回测仪表板
    """
    request_id: str = Field(..., description="请求唯一标识")
    
    # 回测报告
    backtest_report: Dict[str, Any] = Field(..., description="回测报告数据")
    
    # 图表列表
    required_charts: List[VisualizationType] = Field(
        default_factory=lambda: [
            VisualizationType.IC_SERIES,
            VisualizationType.LAYER_RETURNS,
            VisualizationType.LONG_SHORT_NAV
        ]
    )
    
    # 仪表板配置
    dashboard_title: str = Field(default="因子回测报告", description="仪表板标题")
    theme: str = Field(default="default", description="主题")
    layout: str = Field(default="grid", description="布局: grid/tabs/single")
    
    # 交互功能
    enable_interaction: bool = Field(default=True, description="启用交互")
    enable_export: bool = Field(default=True, description="启用导出")


class Role6DashboardResponse(BaseModel):
    """
    Role6 仪表板响应
    """
    request_id: str = Field(..., description="对应请求的ID")
    status: str = Field(..., description="状态: success/error")
    
    # 输出
    dashboard_path: Optional[str] = Field(default=None, description="仪表板文件路径")
    dashboard_url: Optional[str] = Field(default=None, description="仪表板访问URL")
    
    # 组件
    components: List[Dict[str, Any]] = Field(default_factory=list, description="仪表板组件列表")


# ==================== Role5 输出接口 ====================

class Role5BacktestOutput(BaseModel):
    """
    Role5 回测输出
    Role5 生成的完整回测结果，可发送给 Role2 和 Role6
    """
    # 基本信息
    output_id: str = Field(..., description="输出唯一标识")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    version: str = Field(default="1.0.0", description="输出格式版本")
    
    # 因子信息
    factor_id: str = Field(..., description="因子ID")
    factor_name: str = Field(..., description="因子名称")
    factor_description: Optional[str] = Field(default=None, description="因子描述")
    
    # 回测配置
    backtest_config: Dict[str, Any] = Field(default_factory=dict, description="回测配置")
    
    # 回测结果
    metrics: Dict[str, Any] = Field(..., description="回测指标")
    ic_metrics: Dict[str, float] = Field(..., description="IC指标")
    layer_metrics: Dict[str, Any] = Field(..., description="分层收益指标")
    long_short_metrics: Dict[str, Any] = Field(..., description="多空收益指标")
    
    # 图表数据
    chart_data: Dict[str, Any] = Field(default_factory=dict, description="图表数据")
    
    # LLM解释
    llm_explanation: Optional[str] = Field(default=None, description="LLM生成的解释")
    
    # 交易数据
    orders: Optional[List[Dict[str, Any]]] = Field(default=None, description="交易订单")
    positions: Optional[List[Dict[str, Any]]] = Field(default=None, description="持仓记录")
    
    # Mercury结果
    mercury_results: Optional[Dict[str, Any]] = Field(default=None, description="Mercury回测结果")
    
    # 文件路径
    file_paths: Dict[str, Any] = Field(default_factory=dict, description="输出文件路径")
    
    # 数据质量
    data_quality: Dict[str, Any] = Field(default_factory=dict, description="数据质量报告")


class Role5ToRole2Payload(BaseModel):
    """
    Role5 发送给 Role2 的数据
    主要用于数据存储和缓存
    """
    payload_type: str = Field(default="backtest_result", description="载荷类型")
    
    # 回测结果
    backtest_output: Role5BacktestOutput = Field(..., description="回测输出")
    
    # 存储选项
    storage_options: Dict[str, Any] = Field(
        default_factory=lambda: {
            "save_to_database": True,
            "save_to_cache": True,
            "cache_ttl": 3600
        }
    )
    
    # 索引信息
    index_info: Dict[str, Any] = Field(
        default_factory=dict,
        description="用于检索的索引信息"
    )


class Role5ToRole6Payload(BaseModel):
    """
    Role5 发送给 Role6 的数据
    用于生成可视化和仪表板
    """
    payload_type: str = Field(default="visualization_request", description="载荷类型")
    
    # 回测结果
    backtest_output: Role5BacktestOutput = Field(..., description="回测输出")
    
    # 可视化选项
    visualization_options: Dict[str, Any] = Field(
        default_factory=lambda: {
            "generate_charts": True,
            "generate_dashboard": True,
            "generate_report": True,
            "theme": "default"
        }
    )
    
    # 输出配置
    output_config: Dict[str, Any] = Field(
        default_factory=lambda: {
            "output_dir": "./reports",
            "formats": ["html", "png"],
            "timestamp_in_filename": True
        }
    )


# ==================== 接口适配器 ====================

class RoleInterfaceAdapter:
    """
    角色接口适配器
    用于转换和验证角色间的数据交换
    """
    
    @staticmethod
    def create_role2_query(
        factor_id: str,
        start_date: str,
        end_date: str,
        stock_codes: Optional[List[str]] = None
    ) -> Role2DataRequest:
        """创建 Role2 数据查询"""
        return Role2DataRequest(
            request_id=f"req_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            data_type="market_data",
            fields=["open", "high", "low", "close", "volume"],
            start_date=start_date,
            end_date=end_date,
            stock_codes=stock_codes,
            frequency="daily"
        )
    
    @staticmethod
    def create_role6_viz_request(
        viz_type: VisualizationType,
        data: Dict[str, Any],
        output_path: Optional[str] = None
    ) -> Role6VisualizationRequest:
        """创建 Role6 可视化请求"""
        return Role6VisualizationRequest(
            request_id=f"viz_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            viz_type=viz_type,
            data=data,
            output_path=output_path
        )
    
    @staticmethod
    def create_role5_output(
        backtest_report: Dict[str, Any],
        factor_spec: Dict[str, Any]
    ) -> Role5BacktestOutput:
        """创建 Role5 输出"""
        return Role5BacktestOutput(
            output_id=f"out_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            factor_id=factor_spec.get("factor_id", "UNKNOWN"),
            factor_name=factor_spec.get("factor_name", "Unknown Factor"),
            factor_description=factor_spec.get("description"),
            backtest_config=backtest_report.get("config", {}),
            metrics=backtest_report.get("metrics", {}),
            ic_metrics=backtest_report.get("metrics", {}).get("ic_metrics", {}),
            layer_metrics=backtest_report.get("metrics", {}).get("layer_metrics", {}),
            long_short_metrics=backtest_report.get("metrics", {}).get("long_short_metrics", {}),
            chart_data=backtest_report.get("chart_data", {}),
            llm_explanation=backtest_report.get("explanation"),
            orders=backtest_report.get("orders"),
            mercury_results=backtest_report.get("mercury_results"),
            file_paths=backtest_report.get("file_paths", {})
        )
    
    @staticmethod
    def convert_to_role2_payload(
        backtest_output: Role5BacktestOutput
    ) -> Role5ToRole2Payload:
        """转换为 Role2 载荷"""
        return Role5ToRole2Payload(
            backtest_output=backtest_output,
            index_info={
                "factor_id": backtest_output.factor_id,
                "timestamp": backtest_output.timestamp,
                "backtest_period": backtest_output.backtest_config.get("period")
            }
        )
    
    @staticmethod
    def convert_to_role6_payload(
        backtest_output: Role5BacktestOutput,
        output_dir: str = "./reports"
    ) -> Role5ToRole6Payload:
        """转换为 Role6 载荷"""
        return Role5ToRole6Payload(
            backtest_output=backtest_output,
            output_config={
                "output_dir": output_dir,
                "formats": ["html", "png"],
                "timestamp_in_filename": True
            }
        )


# ==================== 便捷函数 ====================

def create_backtest_output_for_roles(
    factor_id: str,
    factor_name: str,
    metrics: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
    explanation: Optional[str] = None,
    file_paths: Optional[Dict[str, str]] = None
) -> Role5BacktestOutput:
    """
    便捷函数：创建回测输出
    
    Args:
        factor_id: 因子ID
        factor_name: 因子名称
        metrics: 回测指标
        config: 回测配置
        explanation: LLM解释
        file_paths: 输出文件路径
        
    Returns:
        Role5BacktestOutput
    """
    return Role5BacktestOutput(
        output_id=f"out_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        factor_id=factor_id,
        factor_name=factor_name,
        backtest_config=config or {},
        metrics=metrics,
        ic_metrics=metrics.get("ic_metrics", {}),
        layer_metrics=metrics.get("layer_metrics", {}),
        long_short_metrics=metrics.get("long_short_metrics", {}),
        llm_explanation=explanation,
        file_paths=file_paths or {}
    )


def prepare_role2_storage_payload(
    backtest_output: Role5BacktestOutput
) -> Dict[str, Any]:
    """
    准备 Role2 存储载荷
    
    Args:
        backtest_output: 回测输出
        
    Returns:
        存储载荷字典
    """
    adapter = RoleInterfaceAdapter()
    payload = adapter.convert_to_role2_payload(backtest_output)
    return payload.model_dump()


def prepare_role6_viz_payload(
    backtest_output: Role5BacktestOutput,
    output_dir: str = "./reports"
) -> Dict[str, Any]:
    """
    准备 Role6 可视化载荷
    
    Args:
        backtest_output: 回测输出
        output_dir: 输出目录
        
    Returns:
        可视化载荷字典
    """
    adapter = RoleInterfaceAdapter()
    payload = adapter.convert_to_role6_payload(backtest_output, output_dir)
    return payload.model_dump()
