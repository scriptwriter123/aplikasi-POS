import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "POSApp"
    app_env: str = "development"
    app_debug: bool = True
    session_timeout_minutes: int = 480
    midtrans_server_key: str | None = None
    midtrans_notification_url: str | None = None
    dana_partner_id: str | None = None
    dana_merchant_id: str | None = None
    dana_private_key: str | None = None
    dana_base_url: str = "https://gateway-mp-sit.dana.id"
    pos_data_dir: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @property
    def data_dir(self) -> Path:
        if self.pos_data_dir:
            path = Path(self.pos_data_dir).expanduser()
            if not path.is_absolute():
                path = Path.cwd() / path
        else:
            base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            path = base / self.app_name / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'pos.db'}"


settings = Settings()
