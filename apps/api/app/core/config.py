from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=API_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://devdocs:devdocs@127.0.0.1:5432/devdocs_ai"
    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    cookie_name: str = "devdocs_session"
    cookie_secure: bool = False
    session_days: int = Field(default=7, ge=1, le=30)
    upload_dir: Path = API_ROOT / "storage" / "uploads"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=10 * 1024 * 1024)
    siliconflow_api_key: SecretStr | None = None
    embedding_batch_size: int = Field(default=16, ge=1, le=16)
    indexing_timeout_seconds: int = Field(default=60, ge=5, le=90)
    chat_model: str = Field(default="deepseek-ai/DeepSeek-V4-Flash", min_length=1, max_length=128)
    chat_max_tokens: int = Field(default=1024, ge=128, le=4096)
    chat_timeout_seconds: int = Field(default=90, ge=5, le=90)
    retrieval_top_k: int = Field(default=5, ge=1, le=8)
    retrieval_min_similarity: float = Field(default=0.35, ge=0, le=1)
    daily_chat_limit: int = Field(default=50, ge=1, le=1000000)
    daily_index_limit: int = Field(default=20, ge=1, le=1000000)

    @field_validator("upload_dir")
    @classmethod
    def absolute_upload_dir(cls, value: Path) -> Path:
        return (value if value.is_absolute() else API_ROOT / value).resolve()
