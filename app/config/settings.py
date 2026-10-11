from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # Database: DATABASE_URL wins (Railway/Heroku style postgres:// URLs are accepted);
    # otherwise a Postgres URL is assembled from the POSTGRES_* fields.
    DATABASE_URL: str | None = None
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "excel2whatsapp"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    # Queue: when no broker URL is set, campaigns are sent by in-process background threads.
    REDIS_URL: str | None = None
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None

    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # WhatsApp Cloud API
    ACCESS_TOKEN: str
    PHONE_NUMBER_ID: str
    VERIFY_TOKEN: str
    # Meta app secret; when set, incoming webhooks must carry a valid X-Hub-Signature-256.
    APP_SECRET: str | None = None

    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ENV: str = "development"


settings = Settings()
