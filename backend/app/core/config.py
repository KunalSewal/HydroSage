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

    open_meteo_base_url: str = "https://archive-api.open-meteo.com"

    overpass_base_url: str = "https://overpass-api.de"

    # Comma-separated -- e.g. "https://hydrosage.example.com,http://localhost:5173".
    # Defaults cover local dev only; a real deployment must set this to the
    # frontend's actual public URL or the browser will silently block every
    # request (this exact bug already shipped once this project -- see
    # docs/DECISIONS.md D-005's CORS fix -- so it's a setting, not a
    # hardcoded list, specifically to avoid repeating it per-environment).
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
