from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Signalboard"
    database_url: str = "sqlite:///./data/signalboard.db"
    max_upload_size_mb: int = 8
    allowed_extensions: str = "pdf,docx,txt"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_extension_set(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_extensions.split(",")}


@lru_cache
def get_settings() -> Settings:
    return Settings()
