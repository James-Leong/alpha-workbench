"""
Mercury 回测服务适配器
用于对接现有的 Mercury 回测服务 API
"""
import logging
import os
import time
from typing import Dict, Any, Optional
from datetime import datetime
import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MercuryConfig(BaseModel):
    """Mercury服务配置"""
    base_url: str = Field(
        default_factory=lambda: os.environ.get("MERCURY_BASE_URL", "http://quant.futuri.top"),
        description="服务地址",
    )
    timeout: int = Field(default=60, description="超时时间(秒)")
    retry_times: int = Field(default=3, description="重试次数")
    retry_delay: float = Field(default=1.0, description="重试间隔(秒)")
    api_token: Optional[str] = Field(
        default_factory=lambda: os.environ.get("MERCURY_API_TOKEN"),
        description="API认证令牌 (Bearer Token)",
    )
    headers: Optional[Dict[str, str]] = Field(default=None, description="自定义请求头")


class MercuryStrategyInput(BaseModel):
    """Mercury策略输入"""
    kind: str = Field(default="strategy", description="输入类型: strategy/order/transaction")
    name: str = Field(..., description="策略名称")
    language: str = Field(default="python-restricted", description="策略语言")
    version: int = Field(default=1, description="版本号")
    ops: list = Field(default_factory=list, description="操作列表")


class MercuryOrderInput(BaseModel):
    """Mercury订单输入"""
    kind: str = Field(default="order", description="输入类型")
    name: str = Field(..., description="订单名称")
    version: int = Field(default=1, description="版本号")
    time_in_force: str = Field(default="day", description="订单有效期")
    orders: list = Field(default_factory=list, description="订单列表")


class MercuryRunConfig(BaseModel):
    """Mercury回测运行配置"""
    start_date: str = Field(..., description="开始日期 (YYYYMMDD)")
    end_date: str = Field(..., description="结束日期 (YYYYMMDD)")
    initial_cash: float = Field(default=1000000.0, description="初始资金")
    transaction_cost_bps: float = Field(default=5.0, description="交易成本(基点)")


class MercuryRunSpec(BaseModel):
    """Mercury RunSpec"""
    run: MercuryRunConfig
    inputs: list = Field(default_factory=list)


class MercurySummary(BaseModel):
    """Mercury回测摘要"""
    start_date: str
    end_date: str
    trading_days: int = 0
    initial_unit_nav: float = 1.0
    final_unit_nav: float = 1.0
    total_asset: float = 0.0
    total_debt: float = 0.0
    total_return: float = 0.0
    annualized_return: float = 0.0
    annualized_volatility: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    total_turnover: float = 0.0
    total_trades: int = 0


class MercuryMetrics(BaseModel):
    """Mercury执行指标"""
    total_ms: int = 0
    build_requirement_ms: int = 0
    prepare_data_ms: int = 0
    load_execution_view_ms: int = 0
    cache_hit: bool = False
    connect_ms: int = 0
    resolve_assets_ms: int = 0
    load_bars_ms: int = 0
    source_fetch_count: int = 0
    prepare_partition_count: int = 0
    load_partition_count: int = 0
    cache_write_count: int = 0
    backtest_ms: int = 0
    persist_ms: int = 0


class MercuryBacktestResponse(BaseModel):
    """Mercury回测响应"""
    job_id: str
    status: str
    output_dir: str = ""
    run_spec: Optional[dict] = None
    execution_view: Optional[dict] = None
    summary: Optional[MercurySummary] = None
    metrics: Optional[MercuryMetrics] = None
    error: Optional[str] = None
    message: Optional[str] = None


class MercuryAdapter:
    """
    Mercury回测服务适配器
    
    用于对接 Mercury 回测服务的 HTTP API
    """
    
    def __init__(self, config: Optional[MercuryConfig] = None):
        """
        初始化适配器
        
        Args:
            config: Mercury服务配置
        """
        self.config = config or MercuryConfig()
        if self.config.api_token:
            self.config.api_token = self._normalize_token(self.config.api_token)
        
        # 构建默认请求头
        headers = {}
        
        # 添加API Token认证
        if self.config.api_token:
            headers["Authorization"] = f"Bearer {self.config.api_token}"
        
        # 添加自定义请求头
        if self.config.headers:
            headers.update(self.config.headers)
        
        self.client = httpx.Client(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            headers=headers if headers else None
        )
        has_token = bool(self.config.api_token)
        logger.info(
            "MercuryAdapter initialized (base_url=%s, auth=%s)",
            self.config.base_url, "yes" if has_token else "no",
        )

    @staticmethod
    def _normalize_token(raw_token: str) -> str:
        """兼容输入 'Authorization: Bearer xxx' / 'Bearer xxx' / 'xxx' 三种写法。"""
        token = raw_token.strip()
        lower = token.lower()
        if lower.startswith("authorization:"):
            token = token.split(":", 1)[1].strip()
            lower = token.lower()
        if lower.startswith("bearer "):
            token = token[7:].strip()
        return token
    
    def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            健康状态字典
        """
        try:
            response = self.client.get("/healthz")
            response.raise_for_status()
            result = response.json()
            logger.info("Mercury health check: %s", result.get("status", "ok"))
            return result
        except Exception as e:
            logger.warning("Mercury health check failed: %s", e)
            return {"status": "error", "message": str(e)}
    
    def ready_check(self) -> Dict[str, Any]:
        """
        就绪检查
        
        Returns:
            就绪状态字典
        """
        try:
            response = self.client.get("/readyz")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"status": "not_ready", "message": e.response.json().get("message", str(e))}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def create_backtest(self, run_spec: MercuryRunSpec) -> MercuryBacktestResponse:
        """
        创建回测任务
        
        Args:
            run_spec: 回测规格
            
        Returns:
            回测响应
        """
        try:
            response = self.client.post(
                "/api/v1/backtests",
                json=run_spec.model_dump(),
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            data = response.json()
            job_id = data.get("job_id", "")
            logger.info("Mercury backtest created: job_id=%s", job_id)
            
            return MercuryBacktestResponse(
                job_id=job_id,
                status=data.get("status", ""),
                output_dir=data.get("output_dir", ""),
                summary=MercurySummary(**data.get("summary", {})) if data.get("summary") else None,
                metrics=MercuryMetrics(**data.get("metrics", {})) if data.get("metrics") else None
            )
        except httpx.HTTPStatusError as e:
            logger.warning("Mercury backtest HTTP error: %s", e)
            try:
                error_data = e.response.json()
                return MercuryBacktestResponse(
                    job_id="",
                    status="error",
                    error=error_data.get("error", "unknown"),
                    message=error_data.get("message", str(e))
                )
            except:
                return MercuryBacktestResponse(
                    job_id="",
                    status="error",
                    error="http_error",
                    message=str(e)
                )
        except Exception as e:
            logger.error("Mercury backtest exception: %s", e)
            return MercuryBacktestResponse(
                job_id="",
                status="error",
                error="exception",
                message=str(e)
            )
    
    def get_backtest(self, job_id: str) -> MercuryBacktestResponse:
        """
        查询回测任务
        
        Args:
            job_id: 任务ID
            
        Returns:
            回测响应
        """
        try:
            response = self.client.get(f"/api/v1/backtests/{job_id}")
            response.raise_for_status()
            data = response.json()
            
            return MercuryBacktestResponse(
                job_id=data.get("job_id", ""),
                status=data.get("status", ""),
                output_dir=data.get("output_dir", ""),
                run_spec=data.get("run_spec"),
                execution_view=data.get("execution_view"),
                summary=MercurySummary(**data.get("summary", {})) if data.get("summary") else None,
                metrics=MercuryMetrics(**data.get("metrics", {})) if data.get("metrics") else None
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return MercuryBacktestResponse(
                    job_id=job_id,
                    status="not_found",
                    error="not_found",
                    message=f"Job not found: {job_id}"
                )
            try:
                error_data = e.response.json()
                return MercuryBacktestResponse(
                    job_id=job_id,
                    status="error",
                    error=error_data.get("error", "unknown"),
                    message=error_data.get("message", str(e))
                )
            except:
                return MercuryBacktestResponse(
                    job_id=job_id,
                    status="error",
                    error="http_error",
                    message=str(e)
                )
        except Exception as e:
            return MercuryBacktestResponse(
                job_id=job_id,
                status="error",
                error="exception",
                message=str(e)
            )
    
    def wait_for_completion(self, job_id: str, poll_interval: float = 1.0, max_wait: float = 300.0) -> MercuryBacktestResponse:
        """
        等待回测任务完成
        
        Args:
            job_id: 任务ID
            poll_interval: 轮询间隔(秒)
            max_wait: 最大等待时间(秒)
            
        Returns:
            最终回测响应
        """
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            response = self.get_backtest(job_id)
            
            if response.status in ["completed", "error", "not_found"]:
                return response
            
            time.sleep(poll_interval)
        
        return MercuryBacktestResponse(
            job_id=job_id,
            status="timeout",
            error="timeout",
            message=f"Wait timeout after {max_wait} seconds"
        )
    
    def create_and_wait(self, run_spec: MercuryRunSpec, poll_interval: float = 1.0, max_wait: float = 300.0) -> MercuryBacktestResponse:
        """
        创建并等待回测任务完成
        
        Args:
            run_spec: 回测规格
            poll_interval: 轮询间隔(秒)
            max_wait: 最大等待时间(秒)
            
        Returns:
            最终回测响应
        """
        response = self.create_backtest(run_spec)
        
        if response.error:
            logger.warning("Mercury create_and_wait failed: %s", response.message)
            return response
        
        logger.info("Mercury waiting for job %s to complete...", response.job_id)
        return self.wait_for_completion(response.job_id, poll_interval, max_wait)
    
    def close(self):
        """关闭客户端"""
        self.client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def create_mercury_adapter(
    base_url: str = "",
    api_token: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None
) -> MercuryAdapter:
    """
    创建Mercury适配器

    Args:
        base_url: 服务地址（默认从 MERCURY_BASE_URL 环境变量读取，fallback http://quant.futuri.top）
        api_token: API认证令牌 (Bearer Token)
        headers: 自定义请求头
        
    Returns:
        MercuryAdapter实例
        
    示例:
        # 使用API Token认证
        adapter = create_mercury_adapter(
            base_url="http://quant.futuri.top",
            api_token="YOUR_MERCURY_API_TOKEN"
        )
        
        # 使用自定义请求头
        adapter = create_mercury_adapter(
            base_url="http://quant.futuri.top",
            headers={"Authorization": "Bearer YOUR_MERCURY_API_TOKEN"}
        )
    """
    config = MercuryConfig(
        api_token=api_token,
        headers=headers
    )
    if base_url:
        config.base_url = base_url
    return MercuryAdapter(config)
