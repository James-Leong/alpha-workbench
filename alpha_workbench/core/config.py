"""项目配置 — 采用 pydantic-settings 按功能分类管理。

所有环境变量统一在此读取；FastAPI / Streamlit / CLI 都通过
`from alpha_workbench.core.config import settings` 或 `get_settings()` 获取配置。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


def _csv(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


class AppSettings(BaseSettings):
    """应用基础配置。"""

    model_config = SettingsConfigDict(env_prefix="APP_")

    name: str = "AlphaWorkbench"
    base_dir: Path = BASE_DIR
    data_dir: Path | None = Field(default=None, alias="DATA_DIR")
    environment: str = Field(default="development", alias="ENV")

    @field_validator("base_dir", "data_dir", mode="before")
    @classmethod
    def _coerce_path(cls, v: Any) -> Any:
        return Path(v) if v is not None else None


class LoggingSettings(BaseSettings):
    """日志配置。

    兼容旧的环境变量名 ALPHA_LOG_LEVEL：当 LOG_LEVEL 未设置时回退到 ALPHA_LOG_LEVEL。
    """

    model_config = SettingsConfigDict(env_prefix="LOG_")

    level: str = Field(
        default_factory=lambda: (
            os.getenv("LOG_LEVEL") or os.getenv("ALPHA_LOG_LEVEL") or "INFO"
        ),
        alias="LOG_LEVEL",
    )
    to_console: bool = False
    to_file: bool = True
    json_enabled: bool = True
    dir: Path | None = Field(default=None, alias="LOG_DIR")
    rotation_max_bytes: int = 10 * 1024 * 1024
    rotation_backup_count: int = 5

    @field_validator("dir", mode="before")
    @classmethod
    def _coerce_path(cls, v: Any) -> Any:
        return Path(v) if v is not None else None


class DatabaseSettings(BaseSettings):
    """数据库配置。"""

    model_config = SettingsConfigDict(env_prefix="DATABASE_")

    url: str = Field(
        default_factory=lambda: f"sqlite:///{BASE_DIR / 'data' / 'alpha_workbench.sqlite3'}"
    )


class ApiSettings(BaseSettings):
    """FastAPI / 前后端对接配置。"""

    frontend_base_url: str = Field(
        default="http://localhost:5173", alias="FRONTEND_BASE_URL"
    )
    backend_base_url: str = Field(
        default="http://localhost:8000", alias="BACKEND_BASE_URL"
    )
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"],
        alias="CORS_ALLOWED_ORIGINS",
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        return _csv(v)


class AuthSettings(BaseSettings):
    """鉴权 / Session / OAuth 配置。"""

    app_secret_key: str = Field(default="dev-only-change-me", alias="APP_SECRET_KEY")
    jwt_secret_key: str = Field(default="change-me", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    session_cookie_name: str = Field(default="aw_session", alias="SESSION_COOKIE_NAME")
    session_cookie_secure: bool = Field(
        default=False, alias="SESSION_COOKIE_SECURE"
    )
    session_cookie_samesite: str = Field(
        default="strict", alias="SESSION_COOKIE_SAMESITE"
    )
    session_ttl_hours: int = Field(default=168, alias="SESSION_TTL_HOURS")
    github_client_id: str = Field(default="", alias="GITHUB_CLIENT_ID")
    github_client_secret: str = Field(default="", alias="GITHUB_CLIENT_SECRET")


class LlmSettings(BaseSettings):
    """主 LLM 配置。

    优先读取 LLM_*；未设置时回退到 DEEPSEEK_* / OPENAI_*。
    """

    model_config = SettingsConfigDict(env_prefix="LLM_")

    provider: str = "deepseek"
    model_id: str = Field(
        default_factory=lambda: (
            os.getenv("LLM_MODEL_ID")
            or os.getenv("DEEPSEEK_MODEL")
            or os.getenv("MODEL_NAME")
            or "deepseek-v4-flash"
        )
    )
    api_key: str = Field(
        default_factory=lambda: (
            os.getenv("LLM_API_KEY")
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or ""
        )
    )
    base_url: str = Field(
        default_factory=lambda: (
            os.getenv("LLM_BASE_URL")
            or os.getenv("DEEPSEEK_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or ""
        )
    )


class VisionLlmSettings(BaseSettings):
    """Vision LLM 配置。

    未设置时默认继承主 LLM 配置。
    """

    model_config = SettingsConfigDict(env_prefix="VISION_LLM_")

    provider: str = ""
    model_id: str = ""
    api_key: str = ""
    base_url: str = ""


class MercurySettings(BaseSettings):
    """Mercury 交易级回测服务配置。"""

    model_config = SettingsConfigDict(env_prefix="MERCURY_")

    api_token: str = ""
    base_url: str = "http://quant.futuri.top"


class FactorCodeSettings(BaseSettings):
    """因子代码生成（Codex）配置。"""

    model_config = SettingsConfigDict(env_prefix="FACTOR_CODE_")

    agent: str = "codex"
    timeout_seconds: int = 600
    jobs_dir: Path | None = None
    plugin_registry_dir: Path | None = None

    @field_validator("jobs_dir", "plugin_registry_dir", mode="before")
    @classmethod
    def _coerce_path(cls, v: Any) -> Any:
        return Path(v) if v is not None else None


class ReviewSettings(BaseSettings):
    """PDF / 文档 review 相关配置。"""

    max_check_items_per_batch: int = Field(
        default=64, alias="MAX_CHECK_ITEMS_PER_BATCH"
    )
    max_pages_per_check: int = Field(default=6, alias="MAX_PAGES_PER_CHECK")
    max_pages_per_batch: int = Field(default=12, alias="MAX_PAGES_PER_BATCH")
    max_visual_images_per_batch: int = Field(
        default=4, alias="MAX_VISUAL_IMAGES_PER_BATCH"
    )
    local_review_page_batch_size: int = Field(
        default=30, alias="LOCAL_REVIEW_PAGE_BATCH_SIZE"
    )
    segment_review_page_chars: int = Field(
        default=2000, alias="SEGMENT_REVIEW_PAGE_CHARS"
    )
    global_anchor_page_chars: int = Field(
        default=500, alias="GLOBAL_ANCHOR_PAGE_CHARS"
    )


class ReferenceSettings(BaseSettings):
    """参考文档相关配置。"""

    doc_path: Path = Field(
        default_factory=lambda: BASE_DIR / "source" / "common-problems-for-students.md",
        alias="REFERENCE_DOC_PATH",
    )
    max_pages: int = Field(default=120, alias="MAX_PAGES")
    max_page_chars: int = Field(default=4000, alias="MAX_PAGE_CHARS")

    @field_validator("doc_path", mode="before")
    @classmethod
    def _coerce_path(cls, v: Any) -> Path:
        return Path(v)


class Settings(BaseSettings):
    """AlphaWorkbench 统一配置入口。

    使用嵌套的 BaseSettings 子类按功能分类，同时通过@property提供
    向后兼容的扁平访问接口，避免一次性修改大量现有代码。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app: AppSettings = AppSettings()
    logging: LoggingSettings = LoggingSettings()
    database: DatabaseSettings = DatabaseSettings()
    api: ApiSettings = ApiSettings()
    auth: AuthSettings = AuthSettings()
    llm: LlmSettings = LlmSettings()
    vision_llm: VisionLlmSettings = VisionLlmSettings()
    mercury: MercurySettings = MercurySettings()
    factor_code: FactorCodeSettings = FactorCodeSettings()
    review: ReviewSettings = ReviewSettings()
    reference: ReferenceSettings = ReferenceSettings()

    @model_validator(mode="after")
    def _derive_defaults(self) -> "Settings":
        """根据 base_dir / data_dir 推导路径默认值，并处理 Vision LLM 继承。"""

        if self.app.data_dir is None:
            self.app.data_dir = self.app.base_dir / "data"
        if self.logging.dir is None:
            self.logging.dir = self.app.base_dir / "logs"
        if self.factor_code.jobs_dir is None:
            self.factor_code.jobs_dir = self.app.base_dir / "runs" / "factor_code_jobs"
        if self.factor_code.plugin_registry_dir is None:
            self.factor_code.plugin_registry_dir = (
                self.app.base_dir / "runs" / "factor_plugins"
            )

        # Vision LLM 未设置时继承主 LLM
        if not self.vision_llm.provider:
            self.vision_llm.provider = self.llm.provider
        if not self.vision_llm.model_id:
            self.vision_llm.model_id = self.llm.model_id
        if not self.vision_llm.api_key:
            self.vision_llm.api_key = self.llm.api_key
        if not self.vision_llm.base_url:
            self.vision_llm.base_url = self.llm.base_url

        return self

    # ------------------------------------------------------------------
    # 向后兼容的扁平属性
    # ------------------------------------------------------------------
    @property
    def log_level(self) -> str:
        return self.logging.level

    @property
    def log_to_console(self) -> bool:
        return self.logging.to_console

    @property
    def base_dir(self) -> Path:
        return self.app.base_dir

    @property
    def data_dir(self) -> Path:
        return self.app.data_dir

    @property
    def app_name(self) -> str:
        return self.app.name

    @property
    def environment(self) -> str:
        return self.app.environment

    @property
    def database_url(self) -> str:
        return self.database.url

    @property
    def cors_origins(self) -> list[str]:
        return self.api.allowed_origins

    @property
    def app_secret_key(self) -> str:
        return self.auth.app_secret_key

    @property
    def jwt_secret_key(self) -> str:
        return self.auth.jwt_secret_key

    @property
    def jwt_algorithm(self) -> str:
        return self.auth.jwt_algorithm

    @property
    def access_token_expire_minutes(self) -> int:
        return self.auth.access_token_expire_minutes

    @property
    def session_cookie_name(self) -> str:
        return self.auth.session_cookie_name

    @property
    def session_cookie_secure(self) -> bool:
        return self.auth.session_cookie_secure

    @property
    def session_cookie_samesite(self) -> str:
        return self.auth.session_cookie_samesite

    @property
    def cookie_secure(self) -> bool:
        return self.auth.session_cookie_secure

    @property
    def session_ttl_hours(self) -> int:
        return self.auth.session_ttl_hours

    @property
    def allowed_origins(self) -> list[str]:
        return self.api.allowed_origins

    @property
    def frontend_base_url(self) -> str:
        return self.api.frontend_base_url

    @property
    def backend_base_url(self) -> str:
        return self.api.backend_base_url

    @property
    def github_client_id(self) -> str:
        return self.auth.github_client_id

    @property
    def github_client_secret(self) -> str:
        return self.auth.github_client_secret

    # LLM
    @property
    def llm_provider(self) -> str:
        return self.llm.provider

    @property
    def llm_model_id(self) -> str:
        return self.llm.model_id

    @property
    def llm_api_key(self) -> str:
        return self.llm.api_key

    @property
    def llm_base_url(self) -> str:
        return self.llm.base_url

    # Vision LLM
    @property
    def vision_llm_provider(self) -> str:
        return self.vision_llm.provider

    @property
    def vision_llm_model_id(self) -> str:
        return self.vision_llm.model_id

    @property
    def vision_llm_api_key(self) -> str:
        return self.vision_llm.api_key

    @property
    def vision_llm_base_url(self) -> str:
        return self.vision_llm.base_url

    # Mercury
    @property
    def mercury_api_token(self) -> str:
        return self.mercury.api_token

    @property
    def mercury_base_url(self) -> str:
        return self.mercury.base_url

    # Factor code
    @property
    def factor_code_agent(self) -> str:
        return self.factor_code.agent

    @property
    def factor_code_timeout_seconds(self) -> int:
        return self.factor_code.timeout_seconds

    @property
    def factor_code_jobs_dir(self) -> Path:
        return self.factor_code.jobs_dir

    @property
    def factor_plugin_registry_dir(self) -> Path:
        return self.factor_code.plugin_registry_dir

    # Review
    @property
    def max_check_items_per_batch(self) -> int:
        return self.review.max_check_items_per_batch

    @property
    def max_pages_per_check(self) -> int:
        return self.review.max_pages_per_check

    @property
    def max_pages_per_batch(self) -> int:
        return self.review.max_pages_per_batch

    @property
    def max_visual_images_per_batch(self) -> int:
        return self.review.max_visual_images_per_batch

    @property
    def local_review_page_batch_size(self) -> int:
        return self.review.local_review_page_batch_size

    @property
    def segment_review_page_chars(self) -> int:
        return self.review.segment_review_page_chars

    @property
    def global_anchor_page_chars(self) -> int:
        return self.review.global_anchor_page_chars

    # Reference
    @property
    def reference_doc_path(self) -> Path:
        return self.reference.doc_path

    @property
    def max_pages(self) -> int:
        return self.reference.max_pages

    @property
    def max_page_chars(self) -> int:
        return self.reference.max_page_chars

    @property
    def is_dev(self) -> bool:
        return self.app.environment in {"development", "dev", "local"}


@lru_cache
def get_settings() -> Settings:
    """返回进程内唯一的 Settings 实例。"""
    return Settings()


settings = get_settings()
