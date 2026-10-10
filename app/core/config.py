import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "POSApp"
    app_env: str = "development"
    app_debug: bool = True
    session_timeout_minutes: int = 480

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @property
    def data_dir(self) -> Path:
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        path = base / self.app_name / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'pos.db'}"


settings = Settings()
