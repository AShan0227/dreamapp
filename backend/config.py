from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/dreamapp.db"

    # LLM (OpenAI-compatible)
    llm_api_key: Optional[str] = None
    llm_base_url: str = "https://api.minimax.chat/v1"
    llm_model: str = "minimax-m2.5-highspeed"

    # Video Generation
    video_provider: str = "seedance"  # seedance | kling

    # Kling
    kling_access_key: Optional[str] = None
    kling_secret_key: Optional[str] = None
    kling_base_url: str = "https://openapi.klingai.com"

    # SeedDance
    seedance_api_key: Optional[str] = None
    seedance_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    seedance_model: str = "doubao-seedance-1-5-pro-251215"

    # Embeddings
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dim: int = 512
    embedding_cache_dir: str = "./models"

    # MinIO / Object Storage
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "dreamapp"
    minio_secret_key: str = "dreamapp_minio_secret"
    minio_bucket: str = "dreamapp-videos"
    minio_secure: bool = False

    # Storage
    video_storage_path: str = "./data/videos"

    # CORS — comma-separated list of allowed origins. "*" only for dev.
    # Example: "https://dreamapp.cn,https://www.dreamapp.cn"
    cors_origins: str = "*"

    # Auth — JWT signing secret (used by token rotation / OTP flow)
    auth_secret: str = "change-me-in-production"

    # Daily video generation cap per user
    daily_video_quota: int = 5

    model_config = {"env_file": ".env", "env_prefix": "DREAM_"}

    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
