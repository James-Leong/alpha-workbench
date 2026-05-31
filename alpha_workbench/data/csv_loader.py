"""
CSV Data Loader for AlphaWorkbench
支持从CSV文件加载因子数据、价格数据和回测数据
"""
import pandas as pd
from typing import Tuple, Optional, Dict, List
from pathlib import Path
from datetime import datetime


def load_factor_data_from_csv(
    csv_path: str,
    date_col: str = 'date',
    stock_col: str = 'stock_code',
    factor_col: str = 'factor_value',
    date_format: Optional[str] = None
) -> pd.DataFrame:
    """
    从CSV加载因子数据
    
    CSV格式要求:
    - 长格式: 每行一条记录，包含日期、股票代码、因子值
    - 或宽格式: 行为日期，列为股票代码
    
    Args:
        csv_path: CSV文件路径
        date_col: 日期列名
        stock_col: 股票代码列名
        factor_col: 因子值列名
        date_format: 日期格式，如 '%Y-%m-%d'
        
    Returns:
        factor_data: DataFrame, index=date, columns=stock_code
    """
    df = pd.read_csv(csv_path)
    
    # 解析日期
    if date_format:
        df[date_col] = pd.to_datetime(df[date_col], format=date_format)
    else:
        df[date_col] = pd.to_datetime(df[date_col])
    
    # 判断是长格式还是宽格式
    if stock_col in df.columns and factor_col in df.columns:
        # 长格式转宽格式
        factor_data = df.pivot(index=date_col, columns=stock_col, values=factor_col)
    elif len(df.columns) > 2:
        # 可能是宽格式，第一列是日期
        if date_col in df.columns:
            df.set_index(date_col, inplace=True)
        factor_data = df
    else:
        raise ValueError(f"无法识别CSV格式，请确保包含列: {date_col}, {stock_col}, {factor_col}")
    
    # 确保索引是日期类型
    factor_data.index = pd.to_datetime(factor_data.index)
    factor_data.index.name = 'date'
    
    return factor_data


def load_price_data_from_csv(
    csv_path: str,
    date_col: str = 'date',
    stock_col: str = 'stock_code',
    price_col: str = 'close',
    date_format: Optional[str] = None
) -> pd.DataFrame:
    """
    从CSV加载价格数据
    
    Args:
        csv_path: CSV文件路径
        date_col: 日期列名
        stock_col: 股票代码列名
        price_col: 价格列名
        date_format: 日期格式
        
    Returns:
        price_data: DataFrame, index=date, columns=stock_code
    """
    df = pd.read_csv(csv_path)
    
    # 解析日期
    if date_format:
        df[date_col] = pd.to_datetime(df[date_col], format=date_format)
    else:
        df[date_col] = pd.to_datetime(df[date_col])
    
    # 判断格式并转换
    if stock_col in df.columns and price_col in df.columns:
        price_data = df.pivot(index=date_col, columns=stock_col, values=price_col)
    elif date_col in df.columns:
        df.set_index(date_col, inplace=True)
        price_data = df
    else:
        raise ValueError(f"无法识别CSV格式，请确保包含列: {date_col}, {stock_col}, {price_col}")
    
    price_data.index = pd.to_datetime(price_data.index)
    price_data.index.name = 'date'
    
    return price_data


def load_ohlcv_from_csv(
    csv_path: str,
    date_col: str = 'date',
    stock_col: str = 'stock_code',
    price_col: str = 'close',
    date_format: Optional[str] = None
) -> Dict[str, pd.DataFrame]:
    """
    从CSV加载OHLCV数据
    
    Args:
        csv_path: CSV文件路径
        date_col: 日期列名
        stock_col: 股票代码列名
        price_col: 默认使用的价格列
        date_format: 日期格式
        
    Returns:
        ohlcv_dict: 包含 open, high, low, close, volume 的字典
    """
    df = pd.read_csv(csv_path)
    
    # 解析日期
    if date_format:
        df[date_col] = pd.to_datetime(df[date_col], format=date_format)
    else:
        df[date_col] = pd.to_datetime(df[date_col])
    
    # 识别OHLCV列
    ohlcv_cols = {}
    col_mapping = {
        'open': ['open', 'Open', 'OPEN', '开盘价'],
        'high': ['high', 'High', 'HIGH', '最高价'],
        'low': ['low', 'Low', 'LOW', '最低价'],
        'close': ['close', 'Close', 'CLOSE', '收盘价', 'price', 'Price'],
        'volume': ['volume', 'Volume', 'VOLUME', 'vol', 'Vol', '成交量']
    }
    
    for std_name, possible_names in col_mapping.items():
        for col in df.columns:
            if col in possible_names:
                ohlcv_cols[std_name] = col
                break
    
    # 转换为宽格式
    result = {}
    for std_name, col_name in ohlcv_cols.items():
        if stock_col in df.columns:
            pivoted = df.pivot(index=date_col, columns=stock_col, values=col_name)
        else:
            pivoted = df.set_index(date_col)[[col_name]]
        pivoted.index = pd.to_datetime(pivoted.index)
        result[std_name] = pivoted
    
    return result


def load_backtest_data_from_csv(
    factor_csv: str,
    price_csv: str,
    factor_date_col: str = 'date',
    factor_stock_col: str = 'stock_code',
    factor_value_col: str = 'factor_value',
    price_date_col: str = 'date',
    price_stock_col: str = 'stock_code',
    price_value_col: str = 'close',
    date_format: Optional[str] = None
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    从CSV加载完整的回测数据
    
    Args:
        factor_csv: 因子数据CSV路径
        price_csv: 价格数据CSV路径
        其他参数: 各列名配置
        
    Returns:
        (factor_data, price_data, returns_data)
    """
    # 加载因子数据
    factor_data = load_factor_data_from_csv(
        factor_csv,
        date_col=factor_date_col,
        stock_col=factor_stock_col,
        factor_col=factor_value_col,
        date_format=date_format
    )
    
    # 加载价格数据
    price_data = load_price_data_from_csv(
        price_csv,
        date_col=price_date_col,
        stock_col=price_stock_col,
        price_col=price_value_col,
        date_format=date_format
    )
    
    # 对齐日期和股票
    common_dates = factor_data.index.intersection(price_data.index)
    common_stocks = factor_data.columns.intersection(price_data.columns)
    
    factor_data = factor_data.loc[common_dates, common_stocks]
    price_data = price_data.loc[common_dates, common_stocks]
    
    # 计算收益率
    returns_data = price_data.pct_change().shift(-1).iloc[:-1]
    factor_data = factor_data.iloc[:-1]
    price_data = price_data.iloc[:-1]
    
    return factor_data, price_data, returns_data


def load_role4_factor_output(
    csv_path: str,
    date_col: str = 'date',
    stock_col: str = 'stock_code',
    factor_col: str = 'factor_value',
    factor_id_col: Optional[str] = None,
    factor_name_col: Optional[str] = None
) -> Tuple[pd.DataFrame, Dict[str, any]]:
    """
    加载Role4输出的因子数据
    
    支持两种格式:
    1. 单因子: date, stock_code, factor_value
    2. 多因子: date, stock_code, factor_1, factor_2, ...
    
    Args:
        csv_path: CSV文件路径
        date_col: 日期列名
        stock_col: 股票代码列名
        factor_col: 因子值列名（单因子）或因子列前缀
        factor_id_col: 因子ID列名（元数据）
        factor_name_col: 因子名称列名（元数据）
        
    Returns:
        (factor_data, metadata)
    """
    df = pd.read_csv(csv_path)
    
    # 解析日期
    df[date_col] = pd.to_datetime(df[date_col])
    
    # 提取元数据
    metadata = {}
    if factor_id_col and factor_id_col in df.columns:
        metadata['factor_id'] = df[factor_id_col].iloc[0]
    if factor_name_col and factor_name_col in df.columns:
        metadata['factor_name'] = df[factor_name_col].iloc[0]
    
    # 判断格式
    if factor_col in df.columns:
        # 单因子长格式
        factor_data = df.pivot(index=date_col, columns=stock_col, values=factor_col)
    else:
        # 多因子宽格式
        factor_cols = [c for c in df.columns if c.startswith(factor_col)]
        if len(factor_cols) == 1:
            factor_data = df.pivot(index=date_col, columns=stock_col, values=factor_cols[0])
        else:
            # 返回多个因子
            factor_data = {}
            for fc in factor_cols:
                factor_data[fc] = df.pivot(index=date_col, columns=stock_col, values=fc)
    
    if isinstance(factor_data, pd.DataFrame):
        factor_data.index = pd.to_datetime(factor_data.index)
        factor_data.index.name = 'date'
    
    return factor_data, metadata


def save_backtest_report_to_csv(
    report_data: Dict[str, any],
    output_dir: str,
    prefix: str = "backtest"
) -> List[str]:
    """
    将回测报告保存为CSV格式
    
    Args:
        report_data: 回测报告数据
        output_dir: 输出目录
        prefix: 文件名前缀
        
    Returns:
        保存的文件路径列表
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    saved_files = []
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # 保存IC序列
    if 'ic_series' in report_data:
        ic_file = output_path / f"{prefix}_ic_series_{timestamp}.csv"
        report_data['ic_series'].to_csv(ic_file)
        saved_files.append(str(ic_file))
    
    # 保存分层收益
    if 'layer_returns' in report_data:
        layer_file = output_path / f"{prefix}_layer_returns_{timestamp}.csv"
        report_data['layer_returns'].to_csv(layer_file)
        saved_files.append(str(layer_file))
    
    # 保存多空收益
    if 'long_short_returns' in report_data:
        ls_file = output_path / f"{prefix}_long_short_{timestamp}.csv"
        report_data['long_short_returns'].to_csv(ls_file)
        saved_files.append(str(ls_file))
    
    # 保存订单列表
    if 'orders' in report_data:
        orders_file = output_path / f"{prefix}_orders_{timestamp}.csv"
        pd.DataFrame(report_data['orders']).to_csv(orders_file, index=False)
        saved_files.append(str(orders_file))
    
    return saved_files


# 便捷函数
load_factor_csv = load_factor_data_from_csv
load_price_csv = load_price_data_from_csv
load_ohlc_csv = load_ohlcv_from_csv
