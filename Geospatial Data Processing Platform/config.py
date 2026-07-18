"""Environment-backed runtime configuration for MapWork.ai."""

import os
from dataclasses import dataclass
from typing import Dict

from dotenv import load_dotenv


load_dotenv()


def environment_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    log_level: str = "INFO"
    postgres_host: str = ""
    postgres_port: int = 5432
    postgres_database: str = ""
    postgres_user: str = ""
    postgres_password: str = ""
    mapbox_token: str = ""
    planet_api_key: str = ""
    sentinel_instance_id: str = ""

    @classmethod
    def from_environment(cls) -> "Config":
        return cls(
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
            debug=environment_flag("FLASK_DEBUG"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            postgres_host=os.getenv("POSTGRES_HOST", os.getenv("DB_HOST", "")),
            postgres_port=int(os.getenv("POSTGRES_PORT", os.getenv("DB_PORT", "5432"))),
            postgres_database=os.getenv("POSTGRES_DB", ""),
            postgres_user=os.getenv("POSTGRES_USER", ""),
            postgres_password=os.getenv("POSTGRES_PASSWORD", ""),
            mapbox_token=os.getenv("MAPBOX_TOKEN", ""),
            planet_api_key=os.getenv("PL_API_KEY", ""),
            sentinel_instance_id=os.getenv("SENTINEL_HUB_INSTANCE_ID", ""),
        )

    @property
    def database_configured(self) -> bool:
        return all((self.postgres_host, self.postgres_database, self.postgres_user, self.postgres_password))

    @property
    def database_parameters(self) -> Dict[str, object]:
        return {
            "host": self.postgres_host,
            "port": self.postgres_port,
            "dbname": self.postgres_database,
            "user": self.postgres_user,
            "password": self.postgres_password,
        }

    def integration_status(self) -> Dict[str, Dict[str, bool]]:
        return {
            "postgis": {"configured": self.database_configured},
            "mapbox": {"configured": bool(self.mapbox_token)},
            "planet": {"configured": bool(self.planet_api_key)},
            "sentinel_hub": {"configured": bool(self.sentinel_instance_id)},
        }
