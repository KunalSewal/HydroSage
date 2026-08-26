from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "HydroSage API"
    environment: str = "development"

    database_url: str = "postgresql+psycopg://hydrosage:hydrosage@localhost:5432/hydrosage"

    redis_url: str = "redis://localhost:6379/0"

    object_storage_endpoint: str = "localhost:9000"
    object_storage_access_key: str = "hydrosage"
    object_storage_secret_key: str = "hydrosage_dev_secret"
    object_storage_bucket: str = "hydrosage-rasters"
    object_storage_secure: bool = False

    elevation_api_base_url: str = "https://openzenith.cyopsys.com/api/elevation"

    opentopography_api_key: str = ""
    opentopography_base_url: str = "https://portal.opentopography.org/API"

    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    nominatim_user_agent: str = "HydroSage/0.1 (student project, IIT Bhilai)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
