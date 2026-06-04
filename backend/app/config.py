from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./onlinetools.db"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    storage_path: str = "./storage"
    cors_origins: str = "http://localhost:3000"
    max_upload_bytes: int = 50 * 1024 * 1024
    tesseract_cmd: str | None = None  # e.g. /opt/homebrew/bin/tesseract

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
