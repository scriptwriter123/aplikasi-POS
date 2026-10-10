import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


def upgrade_database() -> None:
    if getattr(sys, "frozen", False):
        project_root = Path(sys._MEIPASS)
    else:
        project_root = Path(__file__).resolve().parents[2]

    config_path = project_root / "alembic.ini"
    migrations_path = project_root / "migrations"
    if not config_path.is_file() or not migrations_path.is_dir():
        raise FileNotFoundError(
            "File konfigurasi migrasi database tidak ditemukan."
        )

    config = Config(str(config_path))
    config.set_main_option("script_location", str(migrations_path))
    command.upgrade(config, "head")
