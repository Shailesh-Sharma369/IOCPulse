import os
from pydantic_settings import BaseSettings
from pathlib import Path
from typing import List

class Settings(BaseSettings):
    DB_PATH: str = "../data/raw_repository.db"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True
    LLM_SERVER_URL: str = "http://localhost:8000"
    
    # Comma-separated list of allowed origins for CORS
    # Example: "https://frontend-domain.com,http://localhost:3000"
    ALLOWED_ORIGINS: str = "*"  # default to all for development

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    def get_cors_origins(self) -> List[str]:
        if self.ALLOWED_ORIGINS == "*":
            return ["*"]
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

settings = Settings()

# Validate DB_PATH at startup
db_path = Path(settings.DB_PATH)
if not db_path.exists():
    # The database will be created by DatabaseClient on first connection; just warn.
    print(f"Warning: Database file not found at {db_path}. It will be created automatically.")