from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "Partner Expense Control ERP"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql+psycopg://pec:pec@localhost:5432/pec_erp"

    JWT_SECRET_KEY: str = "change-me-in-env"  # never used outside local dev
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    CORS_ORIGINS: str = "http://localhost:3000"

    STORAGE_BACKEND: str = "local"  # local | s3
    STORAGE_LOCAL_PATH: str = "./storage"
    STORAGE_S3_BUCKET: str = ""
    MAX_UPLOAD_MB: int = 10
    ALLOWED_UPLOAD_TYPES: str = "application/pdf,image/png,image/jpeg,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    BASE_CURRENCY: str = "USD"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_upload_types(self) -> set[str]:
        return {t.strip() for t in self.ALLOWED_UPLOAD_TYPES.split(",") if t.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
