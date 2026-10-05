import os
from pydantic_settings import BaseSettings
from pathlib import Path
from typing import List


class Settings(BaseSettings):
    DB_PATH: str = "../data/ioc_pulse.db"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True

    # Comma-separated list of allowed origins for CORS
    ALLOWED_ORIGINS: str = "*"

    # ---- CVE enrichment (Phase 3) ----
    # Optional. If empty, NVD requests are made without an API key and are
    # aggressively rate-limited (5 req / 30 s). Set a free key for 50 req / 30 s.
    # Request one at: https://nvd.nist.gov/developers/request-an-api-key
    NVD_API_KEY: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    def get_cors_origins(self) -> List[str]:
        if self.ALLOWED_ORIGINS == "*":
            return ["*"]
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()

db_path = Path(settings.DB_PATH)
if not db_path.exists():
    print(f"Warning: Database file not found at {db_path}. It will be created automatically.")