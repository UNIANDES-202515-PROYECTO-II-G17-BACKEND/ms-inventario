from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SERVICE_NAME: str = "ms-compras"
    VERSION: str = "0.1.0"

    # GCP
    GCP_PROJECT: str = "misw4301-g26"
    GCP_REGION: str = "us-central1"

    # Sharding por paÃ­s (CO, MX, EC, PE)
    DATABASE_URL_CO: str | None = None
    DATABASE_URL_MX: str | None = None
    DATABASE_URL_EC: str | None = None
    DATABASE_URL_PE: str | None = None

    # Redis
    REDIS_URL: str | None = None

    # Pub/Sub
    PUBSUB_TOPIC: str | None = None

    # BigQuery / Bigtable / GCS
    BQ_DATASET: str | None = None
    BT_INSTANCE: str | None = None
    GCS_BUCKET: str | None = None
    GCS_FOLDER: str | None = None

    class Config:
        env_file = ".env"

settings = Settings()
