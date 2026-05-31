"""
Backtest Plotter for AlphaWorkbench Role 5
使用Plotly生成交互式回测图表
"""
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Optional, List
import json


class BacktestPlotter:
    """
    回测图表绘制器
    
    生成以下图表：
    1. IC序列图
    2. 分层累计收益图
    3. 多空净值曲线图
    4. IC分布图
    5. IC月度热力图
    
    特性：
    - 增强的悬停提示，显示详细数值
    - 图表联动，支持同步缩放
    - 优化的视觉效果
    """
    
    def __init__(self, theme: str = "plotly_white"):
        """
        初始化绘图器
        
        Args:
            theme: Plotly主题
        """
        self.theme = theme
        self.colors = {
            'primary': '#2563eb',
            'secondary': '#f59e0b',
            'success': '#10b981',
            'danger': '#ef4444',
            'neutral': '#6b7280',
            'layers': ['#2563eb', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6', '#ec4899']
        }
        self.chart_ids = []
    
    def _get_sync_zoom_script(self, chart_ids: List[str]) -> str:
        """
        生成图表同步缩放的JavaScript代码
        
        Args:
            chart_ids: 需要联动的图表ID列表
            
        Returns:
            JavaScript代码字符串
        """
        if len(chart_ids) < 2:
            return ""
        
        chart_ids_json = json.dumps(chart_ids)
        
        script = f"""
<script>
(function() {{
    var chartIds = {chart_ids_json};
    var isSyncing = false;
    
    function syncZoom(sourceId, eventData) {{
        if (isSyncing) return;
        isSyncing = true;
        
        var xRange = eventData['xaxis.range'];
        var xRange2 = eventData['xaxis.range[0]'];
        var auto = eventData['xaxis.autorange'];
        
        chartIds.forEach(function(targetId) {{
            if (targetId !== sourceId) {{
                var targetDiv = document.getElementById(targetId);
                if (targetDiv) {{
                    if (auto) {{
                        Plotly.relayout(targetDiv, {{'xaxis.autorange': true}});
                    }} else if (xRange) {{
                        Plotly.relayout(targetDiv, {{'xaxis.range': xRange}});
                    }} else if (xRange2 !== undefined) {{
                        Plotly.relayout(targetDiv, {{
                            'xaxis.range[0]': eventData['xaxis.range[0]'],
                            'xaxis.range[1]': eventData['xaxis.range[1]']
                        }});
                    }}
                }}
            }}
        }});
        
        setTimeout(function() {{ isSyncing = false; }}, 100);
    }}
    
    chartIds.forEach(function(chartId) {{
        var chartDiv = document.getElementById(chartId);
        if (chartDiv) {{
            chartDiv.on('plotly_relayout', function(eventData) {{
                syncZoom(chartId, eventData);
            }});
        }}
    }});
}})();
</script>
"""
        return script
    
    def plot_ic_series(self, ic_series: pd.Series, title: Optional[str] = None) -> go.Figure:
        """
        绘制IC序列图
        
        Args:
            ic_series: IC序列，index为日期
            title: 图表标题
            
        Returns:
            Plotly图表对象
        """
        if title is None:
            title = "IC序列图 (Spearman Rank Correlation)"
        
        fig = go.Figure()
        
        # 计算累计IC和移动平均
        ic_cumsum = ic_series.cumsum()
        ic_ma20 = ic_series.rolling(window=20, min_periods=1).mean()
        
        # IC序列柱状图 - 增强悬停提示
        colors = [self.colors['success'] if x > 0 else self.colors['danger'] for x in ic_series]
        
        # 准备悬停文本
        hover_text = [
            f"<b>日期:</b> {date.strftime('%Y-%m-%d')}<br>"
            f"<b>IC值:</b> {ic:.4f}<br>"
            f"<b>20日移动平均:</b> {ma:.4f}<br>"
            f"<b>累计IC:</b> {cum:.4f}<br>"
            f"<extra></extra>"
            for date, ic, ma, cum in zip(ic_series.index, ic_series.values, ic_ma20.values, ic_cumsum.values)
        ]
        
        fig.add_trace(go.Bar(
            x=ic_series.index,
            y=ic_series.values,
            marker_color=colors,
            name='IC',
            opacity=0.7,
            text=hover_text,
            hoverinfo='text'
        ))
        
        # 添加20日移动平均线
        fig.add_trace(go.Scatter(
            x=ic_series.index,
            y=ic_ma20.values,
            mode='lines',
            name='20日移动平均',
            line=dict(color=self.colors['secondary'], width=2, dash='dash'),
            hovertemplate=(
                "<b>日期:</b> %{x|%Y-%m-%d}<br>"
                "<b>20日移动平均IC:</b> %{y:.4f}<br>"
                "<extra></extra>"
            ),
            showlegend=True
        ))
        
        # 均值线
        ic_mean = ic_series.mean()
        fig.add_hline(
            y=ic_mean,
            line_dash="dash",
            line_color=self.colors['primary'],
            annotation_text=f"均值: {ic_mean:.4f}",
            annotation_position="top right"
        )
        
        # 零线
        fig.add_hline(y=0, line_dash="solid", line_color="gray", opacity=0.5)
        
        # 布局 - 优化视觉效果
        fig.update_layout(
            title=dict(text=title, font=dict(size=18, color='#1f2937')),
            xaxis_title="日期",
            yaxis_title="IC",
            template=self.theme,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                font=dict(size=12)
            ),
            height=450,
            font=dict(size=13, color='#374151'),
            hovermode='x unified',
            xaxis=dict(
                tickfont=dict(size=11),
                tickangle=45,
                showgrid=True,
                gridcolor='rgba(0,0,0,0.05)',
                fixedrange=True
            ),
            yaxis=dict(
                tickfont=dict(size=11),
                showgrid=True,
                gridcolor='rgba(0,0,0,0.05)',
                zeroline=True,
                zerolinecolor='rgba(0,0,0,0.2)',
                fixedrange=True
            ),
            margin=dict(l=60, r=40, t=80, b=80),
            dragmode=False
        )
        
        return fig
    
    def plot_layer_cumreturns(
        self, 
        layer_cum_returns: pd.DataFrame,
        title: Optional[str] = None
    ) -> go.Figure:
        """
        绘制分层累计收益图
        
        Args:
            layer_cum_returns: 各层累计收益DataFrame
            title: 图表标题
            
        Returns:
            Plotly图表对象
        """
        if title is None:
            title = "分层累计收益图"
        
        fig = go.Figure()
        
        n_layers = len(layer_cum_returns.columns)
        
        # 计算每层年化收益率
        total_return = layer_cum_returns.iloc[-1] - 1
        n_years = len(layer_cum_returns) / 252  # 假设252个交易日/年
        annual_returns = ((1 + total_return) ** (1/n_years) - 1) if n_years > 0 else total_return
        
        for i, layer in enumerate(layer_cum_returns.columns):
            color = self.colors['layers'][i % len(self.colors['layers'])]
            
            # 计算日收益率用于悬停显示
            daily_returns = layer_cum_returns[layer].pct_change().fillna(0) * 100
            
            fig.add_trace(go.Scatter(
                x=layer_cum_returns.index,
                y=layer_cum_returns[layer].values,
                mode='lines',
                name=f'第{layer}层',
                line=dict(color=color, width=2.5),
                hovertemplate=(
                    f"<b>第{layer}层</b><br>"
                    "<b>日期:</b> %{x|%Y-%m-%d}<br>"
                    "<b>累计收益:</b> %{y:.4f}<br>"
                    "<b>日收益率:</b> %{customdata:.2f}%<br>"
                    "<b>总收益率:</b> %{meta:.2%}<br>"
                    "<b>年化收益率:</b> " + f"{annual_returns[layer]:.2%}" + "<br>"
                    "<extra></extra>"
                ),
                customdata=daily_returns.values,
                meta=[total_return[layer]] * len(layer_cum_returns)
            ))
        
        # 添加基准线（1.0）
        fig.add_hline(
            y=1.0,
            line_dash="dash",
            line_color="gray",
            opacity=0.5,
            annotation_text="基准"
        )
        
        fig.update_layout(
            title=dict(text=title, font=dict(size=18, color='#1f2937')),
            xaxis_title="日期",
            yaxis_title="累计收益",
            template=self.theme,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                font=dict(size=11)
            ),
            height=500,
            font=dict(size=13, color='#374151'),
            hovermode='x unified',
            xaxis=dict(
                tickfont=dict(size=11),
                tickangle=45,
                showgrid=True,
                gridcolor='rgba(0,0,0,0.05)',
                fixedrange=True
            ),
            yaxis=dict(
                tickfont=dict(size=11),
                showgrid=True,
                gridcolor='rgba(0,0,0,0.05)',
                zeroline=False,
                fixedrange=True
            ),
            margin=dict(l=60, r=40, t=100, b=80),
            dragmode=False
        )
        
        return fig
    
    def plot_long_short_nav(
        self,
        cum_returns: pd.Series,
        title: Optional[str] = None,
        benchmark: Optional[pd.Series] = None
    ) -> go.Figure:
        """
        绘制多空净值曲线图
        
        Args:
            cum_returns: 多空组合累计收益序列
            title: 图表标题
            benchmark: 基准净值序列（可选）
            
        Returns:
            Plotly图表对象
        """
        if title is None:
            title = "多空组合净值曲线"
        
        # 计算回撤
        running_max = cum_returns.expanding().max()
        drawdown = (cum_returns - running_max) / running_max
        
        # 计算日收益率
        daily_returns = cum_returns.pct_change().fillna(0) * 100
        
        # 计算统计指标
        total_return = cum_returns.iloc[-1] - 1
        max_dd = drawdown.min()
        
        # 创建子图
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.12,
            row_heights=[0.7, 0.3],
            subplot_titles=("净值曲线", "回撤")
        )
        
        # 净值曲线 - 增强悬停提示
        fig.add_trace(
            go.Scatter(
                x=cum_returns.index,
                y=cum_returns.values,
                mode='lines',
                name='多空净值',
                line=dict(color=self.colors['primary'], width=2.5),
                fill='tozeroy',
                fillcolor='rgba(37, 99, 235, 0.15)',
                hovertemplate=(
                    "<b>多空组合</b><br>"
                    "<b>日期:</b> %{x|%Y-%m-%d}<br>"
                    "<b>净值:</b> %{y:.4f}<br>"
                    "<b>日收益率:</b> %{customdata:.2f}%<br>"
                    "<b>累计收益:</b> %{meta:.2%}<br>"
                    "<extra></extra>"
                ),
                customdata=daily_returns.values,
                meta=[total_return] * len(cum_returns)
            ),
            row=1, col=1
        )
        
        # 添加基准线
        if benchmark is not None:
            fig.add_trace(
                go.Scatter(
                    x=benchmark.index,
                    y=benchmark.values,
                    mode='lines',
                    name='基准净值',
                    line=dict(color=self.colors['neutral'], width=2, dash='dash'),
                    hovertemplate=(
                        "<b>基准</b><br>"
                        "<b>日期:</b> %{x|%Y-%m-%d}<br>"
                        "<b>净值:</b> %{y:.4f}<br>"
                        "<extra></extra>"
                    )
                ),
                row=1, col=1
            )
        
        fig.add_hline(y=1.0, line_dash="dash", line_color="gray", opacity=0.5, row=1, col=1)
        
        # 回撤 - 增强悬停提示
        fig.add_trace(
            go.Scatter(
                x=drawdown.index,
                y=drawdown.values * 100,
                mode='lines',
                name='回撤',
                line=dict(color=self.colors['danger'], width=1.5),
                fill='tozeroy',
                fillcolor='rgba(239, 68, 68, 0.2)',
                hovertemplate=(
                    "<b>回撤</b><br>"
                    "<b>日期:</b> %{x|%Y-%m-%d}<br>"
                    "<b>回撤:</b> %{y:.2f}%<br>"
                    "<b>最大回撤:</b> " + f"{max_dd:.2%}" + "<br>"
                    "<extra></extra>"
                ),
                showlegend=False
            ),
            row=2, col=1
        )
        
        fig.update_layout(
            title=dict(text=title, font=dict(size=18, color='#1f2937')),
            template=self.theme,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                font=dict(size=11)
            ),
            height=650,
            font=dict(size=13, color='#374151'),
            hovermode='x unified',
            margin=dict(l=60, r=40, t=100, b=60)
        )
        
        fig.update_yaxes(
            title_text="净值",
            tickfont=dict(size=11),
            showgrid=True,
            gridcolor='rgba(0,0,0,0.05)',
            fixedrange=True,
            row=1, col=1
        )
        fig.update_yaxes(
            title_text="回撤(%)",
            tickfont=dict(size=11),
            showgrid=True,
            gridcolor='rgba(0,0,0,0.05)',
            fixedrange=True,
            row=2, col=1
        )
        fig.update_xaxes(
            title_text="日期",
            tickfont=dict(size=11),
            tickangle=45,
            showgrid=True,
            gridcolor='rgba(0,0,0,0.05)',
            fixedrange=True,
            row=1, col=1
        )
        fig.update_xaxes(
            title_text="日期",
            tickfont=dict(size=11),
            tickangle=45,
            showgrid=True,
            gridcolor='rgba(0,0,0,0.05)',
            fixedrange=True,
            row=2, col=1
        )
        
        fig.update_layout(dragmode=False)
        
        return fig
    
    def plot_ic_distribution(
        self,
        ic_series: pd.Series,
        title: Optional[str] = None
    ) -> go.Figure:
        """
        绘制IC分布图
        
        Args:
            ic_series: IC序列
            title: 图表标题
            
        Returns:
            Plotly图表对象
        """
        if title is None:
            title = "IC分布图"
        
        fig = go.Figure()
        
        # 计算统计指标
        ic_mean = ic_series.mean()
        ic_std = ic_series.std()
        icir = ic_mean / ic_std if ic_std != 0 else 0
        win_rate = (ic_series > 0).mean()
        
        # 直方图 - 增强悬停提示
        fig.add_trace(go.Histogram(
            x=ic_series.values,
            nbinsx=30,
            name='IC分布',
            marker_color=self.colors['primary'],
            opacity=0.7,
            hovertemplate=(
                "<b>IC区间:</b> %{x:.4f}<br>"
                "<b>频数:</b> %{y}<br>"
                "<extra></extra>"
            )
        ))
        
        # 添加均值线
        fig.add_vline(
            x=ic_mean,
            line_dash="dash",
            line_color=self.colors['danger'],
            annotation_text=f"均值: {ic_mean:.4f}",
            annotation_position="top"
        )
        
        # 添加零线
        fig.add_vline(x=0, line_dash="solid", line_color="gray", opacity=0.5)
        
        # 添加统计信息卡片
        stats_text = (
            f"<b>IC统计指标</b><br>"
            f"━━━━━━━━━━━━<br>"
            f"均值: {ic_mean:.4f}<br>"
            f"标准差: {ic_std:.4f}<br>"
            f"ICIR: {icir:.4f}<br>"
            f"胜率: {win_rate:.2%}<br>"
            f"样本数: {len(ic_series)}"
        )
        
        fig.add_annotation(
            xref="paper", yref="paper",
            x=0.98, y=0.98,
            text=stats_text,
            showarrow=False,
            font=dict(size=12, color='#374151'),
            bgcolor="rgba(255,255,255,0.95)",
            bordercolor=self.colors['primary'],
            borderwidth=2,
            borderpad=10,
            align="left"
        )
        
        fig.update_layout(
            title=dict(text=title, font=dict(size=18, color='#1f2937')),
            xaxis_title="IC值",
            yaxis_title="频数",
            template=self.theme,
            showlegend=False,
            height=450,
            font=dict(size=13, color='#374151'),
            hovermode='x unified',
            xaxis=dict(
                tickfont=dict(size=11),
                showgrid=True,
                gridcolor='rgba(0,0,0,0.05)',
                zeroline=True,
                zerolinecolor='rgba(0,0,0,0.2)',
                fixedrange=True
            ),
            yaxis=dict(
                tickfont=dict(size=11),
                showgrid=True,
                gridcolor='rgba(0,0,0,0.05)',
                fixedrange=True
            ),
            margin=dict(l=60, r=40, t=80, b=60),
            dragmode=False
        )
        
        return fig
    
    def plot_ic_heatmap(
        self,
        ic_series: pd.Series,
        title: Optional[str] = None
    ) -> go.Figure:
        """
        绘制IC月度热力图
        
        Args:
            ic_series: IC序列，index为日期
            title: 图表标题
            
        Returns:
            Plotly图表对象
        """
        if title is None:
            title = "IC月度热力图"
        
        # 准备月度数据
        ic_monthly = ic_series.copy()
        ic_monthly.index = pd.to_datetime(ic_monthly.index)
        
        # 按月聚合
        monthly_data = ic_monthly.groupby([
            ic_monthly.index.year,
            ic_monthly.index.month
        ]).mean()
        
        # 构建热力图数据
        years = sorted(set([x[0] for x in monthly_data.index]))
        months = list(range(1, 13))
        
        z = []
        for year in years:
            row = []
            for month in months:
                key = (year, month)
                if key in monthly_data.index:
                    row.append(monthly_data[key])
                else:
                    row.append(np.nan)
            z.append(row)
        
        fig = go.Figure(data=go.Heatmap(
            z=z,
            x=[f"{m}月" for m in months],
            y=[str(y) for y in years],
            colorscale='RdYlGn',
            zmid=0,
            colorbar=dict(title="IC均值"),
            hovertemplate='年份: %{y}<br>月份: %{x}<br>IC: %{z:.4f}<extra></extra>'
        ))
        
        fig.update_layout(
            title=title,
            template=self.theme,
            height=400
        )
        
        return fig
    
    def create_summary_figure(
        self,
        ic_series: pd.Series,
        layer_cum_returns: pd.DataFrame,
        long_short_cum_returns: pd.Series
    ) -> go.Figure:
        """
        创建汇总图表（2x2网格）
        
        Args:
            ic_series: IC序列
            layer_cum_returns: 分层累计收益
            long_short_cum_returns: 多空累计收益
            
        Returns:
            Plotly图表对象
        """
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                "IC序列",
                "分层累计收益",
                "IC分布",
                "多空净值"
            ),
            specs=[
                [{"type": "scatter"}, {"type": "scatter"}],
                [{"type": "histogram"}, {"type": "scatter"}]
            ]
        )
        
        # IC序列
        colors = [self.colors['success'] if x > 0 else self.colors['danger'] for x in ic_series]
        fig.add_trace(go.Bar(x=ic_series.index, y=ic_series.values, marker_color=colors, name='IC'), row=1, col=1)
        fig.add_hline(y=ic_series.mean(), line_dash="dash", line_color=self.colors['primary'], row=1, col=1)
        
        # 分层收益
        for i, layer in enumerate(layer_cum_returns.columns):
            color = self.colors['layers'][i % len(self.colors['layers'])]
            fig.add_trace(go.Scatter(
                x=layer_cum_returns.index,
                y=layer_cum_returns[layer].values,
                mode='lines',
                name=f'第{layer}层',
                line=dict(color=color)
            ), row=1, col=2)
        
        # IC分布
        fig.add_trace(go.Histogram(x=ic_series.values, nbinsx=20, name='IC分布', marker_color=self.colors['primary']), row=2, col=1)
        fig.add_vline(x=ic_series.mean(), line_dash="dash", line_color=self.colors['danger'], row=2, col=1)
        
        # 多空净值
        fig.add_trace(go.Scatter(
            x=long_short_cum_returns.index,
            y=long_short_cum_returns.values,
            mode='lines',
            name='多空净值',
            line=dict(color=self.colors['primary'])
        ), row=2, col=2)
        
        fig.update_layout(
            title="回测结果汇总",
            template=self.theme,
            height=800,
            showlegend=False
        )
        
        return fig
    
    def _generate_ic_table(self, ic_series: pd.Series) -> str:
        """生成IC序列数据表格"""
        # 取最近20条数据
        recent_data = ic_series.tail(20)
        ic_ma20 = ic_series.rolling(window=20, min_periods=1).mean()
        
        rows = ""
        for date, ic in recent_data.items():
            ma20 = ic_ma20[date]
            color_class = "positive" if ic > 0 else "negative"
            rows += f"""
                <tr>
                    <td>{date.strftime('%Y-%m-%d')}</td>
                    <td class="{color_class}">{ic:+.4f}</td>
                    <td>{ma20:.4f}</td>
                </tr>"""
        
        return f"""
        <div class="data-section">
            <div class="data-header">
                <div class="data-title">Recent Data (20)</div>
            </div>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>IC Value</th>
                        <th>MA20</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>"""
    
    def _generate_layer_table(self, layer_cum_returns: pd.DataFrame) -> str:
        """生成分层累计收益数据表格"""
        # 取最近10条数据
        recent_data = layer_cum_returns.tail(10)
        
        headers = "".join([f"<th>{col}</th>" for col in recent_data.columns])
        
        rows = ""
        for date, row in recent_data.iterrows():
            row_data = "".join([f"<td>{val:.4f}</td>" for val in row.values])
            rows += f"""
                <tr>
                    <td>{date.strftime('%Y-%m-%d')}</td>
                    {row_data}
                </tr>"""
        
        return f"""
        <div class="data-section">
            <div class="data-header">
                <div class="data-title">Recent Data (10)</div>
            </div>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Date</th>
                        {headers}
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>"""
    
    def _generate_nav_table(self, long_short_cum_returns: pd.Series) -> str:
        """生成多空净值数据表格"""
        # 计算回撤
        running_max = long_short_cum_returns.expanding().max()
        drawdown = (long_short_cum_returns - running_max) / running_max
        
        # 取最近15条数据
        recent_data = long_short_cum_returns.tail(15)
        
        rows = ""
        for date, nav in recent_data.items():
            dd = drawdown[date]
            daily_return = (long_short_cum_returns.pct_change()[date]) * 100 if date in long_short_cum_returns.pct_change().index else 0
            rows += f"""
                <tr>
                    <td>{date.strftime('%Y-%m-%d')}</td>
                    <td>{nav:.4f}</td>
                    <td>{daily_return:+.2f}%</td>
                    <td class="negative">{dd:.2%}</td>
                </tr>"""
        
        return f"""
        <div class="data-section">
            <div class="data-header">
                <div class="data-title">Recent Data (15)</div>
            </div>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>NAV</th>
                        <th>Daily Return</th>
                        <th>Drawdown</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>"""
    
    def _generate_ic_stats_table(self, ic_series: pd.Series) -> str:
        """生成IC统计信息表格"""
        ic_mean = ic_series.mean()
        ic_std = ic_series.std()
        icir = ic_mean / ic_std if ic_std != 0 else 0
        win_rate = (ic_series > 0).mean()
        
        # 计算分位数
        q25 = ic_series.quantile(0.25)
        q50 = ic_series.quantile(0.50)
        q75 = ic_series.quantile(0.75)
        
        return f"""
        <div class="data-section">
            <div class="data-header">
                <div class="data-title">Statistics</div>
            </div>
            <div class="stats-grid">
                <div class="stats-item">
                    <div class="stats-label">Mean</div>
                    <div class="stats-value {'positive' if ic_mean > 0 else 'negative'}">{ic_mean:+.4f}</div>
                </div>
                <div class="stats-item">
                    <div class="stats-label">Std Dev</div>
                    <div class="stats-value">{ic_std:.4f}</div>
                </div>
                <div class="stats-item">
                    <div class="stats-label">ICIR</div>
                    <div class="stats-value">{icir:.4f}</div>
                </div>
                <div class="stats-item">
                    <div class="stats-label">Win Rate</div>
                    <div class="stats-value positive">{win_rate:.2%}</div>
                </div>
                <div class="stats-item">
                    <div class="stats-label">25th Percentile</div>
                    <div class="stats-value">{q25:.4f}</div>
                </div>
                <div class="stats-item">
                    <div class="stats-label">Median</div>
                    <div class="stats-value">{q50:.4f}</div>
                </div>
                <div class="stats-item">
                    <div class="stats-label">75th Percentile</div>
                    <div class="stats-value">{q75:.4f}</div>
                </div>
                <div class="stats-item">
                    <div class="stats-label">Sample Size</div>
                    <div class="stats-value">{len(ic_series)}</div>
                </div>
            </div>
        </div>"""
    
    def create_dashboard(
        self,
        ic_series: pd.Series,
        layer_cum_returns: pd.DataFrame,
        long_short_cum_returns: pd.Series,
        factor_name: str = "因子",
        output_path: Optional[str] = None
    ) -> str:
        """
        创建交互式Dashboard页面，整合所有图表并支持联动
        
        Args:
            ic_series: IC序列
            layer_cum_returns: 分层累计收益
            long_short_cum_returns: 多空累计收益
            factor_name: 因子名称
            output_path: 输出HTML文件路径
            
        Returns:
            HTML字符串
        """
        import plotly.offline as pyo
        
        # 计算关键指标
        ic_mean = ic_series.mean()
        ic_std = ic_series.std()
        icir = ic_mean / ic_std if ic_std != 0 else 0
        
        total_return = long_short_cum_returns.iloc[-1] - 1
        running_max = long_short_cum_returns.expanding().max()
        max_drawdown = ((long_short_cum_returns - running_max) / running_max).min()
        
        # 生成图表ID
        chart_id_ic = f"chart_ic_{id(ic_series)}"
        chart_id_layer = f"chart_layer_{id(layer_cum_returns)}"
        chart_id_nav = f"chart_nav_{id(long_short_cum_returns)}"
        chart_id_dist = f"chart_dist_{id(ic_series)}"
        
        chart_ids = [chart_id_ic, chart_id_layer, chart_id_nav]
        
        # 创建各个图表
        fig_ic = self.plot_ic_series(ic_series, title="IC序列")
        fig_layer = self.plot_layer_cumreturns(layer_cum_returns, title="分层累计收益")
        fig_nav = self.plot_long_short_nav(long_short_cum_returns, title="多空净值曲线")
        fig_dist = self.plot_ic_distribution(ic_series, title="IC分布")
        
        # 将图表转换为HTML div（禁用缩放）
        config = {'displayModeBar': True, 'scrollZoom': False, 'showAxisDragHandles': False}
        
        html_ic = pyo.plot(fig_ic, output_type='div', include_plotlyjs=False, config=config)
        html_layer = pyo.plot(fig_layer, output_type='div', include_plotlyjs=False, config=config)
        html_nav = pyo.plot(fig_nav, output_type='div', include_plotlyjs=False, config=config)
        html_dist = pyo.plot(fig_dist, output_type='div', include_plotlyjs=False, config=config)
        
        # 替换div id以便联动
        html_ic = html_ic.replace('<div id="', f'<div id="{chart_id_ic}_"')
        html_ic = html_ic.replace(f'var gd = document.getElementById(\'{chart_id_ic}_', f'var gd = document.getElementById(\'{chart_id_ic}')
        
        # 生成数据表格
        ic_table = self._generate_ic_table(ic_series)
        layer_table = self._generate_layer_table(layer_cum_returns)
        nav_table = self._generate_nav_table(long_short_cum_returns)
        ic_stats_table = self._generate_ic_stats_table(ic_series)
        
        # 构建Dashboard HTML
        sync_script = self._get_sync_zoom_script(chart_ids)
        
        dashboard_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{factor_name} - 回测结果</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #FAFAF8;
            --bg-secondary: #F5F5F3;
            --bg-card: #FFFFFF;
            --text-primary: #1A1A1A;
            --text-secondary: #6B6B6B;
            --text-muted: #9B9B9B;
            --border-light: #E8E8E6;
            --border-medium: #D4D4D2;
            --accent-positive: #065F46;
            --accent-negative: #991B1B;
            --accent-neutral: #4338CA;
            --accent-warm: #92400E;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Source Serif 4', Georgia, serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 48px 32px;
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 1440px;
            margin: 0 auto;
        }}
        
        /* Header Section */
        .header {{
            margin-bottom: 48px;
            padding-bottom: 32px;
            border-bottom: 1px solid var(--border-light);
        }}
        
        .header h1 {{
            font-size: 42px;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 8px;
            letter-spacing: -0.02em;
        }}
        
        .header .subtitle {{
            font-size: 16px;
            color: var(--text-secondary);
            font-style: italic;
        }}
        
        /* Metrics Grid */
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 24px;
            margin-bottom: 48px;
        }}
        
        .metric-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-light);
            padding: 28px 24px;
            transition: all 0.2s ease;
        }}
        
        .metric-card:hover {{
            border-color: var(--border-medium);
            box-shadow: 0 4px 20px rgba(0,0,0,0.04);
        }}
        
        .metric-label {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 11px;
            font-weight: 500;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin-bottom: 12px;
        }}
        
        .metric-value {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 28px;
            font-weight: 500;
            color: var(--text-primary);
        }}
        
        .metric-value.positive {{
            color: var(--accent-positive);
        }}
        
        .metric-value.negative {{
            color: var(--accent-negative);
        }}
        
        /* Charts Layout */
        .charts-layout {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 32px;
        }}
        
        .chart-section {{
            background: var(--bg-card);
            border: 1px solid var(--border-light);
            padding: 32px;
        }}
        
        .chart-section.full-width {{
            grid-column: 1 / -1;
        }}
        
        .chart-header {{
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border-light);
        }}
        
        .chart-title {{
            font-size: 20px;
            font-weight: 600;
            color: var(--text-primary);
            letter-spacing: -0.01em;
        }}
        
        .chart-subtitle {{
            font-size: 13px;
            color: var(--text-muted);
            font-style: italic;
        }}
        
        /* Data Table Styles */
        .data-section {{
            margin-top: 32px;
            padding-top: 24px;
            border-top: 1px solid var(--border-light);
        }}
        
        .data-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }}
        
        .data-title {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 11px;
            font-weight: 500;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }}
        
        .data-table {{
            width: 100%;
            border-collapse: collapse;
            font-family: 'IBM Plex Mono', monospace;
            font-size: 12px;
        }}
        
        .data-table th {{
            text-align: left;
            padding: 12px 8px;
            font-weight: 500;
            color: var(--text-secondary);
            border-bottom: 1px solid var(--border-medium);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        
        .data-table td {{
            padding: 10px 8px;
            border-bottom: 1px solid var(--border-light);
            color: var(--text-primary);
        }}
        
        .data-table tr:hover td {{
            background-color: var(--bg-secondary);
        }}
        
        .data-table .positive {{
            color: var(--accent-positive);
            font-weight: 500;
        }}
        
        .data-table .negative {{
            color: var(--accent-negative);
            font-weight: 500;
        }}
        
        /* Stats Table */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 1px;
            background: var(--border-light);
            border: 1px solid var(--border-light);
        }}
        
        .stats-item {{
            background: var(--bg-card);
            padding: 16px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .stats-label {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 11px;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        
        .stats-value {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 14px;
            font-weight: 500;
            color: var(--text-primary);
        }}
        
        .stats-value.positive {{
            color: var(--accent-positive);
        }}
        
        .stats-value.negative {{
            color: var(--accent-negative);
        }}
        
        /* Responsive */
        @media (max-width: 1024px) {{
            .metrics-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
            .charts-layout {{
                grid-template-columns: 1fr;
            }}
        }}
        
        @media (max-width: 640px) {{
            body {{
                padding: 24px 16px;
            }}
            .metrics-grid {{
                grid-template-columns: 1fr;
            }}
            .header h1 {{
                font-size: 28px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{factor_name}</h1>
            <div class="subtitle">Backtest Analysis Report</div>
        </div>
        
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">IC Mean</div>
                <div class="metric-value {'positive' if ic_mean > 0 else 'negative'}">{ic_mean:+.4f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">ICIR</div>
                <div class="metric-value {'positive' if icir > 0 else 'negative'}">{icir:+.4f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Long-Short Return</div>
                <div class="metric-value {'positive' if total_return > 0 else 'negative'}">{total_return:+.2%}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Max Drawdown</div>
                <div class="metric-value negative">{max_drawdown:.2%}</div>
            </div>
        </div>
        
        <div class="charts-layout">
            <div class="chart-section">
                <div class="chart-header">
                    <div class="chart-title">IC Series</div>
                    <div class="chart-subtitle">Information Coefficient over time</div>
                </div>
                {html_ic}
                {ic_table}
            </div>
            
            <div class="chart-section">
                <div class="chart-header">
                    <div class="chart-title">Layered Returns</div>
                    <div class="chart-subtitle">Cumulative returns by quantile</div>
                </div>
                {html_layer}
                {layer_table}
            </div>
            
            <div class="chart-section">
                <div class="chart-header">
                    <div class="chart-title">IC Distribution</div>
                    <div class="chart-subtitle">Distribution of information coefficient</div>
                </div>
                {html_dist}
                {ic_stats_table}
            </div>
            
            <div class="chart-section full-width">
                <div class="chart-header">
                    <div class="chart-title">Long-Short NAV</div>
                    <div class="chart-subtitle">Net asset value and drawdown analysis</div>
                </div>
                {html_nav}
                {nav_table}
            </div>
        </div>
    </div>
</body>
</html>"""
        
        # 保存文件
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(dashboard_html)
        
        return dashboard_html
