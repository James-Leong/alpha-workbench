"""SQLite persistence for field-oriented long-format data."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import date, datetime
import json
from pathlib import Path
from threading import RLock
from typing import Any

import pandas as pd

from alpha_workbench.data_sdk.base import LONG_FORMAT_COLUMNS, normalize_long_frame


class SQLiteStore:
    """Persist standard fields in one indexed SQLite observation table."""

    name = "sqlite"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path) if str(path) != ":memory:" else Path(":memory:")
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS observations (
                field TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                value,
                PRIMARY KEY (field, trade_date, symbol)
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS query_snapshots (
                field TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                symbols_json TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                PRIMARY KEY (field, start_date, end_date, symbols_json)
            )
            """
        )
        self._connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_observations_lookup
            ON observations (field, trade_date, symbol)
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS field_metadata (
                field TEXT PRIMARY KEY,
                value_type TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    @staticmethod
    def _sqlite_value(value: Any) -> Any:
        if pd.isna(value):
            return None
        if isinstance(value, (pd.Timestamp, datetime, date)):
            return value.isoformat()
        if hasattr(value, "item"):
            return value.item()
        return value

    @staticmethod
    def _value_type(values: pd.Series) -> str:
        if pd.api.types.is_datetime64_any_dtype(values.dtype):
            return "datetime"
        non_null = values.dropna()
        if non_null.empty:
            return "unknown"
        if non_null.map(lambda value: isinstance(value, (pd.Timestamp, datetime, date))).all():
            return "datetime"
        if pd.api.types.is_bool_dtype(non_null.dtype):
            return "boolean"
        if pd.api.types.is_integer_dtype(non_null.dtype):
            return "integer"
        if pd.api.types.is_numeric_dtype(non_null.dtype):
            return "real"
        return "text"

    def save(self, field: str, data: pd.DataFrame) -> None:
        if not field or not field.strip():
            raise ValueError("field must be a non-empty string")
        frame = normalize_long_frame(data)
        with self._lock, self._connection:
            self._write_frame(field, frame)

    def replace_scope(
        self,
        field: str,
        data: pd.DataFrame,
        *,
        start_date: str | pd.Timestamp | None = None,
        end_date: str | pd.Timestamp | None = None,
        symbols: Sequence[str] | None = None,
    ) -> None:
        """Atomically replace one cached query scope and record its snapshot."""

        if not field or not field.strip():
            raise ValueError("field must be a non-empty string")
        frame = normalize_long_frame(data)
        clauses = ["field = ?"]
        parameters: list[Any] = [field]
        if start_date is not None:
            clauses.append("trade_date >= ?")
            parameters.append(pd.Timestamp(start_date).normalize().strftime("%Y-%m-%d"))
        if end_date is not None:
            clauses.append("trade_date <= ?")
            parameters.append(pd.Timestamp(end_date).normalize().strftime("%Y-%m-%d"))
        if symbols is not None:
            symbol_values = [str(symbol) for symbol in symbols]
            if symbol_values:
                clauses.append(f"symbol IN ({','.join('?' for _ in symbol_values)})")
                parameters.extend(symbol_values)
            else:
                clauses.append("0 = 1")
        key = self._snapshot_key(field, start_date, end_date, symbols)
        with self._lock, self._connection:
            self._connection.execute(
                f"DELETE FROM observations WHERE {' AND '.join(clauses)}",
                parameters,
            )
            self._write_frame(field, frame)
            self._connection.execute(
                """
                INSERT INTO query_snapshots (
                    field, start_date, end_date, symbols_json, row_count
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(field, start_date, end_date, symbols_json)
                DO UPDATE SET row_count = excluded.row_count
                """,
                (*key, len(frame)),
            )

    def _write_frame(self, field: str, frame: pd.DataFrame) -> None:
        value_type = self._value_type(frame["value"])
        rows = [
            (
                field,
                row.trade_date.strftime("%Y-%m-%d"),
                row.symbol,
                self._sqlite_value(row.value),
            )
            for row in frame.itertuples(index=False)
        ]
        if value_type != "unknown":
            existing = self._connection.execute(
                "SELECT value_type FROM field_metadata WHERE field = ?", (field,)
            ).fetchone()
            if existing is not None and existing[0] != value_type:
                raise TypeError(
                    f"field {field!r} is stored as {existing[0]}, cannot save {value_type} values"
                )
            self._connection.execute(
                """
                INSERT INTO field_metadata (field, value_type)
                VALUES (?, ?)
                ON CONFLICT(field) DO UPDATE SET value_type = excluded.value_type
                """,
                (field, value_type),
            )
        self._connection.executemany(
            """
            INSERT INTO observations (field, trade_date, symbol, value)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(field, trade_date, symbol)
            DO UPDATE SET value = excluded.value
            """,
            rows,
        )

    def load(
        self,
        field: str,
        *,
        start_date: str | pd.Timestamp | None = None,
        end_date: str | pd.Timestamp | None = None,
        symbols: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        if not field or not field.strip():
            raise ValueError("field must be a non-empty string")
        if symbols is not None and not symbols:
            return pd.DataFrame(columns=list(LONG_FORMAT_COLUMNS))

        clauses = ["field = ?"]
        parameters: list[Any] = [field]
        if start_date is not None:
            clauses.append("trade_date >= ?")
            parameters.append(pd.Timestamp(start_date).normalize().strftime("%Y-%m-%d"))
        if end_date is not None:
            clauses.append("trade_date <= ?")
            parameters.append(pd.Timestamp(end_date).normalize().strftime("%Y-%m-%d"))
        if symbols is not None:
            symbol_values = [str(symbol) for symbol in symbols]
            clauses.append(f"symbol IN ({','.join('?' for _ in symbol_values)})")
            parameters.extend(symbol_values)

        query = f"""
            SELECT trade_date, symbol, value
            FROM observations
            WHERE {' AND '.join(clauses)}
            ORDER BY trade_date, symbol
        """
        with self._lock:
            frame = pd.read_sql_query(query, self._connection, params=parameters)
            metadata = self._connection.execute(
                "SELECT value_type FROM field_metadata WHERE field = ?", (field,)
            ).fetchone()
        if frame.empty:
            return pd.DataFrame(columns=list(LONG_FORMAT_COLUMNS))
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        value_type = metadata[0] if metadata is not None else "unknown"
        if value_type == "datetime":
            frame["value"] = pd.to_datetime(frame["value"])
        elif value_type in {"integer", "real"}:
            frame["value"] = pd.to_numeric(frame["value"])
        elif value_type == "boolean":
            frame["value"] = frame["value"].astype("boolean")
        return frame.loc[:, LONG_FORMAT_COLUMNS]

    def fields(self) -> tuple[str, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT DISTINCT field FROM observations ORDER BY field"
            ).fetchall()
        return tuple(row[0] for row in rows)

    def has_snapshot(
        self,
        field: str,
        *,
        start_date: str | pd.Timestamp | None = None,
        end_date: str | pd.Timestamp | None = None,
        symbols: Sequence[str] | None = None,
    ) -> bool:
        key = self._snapshot_key(field, start_date, end_date, symbols)
        with self._lock:
            row = self._connection.execute(
                """
                SELECT 1 FROM query_snapshots
                WHERE field = ? AND start_date = ? AND end_date = ? AND symbols_json = ?
                """,
                key,
            ).fetchone()
        return row is not None

    def record_snapshot(
        self,
        field: str,
        *,
        start_date: str | pd.Timestamp | None = None,
        end_date: str | pd.Timestamp | None = None,
        symbols: Sequence[str] | None = None,
        row_count: int,
    ) -> None:
        if row_count < 0:
            raise ValueError("row_count cannot be negative")
        key = self._snapshot_key(field, start_date, end_date, symbols)
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO query_snapshots (
                    field, start_date, end_date, symbols_json, row_count
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(field, start_date, end_date, symbols_json)
                DO UPDATE SET row_count = excluded.row_count
                """,
                (*key, row_count),
            )

    @staticmethod
    def _snapshot_key(
        field: str,
        start_date: str | pd.Timestamp | None,
        end_date: str | pd.Timestamp | None,
        symbols: Sequence[str] | None,
    ) -> tuple[str, str, str, str]:
        if not field or not field.strip():
            raise ValueError("field must be a non-empty string")
        start = "" if start_date is None else pd.Timestamp(start_date).normalize().date().isoformat()
        end = "" if end_date is None else pd.Timestamp(end_date).normalize().date().isoformat()
        normalized_symbols = None if symbols is None else sorted({str(item) for item in symbols})
        return (
            field,
            start,
            end,
            json.dumps(normalized_symbols, ensure_ascii=True, separators=(",", ":")),
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> SQLiteStore:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()
