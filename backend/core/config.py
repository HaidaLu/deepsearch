# core/config.py — App settings loaded from .env
# Java equivalent: application.properties + @Value / @ConfigurationProperties

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173"]

    # Database — SQLite for local dev without Docker, PostgreSQL in production
    DATABASE_URL: str = "sqlite+aiosqlite:///./deepsearch.db"

    # Elasticsearch
    ES_HOST: str = "http://localhost:9200"
    ES_INDEX: str = "deepsearch"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # JWT Auth
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # LLM providers
    OPENAI_API_KEY: str = ""
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_PROVIDER: str = "dashscope"  # "openai" or "dashscope"
    LLM_MODEL: str = "deepseek-r1"

    # Embedding — same DashScope key and base URL, different model
    EMBEDDING_API_KEY: str = ""  # falls back to DASHSCOPE_API_KEY if empty
    EMBEDDING_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    EMBEDDING_MODEL: str = "text-embedding-v4"

    class Config:
        env_file = ".env"


settings = Settings()
