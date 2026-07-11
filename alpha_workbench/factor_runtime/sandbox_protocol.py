"""JSON protocol shared by the host and isolated factor worker."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping

import pandas as pd


def frame_to_payload(frame: pd.DataFrame) -> dict[str, Any]:
    column_kinds = [_column_kind(frame[column]) for column in frame.columns]
    return {
        "index": [pd.Timestamp(value).isoformat() for value in frame.index],
        "columns": [str(value) for value in frame.columns],
        "column_kinds": column_kinds,
        "data": [
            [_json_cell(value) for value in row]
            for row in frame.itertuples(index=False, name=None)
        ],
    }


def frame_from_payload(payload: Mapping[str, Any]) -> pd.DataFrame:
    required = {"index", "columns", "column_kinds", "data"}
    if set(payload) != required:
        raise ValueError("sandbox frame payload has invalid keys")
    columns = payload["columns"]
    kinds = payload["column_kinds"]
    data = payload["data"]
    index = payload["index"]
    if not isinstance(columns, list) or not all(isinstance(item, str) for item in columns):
        raise ValueError("sandbox frame columns must be strings")
    if not isinstance(kinds, list) or len(kinds) != len(columns):
        raise ValueError("sandbox frame column kinds do not match columns")
    if not isinstance(index, list) or not isinstance(data, list):
        raise ValueError("sandbox frame index and data must be lists")
    if len(index) != len(data):
        raise ValueError("sandbox frame row count does not match index")
    if any(not isinstance(row, list) or len(row) != len(columns) for row in data):
        raise ValueError("sandbox frame row width does not match columns")
    frame = pd.DataFrame(data, columns=columns)
    frame.index = pd.DatetimeIndex(pd.to_datetime(index, errors="raise"))
    for column, kind in zip(columns, kinds, strict=True):
        if kind == "datetime":
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
        elif kind == "numeric":
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        elif kind != "object":
            raise ValueError(f"unsupported sandbox column kind: {kind!r}")
    return frame


def _column_kind(series: pd.Series) -> str:
    if pd.api.types.is_datetime64_any_dtype(series.dtype):
        return "datetime"
    if pd.api.types.is_numeric_dtype(series.dtype):
        return "numeric"
    non_null = series.dropna()
    if not non_null.empty and non_null.map(
        lambda value: isinstance(value, (pd.Timestamp, datetime, date))
    ).all():
        return "datetime"
    return "object"


def _json_cell(value: object) -> object:
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported sandbox value type: {type(value).__name__}")
