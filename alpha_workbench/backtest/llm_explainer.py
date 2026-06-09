"""
Backtest Explainer for AlphaWorkbench Role 5
使用 DeepSeek V3.2 (华为云 MaaS) 对回测结果进行解释

配置方法:
1. 创建 .env 文件在项目根目录，包含 DEEPSEEK_API_KEY
2. 或在初始化时传入 api_key 参数

华为云 MaaS API V2:
- API地址: https://api.modelarts-maas.com/v2/chat/completions
- 鉴权: Bearer Token
- 支持地域: 西南-贵阳一
"""
import logging
import os
import re
import threading
import warnings
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# 抑制 urllib3 的 SSL 警告（华为云官方示例使用 verify=False）
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

from alpha_workbench.schemas.backtest_schemas import (
    BacktestMetrics,
    FactorSpec,
    ICMetrics,
    LayerMetrics,
    LongShortMetrics,
    BacktestExplanationResult
)

# 尝试加载 .env 文件
try:
    from dotenv import load_dotenv
    # 加载项目根目录的 .env 文件
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv 未安装


class BacktestExplainer:
    """
    回测结果解释器

    使用DeepSeek API对回测指标进行专业解释
    返回结构化的BacktestExplanationResult对象，包含is_fallback标志
    """
    
    # 解释Prompt模板
    SYSTEM_PROMPT = """你是一位专业的量化因子研究员，擅长分析因子回测结果。

你的任务是根据提供的回测指标，生成专业、客观、有洞察力的分析报告。

分析维度包括：
1. IC指标（Pearson IC和Rank IC）：评估因子的预测能力
2. 稳定性分析：评估因子预测的可靠性和一致性
3. 分层收益：检验因子的单调性和区分度
4. 多空收益：评估实际交易策略表现
5. 换手率：评估策略的可执行性和交易成本
6. 风险指标：识别潜在风险和回撤

评价标准：
- IC/RankIC均值：|IC| > 0.03 为有效，|IC| > 0.05 为优秀
- ICIR：> 0.5 为稳定，> 1.0 为非常稳定
- IC为正比例：> 50% 表示方向稳定，> 60% 表示方向非常稳定
- t统计量：|t| > 2 表示统计显著，|t| > 3 表示高度显著
- 夏普比率：> 1.0 为优秀，0.5-1.0 为良好，< 0.5 为较差
- 最大回撤：> -20% 为可控，< -30% 为高风险
- 换手率：< 50% 为低换手，50%-100% 为中等，> 100% 为高换手

请用中文回答，语言专业但易懂，给出具体的数据支持和可操作的建议。

特别注意：
- 稳定性分析要结合IC为正比例和t统计量，判断因子是否具有统计显著性
- 如果IC为正比例接近50%，说明因子方向不稳定，即使IC均值较高也可能不可靠
- t统计量可以判断IC均值是否显著异于0，避免随机波动造成的假阳性"""

    USER_PROMPT_TEMPLATE = """请分析以下因子回测结果：

## 因子信息
- 因子名称: {factor_name}
- 因子ID: {factor_id}
- 因子描述: {factor_description}
- 回测区间: {backtest_period}

## IC指标与稳定性
- IC均值: {ic_mean:.4f}, ICIR: {icir:.4f}
- IC为正比例: {ic_positive_ratio:.1%}, t统计量: {ic_tstat:.2f}
- RankIC均值: {rank_ic_mean:.4f}, RankICIR: {rank_icir:.4f}
- RankIC为正比例: {rank_ic_positive_ratio:.1%}, t统计量: {rank_ic_tstat:.2f}

## 分层收益
{layer_returns}

## 多空组合
- 年化收益: {ls_annual_return:.2%}, 夏普: {ls_sharpe:.2f}, 最大回撤: {ls_max_dd:.2%}
{turnover_info}

请生成分析报告，包括：
1. 总体评价：因子整体表现，是否达到实盘标准
2. IC分析：预测能力和统计显著性（结合t统计量）
3. 稳定性分析：方向稳定性（IC为正比例）和统计可靠性（t统计量）
4. 分层分析：单调性和区分度
5. 多空分析：收益风险特征
6. 风险评估：主要风险点
7. 改进建议：具体可操作的优化方向

要求：
- 专业客观，有数据支持
- 稳定性分析必须结合IC为正比例和t统计量
- 如果IC为正比例接近50%或|t|<2，要明确指出因子不可靠
- 建议具体可操作"""

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None, base_url: Optional[str] = None, force_mock: bool = False):
        """
        初始化解释器

        Args:
            model: LLM模型名称，默认 DeepSeek-V3
            api_key: DeepSeek API Key，如不提供则从环境变量 DEEPSEEK_API_KEY 读取
            base_url: API基础URL，默认华为云 MaaS
            force_mock: 强制使用mock模式，不调用API
        """
        self.model = model or os.environ.get('DEEPSEEK_MODEL', 'DeepSeek-V3')
        self.api_key = api_key or os.environ.get('DEEPSEEK_API_KEY')
        self.base_url = base_url or os.environ.get('DEEPSEEK_BASE_URL', 'https://api.modelarts-maas.com/v2')
        self.agent = None
        self.force_mock = force_mock

        # 如果强制使用mock模式，跳过初始化
        if self.force_mock:
            logger.info("强制使用mock模式（跳过API初始化）")
            return

        # 尝试初始化 DeepSeek Agent
        if self.api_key:
            try:
                self._init_deepseek_agent()
            except Exception as e:
                logger.warning("初始化 DeepSeek Agent 失败: %s", e)
                logger.info("将使用mock模式")
        else:
            logger.warning("未设置 DEEPSEEK_API_KEY，将使用mock模式")
            logger.info("请在 .env 文件中配置 DEEPSEEK_API_KEY")
    
    def _init_deepseek_agent(self):
        """初始化 DeepSeek Agent (华为云 MaaS)

        使用 requests 库直接调用，符合华为云 MaaS API 范式
        """
        try:
            import requests

            # 确保 base_url 是完整的 endpoint 路径
            base_url = self.base_url
            # 修复: 正确处理已包含 /chat/completions 的 URL
            if '/chat/completions' in base_url:
                # URL 已经包含完整路径，直接使用
                self.api_url = base_url
            else:
                # 需要添加 /chat/completions
                if not base_url.endswith('/'):
                    base_url += '/'
                self.api_url = base_url + 'chat/completions'

            self.model_id = self.model

            # 设置请求头（符合华为云 MaaS 鉴权方式）
            self.api_headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}'
            }

            logger.info("DeepSeek Agent 初始化成功 (模型: %s)", self.model)
            logger.debug("  API地址: %s", self.api_url)
        except ImportError:
            logger.warning("未安装 requests 库，将使用mock模式")
            logger.info("请运行: pip install requests")
        except Exception as e:
            logger.warning("初始化 DeepSeek Agent 失败: %s", e)
            logger.info("将使用mock模式")
    
    def explain(
        self,
        metrics: BacktestMetrics,
        factor_spec: FactorSpec,
        backtest_period: str = "Unknown",
        use_mock: bool = False,
        save_json: bool = True,
        output_dir: str = "runs/reports"
    ) -> BacktestExplanationResult:
        """
        生成回测解释

        Args:
            metrics: 回测指标
            factor_spec: 因子规格
            backtest_period: 回测区间
            use_mock: 是否强制使用mock模式（跳过API调用）
            save_json: 是否保存为JSON文件（默认True，供Role 2/6使用）
            output_dir: JSON文件输出目录

        Returns:
            BacktestExplanationResult: 结构化解释结果，包含is_fallback标志
        """
        # 如果强制使用mock模式，直接返回mock结果
        if use_mock or self.force_mock:
            logger.info("使用mock模式生成解释（跳过API调用）")
            result = self._explain_mock(metrics, factor_spec, backtest_period)
        # 检查是否已初始化 API（检查 api_url 和 api_headers）
        elif hasattr(self, 'api_url') and hasattr(self, 'api_headers'):
            result = self._explain_with_openai(metrics, factor_spec, backtest_period)
        else:
            logger.info("API 未初始化，使用mock模式生成解释")
            result = self._explain_mock(metrics, factor_spec, backtest_period)
        
        # 保存为JSON文件（供Role 2/6使用）
        if save_json:
            self._save_explanation_to_json(result, factor_spec, output_dir)
        
        return result
    
    def _save_explanation_to_json(
        self,
        result: BacktestExplanationResult,
        factor_spec: FactorSpec,
        output_dir: str = "runs/reports"
    ) -> str:
        """
        将LLM解释结果保存为JSON文件
        
        Args:
            result: LLM解释结果
            factor_spec: 因子规格
            output_dir: 输出目录
            
        Returns:
            保存的文件路径
        """
        import json
        from datetime import datetime
        from pathlib import Path
        
        # 创建输出目录
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 构建文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        factor_id = factor_spec.factor_id if factor_spec.factor_id else "unknown"
        filename = f"llm_explanation_{factor_id}_{timestamp}.json"
        filepath = output_path / filename
        
        # 构建完整的JSON数据（包含元数据，方便Role 2/6使用）
        json_data = {
            "metadata": {
                "version": "1.0.0",
                "generated_at": datetime.now().isoformat(),
                "factor_id": factor_spec.factor_id,
                "factor_name": factor_spec.factor_name,
                "source": "Role 5 - Backtest Explainer",
                "target_audience": ["Role 2 - UI", "Role 6 - Audit & Report"],
                "is_fallback": result.is_fallback
            },
            "explanation": result.to_dict(),
            "factor_spec": {
                "factor_id": factor_spec.factor_id,
                "factor_name": factor_spec.factor_name,
                "description": factor_spec.description,
                "formula_latex": factor_spec.formula_latex if hasattr(factor_spec, 'formula_latex') else None
            }
        }
        
        # 保存JSON文件
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        
        logger.info("LLM解释已保存: %s", filepath)
        return str(filepath)
    
    def _call_api_with_timeout(self, user_prompt: str, timeout: Optional[int] = 120, max_retries: int = 2, stream: bool = True) -> Optional[str]:
        """带重试的 API 调用（使用 requests 库，符合华为云 MaaS 范式）

        Args:
            user_prompt: 用户提示词
            timeout: 超时时间（秒），默认120秒
            max_retries: 最大重试次数，默认2次
            stream: 是否使用流式响应，默认True

        Returns:
            API 响应内容，失败返回 None
        """
        import json
        import requests
        import time

        # 构建请求体（符合华为云 MaaS API 范式）
        payload = {
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "stream": stream,
            "model": self.model_id,
            "max_tokens": 1500
        }

        for attempt in range(max_retries + 1):
            if attempt > 0:
                logger.info("第 %d/%d 次尝试...", attempt + 1, max_retries + 1)
                time.sleep(2)  # 重试前等待2秒

            try:
                # 打印调试信息
                logger.debug("请求 URL: %s", self.api_url)
                logger.debug("请求模型: %s", self.model_id)
                logger.debug("请求体大小: %d 字节", len(json.dumps(payload)))
                logger.debug("超时设置: %d秒", timeout)
                logger.debug("流式响应: %s", "开启" if stream else "关闭")
                
                # 根据华为云官方文档，使用 data=json.dumps() 而不是 json=
                # 并添加 verify=False 跳过 SSL 验证（官方示例）
                request_kwargs = {
                    'headers': self.api_headers,
                    'data': json.dumps(payload),  # 华为云官方要求
                    'verify': False,  # 华为云官方示例使用
                    'timeout': (10, timeout),  # (连接超时, 读取超时)
                    'stream': stream  # 流式响应需要开启 requests 的 stream 参数
                }
                
                response = requests.post(self.api_url, **request_kwargs)
                
                # 打印响应状态
                logger.debug("响应状态码: %d", response.status_code)
                
                response.raise_for_status()
                
                # 处理流式响应
                if stream:
                    return self._handle_streaming_response(response)
                else:
                    # 非流式响应处理
                    data = response.json()
                    logger.debug("响应内容: %s...", json.dumps(data, ensure_ascii=False, indent=2)[:300])
                    
                    # 解析响应内容
                    if "choices" in data and len(data["choices"]) > 0:
                        return data["choices"][0]["message"]["content"]
                    else:
                        raise Exception(f"API 响应格式异常: {data}")
                    
            except requests.exceptions.Timeout:
                timeout_msg = f"（>{timeout}秒）"
                logger.warning("API 调用超时%s", timeout_msg)
                if attempt < max_retries:
                    continue  # 继续重试
                return None
            except requests.exceptions.ConnectionError as e:
                logger.warning("连接错误: %s", e)
                if attempt < max_retries:
                    continue
                raise Exception(f"连接错误: {e}")
            except requests.exceptions.RequestException as e:
                error_msg = f"API 请求错误: {e}"
                # 打印更详细的错误信息
                if hasattr(e.response, 'status_code'):
                    logger.debug("错误状态码: %d", e.response.status_code)
                if hasattr(e.response, 'text'):
                    logger.debug("错误响应: %s", e.response.text[:500])
                raise Exception(error_msg)
            except Exception as e:
                raise Exception(f"请求异常: {e}")

        return None

    def _handle_streaming_response(self, response) -> str:
        """处理流式响应

        Args:
            response: requests Response 对象

        Returns:
            拼接后的完整响应内容
        """
        import json
        
        full_content = []
        logger.debug("LLM streaming start")  # 开始输出标记
        
        for line in response.iter_lines():
            if not line:
                continue
            
            line_str = line.decode('utf-8')
            
            # SSE 格式以 "data: " 开头
            if line_str.startswith('data: '):
                data_str = line_str[6:]  # 去掉 "data: " 前缀
                
                # 流结束标记
                if data_str.strip() == '[DONE]':
                    break
                
                try:
                    data = json.loads(data_str)
                    
                    # 提取 delta 内容
                    if "choices" in data and len(data["choices"]) > 0:
                        choice = data["choices"][0]
                        if "delta" in choice and "content" in choice["delta"]:
                            content = choice["delta"]["content"]
                            full_content.append(content)
                            logger.debug("LLM chunk received (len=%d)", len(content))
                        elif "message" in choice and "content" in choice["message"]:
                            # 某些 API 可能直接返回完整消息
                            content = choice["message"]["content"]
                            full_content.append(content)
                            logger.debug("LLM chunk received (len=%d)", len(content))
                except json.JSONDecodeError:
                    continue  # 忽略无法解析的行
        
        logger.debug("LLM streaming complete (total chars=%d)", len("".join(full_content)))
        return "".join(full_content)

    def _explain_with_openai(
        self,
        metrics: BacktestMetrics,
        factor_spec: FactorSpec,
        backtest_period: str
    ) -> BacktestExplanationResult:
        """使用 OpenAI 客户端生成解释（华为云 MaaS）"""
        # 构建prompt - 只包含关键指标，减少请求体大小
        layer_returns_str = "\n".join([
            f"- {layer}: {ret:.2%}"
            for layer, ret in metrics.layer_metrics.layer_returns.items()
        ])

        # 简化换手率信息
        turnover_info = ""
        if metrics.long_short_metrics.turnover:
            to = metrics.long_short_metrics.turnover
            turnover_info = f"- 换手率: 平均{to.mean_turnover:.1%}, 最大{to.max_turnover:.1%}"

        user_prompt = self.USER_PROMPT_TEMPLATE.format(
            factor_name=factor_spec.factor_name,
            factor_id=factor_spec.factor_id,
            factor_description=factor_spec.description or "N/A",
            backtest_period=backtest_period,
            # IC 指标
            ic_mean=metrics.ic_metrics.ic_mean,
            icir=metrics.ic_metrics.icir,
            # 稳定性指标（新增）
            ic_positive_ratio=metrics.ic_metrics.ic_positive_ratio,
            ic_tstat=metrics.ic_metrics.ic_tstat,
            rank_ic_mean=metrics.ic_metrics.rank_ic_mean,
            rank_icir=metrics.ic_metrics.rank_icir,
            rank_ic_positive_ratio=metrics.ic_metrics.rank_ic_positive_ratio,
            rank_ic_tstat=metrics.ic_metrics.rank_ic_tstat,
            layer_returns=layer_returns_str,
            ls_annual_return=metrics.long_short_metrics.annual_return,
            ls_sharpe=metrics.long_short_metrics.sharpe_ratio,
            ls_max_dd=metrics.long_short_metrics.max_drawdown,
            turnover_info=turnover_info
        )

        try:
            # 使用 OpenAI 客户端直接调用
            import time
            logger.info("正在调用 DeepSeek API 生成分析...")
            logger.info("  模型: %s", self.model_id)
            logger.info("  超时: 120秒 (含2次重试)")
            logger.info("  流式响应: 已开启")
            logger.info("  Prompt大小: %d 字符", len(user_prompt))
            start_time = time.time()

            # 使用流式响应的 API 调用（timeout=120秒，2次重试）
            raw_explanation = self._call_api_with_timeout(user_prompt, timeout=120, max_retries=2, stream=True)

            if raw_explanation is None:
                logger.warning("API 调用超时，将使用 mock 模式生成解释...")
                return self._explain_mock(metrics, factor_spec, backtest_period)

            elapsed = time.time() - start_time
            logger.info("API 调用完成 (耗时 %.1fs)", elapsed)

            return self._parse_explanation_to_structured(raw_explanation, is_fallback=False)

        except Exception as e:
            error_msg = str(e)
            logger.warning("OpenAI API调用失败: %s", error_msg)

            # 判断错误类型
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                logger.warning("API调用超时，将使用 mock 模式生成解释...")
            elif "connection" in error_msg.lower():
                logger.warning("网络连接错误，将使用 mock 模式生成解释...")
            elif "rate limit" in error_msg.lower():
                logger.warning("API速率限制，将使用 mock 模式生成解释...")
            else:
                logger.warning("将使用 mock 模式生成解释...")

            return self._explain_mock(metrics, factor_spec, backtest_period)
    
    def _explain_mock(
        self,
        metrics: BacktestMetrics,
        factor_spec: FactorSpec,
        backtest_period: str
    ) -> BacktestExplanationResult:
        """
        Mock解释模式（当Agent不可用时使用）

        基于规则生成结构化解释
        """
        ic = metrics.ic_metrics
        ls = metrics.long_short_metrics
        layer_returns = metrics.layer_metrics.layer_returns
        sorted_layers = sorted(layer_returns.items(), key=lambda x: x[1], reverse=True)

        # 总体评价
        if abs(ic.ic_mean) > 0.05 and ic.icir > 0.5 and ls.sharpe_ratio > 1.0:
            summary = f"因子【{factor_spec.factor_name}】整体表现优秀，IC均值为{ic.ic_mean:.4f}，夏普比率为{ls.sharpe_ratio:.2f}，达到实盘标准。"
        elif abs(ic.ic_mean) > 0.02 and ls.sharpe_ratio > 0.5:
            summary = f"因子【{factor_spec.factor_name}】表现良好，具有一定预测能力，但建议进一步优化后再考虑实盘。"
        else:
            summary = f"因子【{factor_spec.factor_name}】表现一般，IC均值为{ic.ic_mean:.4f}，需要进一步改进。"

        # IC指标分析
        ic_lines = []
        ic_lines.append(f"**Pearson IC**: 均值{ic.ic_mean:.4f}，ICIR{ic.icir:.2f}")
        if abs(ic.ic_mean) > 0.05 and ic.icir > 0.5:
            ic_lines.append("线性预测能力较强。")
        elif abs(ic.ic_mean) > 0.02:
            ic_lines.append("具有一定线性预测能力，但稳定性有待提升。")
        else:
            ic_lines.append("线性预测能力较弱。")

        ic_lines.append(f"**Rank IC**: 均值{ic.rank_ic_mean:.4f}，RankICIR{ic.rank_icir:.2f}")
        if abs(ic.rank_ic_mean) > 0.05 and ic.rank_icir > 0.5:
            ic_lines.append("排序预测能力较强。")
        elif abs(ic.rank_ic_mean) > 0.02:
            ic_lines.append("具有一定排序预测能力。")
        else:
            ic_lines.append("排序预测能力较弱。")

        ic_diff = abs(ic.ic_mean - ic.rank_ic_mean)
        if ic_diff > 0.01:
            ic_lines.append(f"Pearson IC与Rank IC差异为{ic_diff:.4f}，")
            if abs(ic.ic_mean) < abs(ic.rank_ic_mean):
                ic_lines.append("说明因子对异常值较敏感。")
            else:
                ic_lines.append("说明因子线性关系较强。")

        ic_sign = "正" if ic.ic_mean > 0 else "负"
        ic_lines.append(f"IC为正比例{ic.ic_positive_ratio:.1%}，因子与收益呈{ic_sign}相关。")
        ic_analysis = "\n".join(ic_lines)

        # 分层收益分析
        layer_lines = []
        if len(sorted_layers) >= 2:
            top_layer = sorted_layers[0]
            bottom_layer = sorted_layers[-1]
            spread = top_layer[1] - bottom_layer[1]

            if spread > 0.1:
                layer_lines.append(f"分层效果良好，最高层({top_layer[0]})年化收益{top_layer[1]:.2%}，")
                layer_lines.append(f"最低层({bottom_layer[0]})年化收益{bottom_layer[1]:.2%}，")
                layer_lines.append(f"层间差异{spread:.2%}，单调性良好。")
            else:
                layer_lines.append(f"分层效果一般，层间差异为{spread:.2%}，单调性不够明显。")
        layer_analysis = "\n".join(layer_lines)

        # 多空组合分析
        ls_lines = []
        ls_lines.append(f"年化收益{ls.annual_return:.2%}，年化波动{ls.annual_volatility:.2%}，")
        ls_lines.append(f"夏普比率{ls.sharpe_ratio:.4f}，最大回撤{ls.max_drawdown:.2%}。")

        if ls.sharpe_ratio > 1.0:
            ls_lines.append("夏普比率大于1，风险调整后收益优秀。")
        elif ls.sharpe_ratio > 0.5:
            ls_lines.append("夏普比率在0.5-1之间，风险调整后收益一般。")
        else:
            ls_lines.append("夏普比率较低，风险调整后收益不佳。")

        if abs(ls.max_drawdown) > 0.2:
            ls_lines.append(f"最大回撤达到{ls.max_drawdown:.2%}，需注意风险控制。")
        long_short_analysis = "\n".join(ls_lines)

        # 换手率分析
        turnover_lines = []
        if ls.turnover:
            turnover_lines.append(f"平均换手率{ls.turnover.mean_turnover:.2%}，最大换手率{ls.turnover.max_turnover:.2%}。")
            if ls.turnover.mean_turnover < 0.5:
                turnover_lines.append("换手率较低，策略可执行性好。")
            elif ls.turnover.mean_turnover < 1.0:
                turnover_lines.append("换手率中等，需关注交易成本。")
            else:
                turnover_lines.append("换手率较高，交易成本可能侵蚀收益。")
        turnover_analysis = "\n".join(turnover_lines) if turnover_lines else "未提供换手率数据。"

        # 风险评估
        risks = []
        if ic.icir < 0.3 and ic.rank_icir < 0.3:
            risks.append("IC稳定性不足")
        if abs(ls.max_drawdown) > 0.2:
            risks.append("回撤较大")
        if ls.sharpe_ratio < 0.5:
            risks.append("夏普比率偏低")
        if ls.turnover and ls.turnover.mean_turnover > 1.0:
            risks.append("换手率过高")

        if risks:
            risk_assessment = f"主要风险: {', '.join(risks)}"
        else:
            risk_assessment = "整体风险可控"

        # 改进建议
        suggestions = []
        if ic.icir < 0.5 and ic.rank_icir < 0.5:
            suggestions.append("考虑增加因子稳定性，如使用移动平均平滑或去极值处理")
        if abs(ls.max_drawdown) > 0.2:
            suggestions.append("建议加入止损机制或仓位控制")
        if len(sorted_layers) >= 2:
            spread = sorted_layers[0][1] - sorted_layers[-1][1]
            if spread < 0.05:
                suggestions.append("因子区分度不足，可考虑与其他因子组合")
        if ls.turnover and ls.turnover.mean_turnover > 1.0:
            suggestions.append("换手率过高，建议延长调仓周期或增加持仓数量")

        if suggestions:
            recommendations = "\n".join([f"{i}. {s}" for i, s in enumerate(suggestions, 1)])
        else:
            recommendations = "因子表现良好，可考虑实盘测试。"

        # 创建结果对象
        result = BacktestExplanationResult(
            summary=summary,
            ic_analysis=ic_analysis,
            layer_analysis=layer_analysis,
            long_short_analysis=long_short_analysis,
            turnover_analysis=turnover_analysis,
            risk_assessment=risk_assessment,
            recommendations=recommendations,
            is_fallback=True,
            raw_llm_output=None
        )

        # 添加生成元数据
        result.add_generation_metadata("mode", "mock")
        result.add_generation_metadata("model", self.model or "unknown")
        result.add_generation_metadata("timestamp", datetime.now().isoformat())

        # 验证完整性
        validation = result.validate_completeness()
        if not validation["is_complete"]:
            for field in validation["missing_fields"]:
                result.add_validation_error(f"Mock模式下字段 '{field}' 生成不完整")

        return result
    
    def _parse_explanation_to_structured(
        self,
        raw_explanation: str,
        is_fallback: bool = False
    ) -> BacktestExplanationResult:
        """
        将LLM原始输出解析为结构化格式

        尝试从LLM返回的文本中提取各个部分，如果解析失败则使用启发式方法
        """
        # 初始化默认值
        summary = ""
        ic_analysis = ""
        layer_analysis = ""
        long_short_analysis = ""
        turnover_analysis = ""
        risk_assessment = ""
        recommendations = ""

        try:
            # 尝试按章节解析。LLM 对标题措辞不稳定，例如可能输出
            # “IC分析”而不是 prompt 中的“IC指标分析”，这里统一做别名匹配。
            section_aliases = {
                "summary": ["总体评价", "整体评价", "综合评价"],
                "ic_analysis": ["IC分析", "IC指标分析", "IC 指标分析", "IC与稳定性分析", "预测能力分析"],
                "layer_analysis": ["分层分析", "分层收益分析", "分层效果分析"],
                "long_short_analysis": ["多空分析", "多空组合分析", "多空收益分析"],
                "turnover_analysis": ["换手率分析", "交易成本分析"],
                "risk_assessment": ["风险评估", "风险分析"],
                "recommendations": ["改进建议", "优化建议", "建议"],
            }
            normalized_aliases = {
                en_name: [_normalize_section_heading(alias) for alias in aliases]
                for en_name, aliases in section_aliases.items()
            }

            current_section = None
            section_content = []

            for line in raw_explanation.split('\n'):
                line_stripped = line.strip()

                # 检测章节标题
                is_section_header = False
                normalized_heading = _normalize_section_heading(line_stripped)
                for en_name, aliases in normalized_aliases.items():
                    if (
                        ("##" in line or "###" in line or line_stripped[:2].isdigit())
                        and any(alias in normalized_heading for alias in aliases)
                    ) or any(normalized_heading.startswith(alias) for alias in aliases):
                        # 保存上一个章节的内容
                        if current_section and section_content:
                            content = '\n'.join(section_content).strip()
                            if current_section == "summary":
                                summary = content
                            elif current_section == "ic_analysis":
                                ic_analysis = content
                            elif current_section == "layer_analysis":
                                layer_analysis = content
                            elif current_section == "long_short_analysis":
                                long_short_analysis = content
                            elif current_section == "turnover_analysis":
                                turnover_analysis = content
                            elif current_section == "risk_assessment":
                                risk_assessment = content
                            elif current_section == "recommendations":
                                recommendations = content

                        current_section = en_name
                        inline_content = _extract_inline_section_content(
                            line_stripped,
                            section_aliases[en_name],
                        )
                        section_content = [inline_content] if inline_content else []
                        is_section_header = True
                        break

                if not is_section_header and current_section:
                    section_content.append(line)

            # 保存最后一个章节
            if current_section and section_content:
                content = '\n'.join(section_content).strip()
                if current_section == "summary":
                    summary = content
                elif current_section == "ic_analysis":
                    ic_analysis = content
                elif current_section == "layer_analysis":
                    layer_analysis = content
                elif current_section == "long_short_analysis":
                    long_short_analysis = content
                elif current_section == "turnover_analysis":
                    turnover_analysis = content
                elif current_section == "risk_assessment":
                    risk_assessment = content
                elif current_section == "recommendations":
                    recommendations = content

            # 如果没有解析出任何内容，将整个文本作为summary
            if not any([summary, ic_analysis, layer_analysis, long_short_analysis, risk_assessment, recommendations]):
                summary = raw_explanation[:500] + "..." if len(raw_explanation) > 500 else raw_explanation

        except Exception as e:
            # 解析失败时使用原始文本
            summary = f"解析LLM输出时出错: {e}"
            ic_analysis = raw_explanation[:1000] if len(raw_explanation) > 1000 else raw_explanation

        # 创建结果对象
        result = BacktestExplanationResult(
            summary=summary or "未生成总体评价",
            ic_analysis=ic_analysis or "未生成IC分析",
            layer_analysis=layer_analysis or "未生成分层分析",
            long_short_analysis=long_short_analysis or "未生成多空分析",
            turnover_analysis=turnover_analysis or "未生成换手率分析",
            risk_assessment=risk_assessment or "未生成风险评估",
            recommendations=recommendations or "未生成改进建议",
            is_fallback=is_fallback,
            raw_llm_output=raw_explanation if not is_fallback else None
        )

        # 添加生成元数据
        result.add_generation_metadata("mode", "api" if not is_fallback else "fallback")
        result.add_generation_metadata("model", self.model or "unknown")
        result.add_generation_metadata("timestamp", datetime.now().isoformat())

        # 验证完整性并记录缺失字段
        validation = result.validate_completeness()
        if not validation["is_complete"]:
            for field in validation["missing_fields"]:
                result.add_validation_error(f"LLM输出缺少字段 '{field}'")

        # 如果有警告也记录下来
        for warning in validation["warnings"]:
            result.add_generation_metadata("warning", warning)

        return result


def _normalize_section_heading(value: str) -> str:
    """Normalize LLM section headings for robust alias matching."""
    heading = re.sub(r"^[#\s\d.、:：()-]+", "", value.strip(), flags=re.ASCII)
    heading = re.sub(r"[\s:：#*_\-—/（）()]+", "", heading)
    return heading.upper()


def _extract_inline_section_content(line: str, aliases: list[str]) -> str:
    """Return content after a same-line section heading, if present."""
    content = re.sub(r"^[#\s\d.、:：()-]+", "", line.strip(), flags=re.ASCII).strip()
    for alias in aliases:
        alias_pattern = r"\s*".join(re.escape(char) for char in alias.replace(" ", ""))
        match = re.match(rf"^{alias_pattern}\s*[:：-]?\s*(.*)$", content, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""

    def _format_explanation_to_text(self, result: BacktestExplanationResult, include_metadata: bool = True) -> str:
        """将结构化解释格式化为文本输出（用于兼容旧代码）

        Args:
            result: BacktestExplanationResult对象
            include_metadata: 是否包含元数据信息
        """
        lines = [
            "## 回测结果分析",
            "",
            "### 总体评价",
            result.summary,
            "",
            "### IC指标分析",
            result.ic_analysis,
            "",
            "### 分层收益分析",
            result.layer_analysis,
            "",
            "### 多空组合分析",
            result.long_short_analysis,
            "",
        ]

        if result.turnover_analysis:
            lines.extend([
                "### 换手率分析",
                result.turnover_analysis,
                "",
            ])

        lines.extend([
            "### 风险评估",
            result.risk_assessment,
            "",
            "### 改进建议",
            result.recommendations,
            "",
        ])

        # 添加元数据信息
        if include_metadata:
            lines.extend([
                "---",
                "**元数据信息**:",
                f"- is_fallback: {result.is_fallback}",
                f"- quality_score: {result.get_quality_score()}",
            ])

            if result.missing_fields:
                lines.append(f"- missing_fields: {', '.join(result.missing_fields)}")

            if result.validation_errors:
                lines.append("- validation_errors:")
                for error in result.validation_errors:
                    lines.append(f"  - {error}")

            if result.generation_metadata:
                lines.append("- generation_metadata:")
                for key, value in result.generation_metadata.items():
                    lines.append(f"  - {key}: {value}")

        return "\n".join(lines)


# 便捷函数
def create_explainer(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    force_mock: bool = False
) -> BacktestExplainer:
    """
    创建回测解释器 (DeepSeek V3.2)

    Args:
        model: LLM模型名称，默认 DeepSeek-V3
        api_key: DeepSeek API Key，如不提供则从环境变量 DEEPSEEK_API_KEY 读取
        base_url: API基础URL，默认华为云 MaaS
        force_mock: 强制使用mock模式，不调用API

    Returns:
        BacktestExplainer实例

    示例:
        # 方法1: 使用 .env 文件 (推荐)
        # 在项目根目录创建 .env 文件，包含:
        # DEEPSEEK_API_KEY=your-key
        # DEEPSEEK_MODEL=DeepSeek-V3
        explainer = create_explainer()

        # 方法2: 直接传入 API Key
        explainer = create_explainer(api_key="your-deepseek-key")

        # 方法3: 指定完整配置
        explainer = create_explainer(
            model="DeepSeek-V3",
            api_key="your-key",
            base_url="https://api.modelarts-maas.com/v2"
        )

        # 方法4: 强制使用mock模式（跳过API调用）
        explainer = create_explainer(force_mock=True)
    """
    return BacktestExplainer(model=model, api_key=api_key, base_url=base_url, force_mock=force_mock)
