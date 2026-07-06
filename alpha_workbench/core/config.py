"""项目配置 — 从 .env 加载环境变量。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def _getenv(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings:
    """AlphaWorkbench 统一项目配置。

    环境变量优先级：
    1. LLM_* / VISION_LLM_*：显式覆盖模型参数。
    2. DEEPSEEK_* / OPENAI_API_KEY：与仓库 .env 保持一致的默认 DeepSeek 配置，
       同时向后兼容旧的 OpenAI 变量名。
    3. 代码内默认值：保证未配置时也能运行 mock 链路。
    """

    def __init__(self) -> None:
        load_dotenv()
        self.base_dir = Path(_getenv("APP_BASE_DIR", str(BASE_DIR)))
        self.app_name = _getenv("APP_NAME", "AlphaWorkbench")
        self.data_dir = Path(_getenv("DATA_DIR", str(self.base_dir / "data")))
        self.environment = _getenv("ENV", "development").lower()
        self.log_level = _getenv("LOG_LEVEL", "INFO")
        self.log_to_console = _bool(_getenv("LOG_TO_CONSOLE", "false"))

        # LLM 配置：LLM_* 优先，否则回退到 DEEPSEEK_*，再向后兼容 OPENAI_*
        self.llm_provider = _getenv("LLM_PROVIDER", "deepseek")
        self.llm_model_id = _getenv(
            "LLM_MODEL_ID",
            _getenv("DEEPSEEK_MODEL", _getenv("MODEL_NAME", "deepseek-v4-flash")),
        )
        self.llm_api_key = _getenv(
            "LLM_API_KEY",
            _getenv("DEEPSEEK_API_KEY", _getenv("OPENAI_API_KEY", "")),
        )
        self.llm_base_url = _getenv(
            "LLM_BASE_URL",
            _getenv("DEEPSEEK_BASE_URL", _getenv("OPENAI_BASE_URL", "")),
        )

        # Vision LLM 配置：默认继承主 LLM
        self.vision_llm_provider = _getenv("VISION_LLM_PROVIDER", self.llm_provider)
        self.vision_llm_model_id = _getenv(
            "VISION_LLM_MODEL_ID",
            _getenv("VISION_DEEPSEEK_MODEL", self.llm_model_id),
        )
        self.vision_llm_api_key = _getenv(
            "VISION_LLM_API_KEY",
            _getenv("VISION_OPENAI_API_KEY", self.llm_api_key),
        )
        self.vision_llm_base_url = _getenv(
            "VISION_LLM_BASE_URL",
            _getenv("VISION_OPENAI_BASE_URL", self.llm_base_url),
        )

        # Mercury 交易级回测服务
        self.mercury_api_token = _getenv("MERCURY_API_TOKEN", "")
        self.mercury_base_url = _getenv("MERCURY_BASE_URL", "http://quant.futuri.top")

        # 应用级/鉴权/数据库配置（保留旧 Settings 字段以兼容既有代码）
        self.database_url = _getenv(
            "DATABASE_URL",
            f"sqlite:///{self.data_dir / 'app.db'}",
        )
        self.jwt_secret_key = _getenv("JWT_SECRET_KEY", "change-me")
        self.jwt_algorithm = _getenv("JWT_ALGORITHM", "HS256")
        self.access_token_expire_minutes = int(_getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
        self.session_cookie_name = _getenv("SESSION_COOKIE_NAME", "aw_session")
        self.session_cookie_secure = _bool(_getenv("SESSION_COOKIE_SECURE", "false"))
        self.session_cookie_samesite: str = _getenv("SESSION_COOKIE_SAMESITE", "strict").lower()

        # 旧 review/check 相关配置（保留以兼容可能的既有调用）
        self.max_check_items_per_batch = int(_getenv("MAX_CHECK_ITEMS_PER_BATCH", "64"))
        self.max_pages_per_check = int(_getenv("MAX_PAGES_PER_CHECK", "6"))
        self.max_pages_per_batch = int(_getenv("MAX_PAGES_PER_BATCH", "12"))
        self.max_visual_images_per_batch = int(_getenv("MAX_VISUAL_IMAGES_PER_BATCH", "4"))
        self.local_review_page_batch_size = int(_getenv("LOCAL_REVIEW_PAGE_BATCH_SIZE", "30"))
        self.segment_review_page_chars = int(_getenv("SEGMENT_REVIEW_PAGE_CHARS", "2000"))
        self.global_anchor_page_chars = int(_getenv("GLOBAL_ANCHOR_PAGE_CHARS", "500"))

        self.reference_doc_path = Path(
            _getenv(
                "REFERENCE_DOC_PATH",
                str(self.base_dir / "source" / "common-problems-for-students.md"),
            )
        )
        self.max_pages = int(_getenv("MAX_PAGES", "120"))
        self.max_page_chars = int(_getenv("MAX_PAGE_CHARS", "4000"))
        self.cors_origins = _csv(
            _getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
        )

    def is_dev(self) -> bool:
        return self.environment in {"development", "dev"}


settings = Settings()
