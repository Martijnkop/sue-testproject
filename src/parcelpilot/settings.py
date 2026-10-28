from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/parcelpilot",
        description="PostgreSQL connection string",
    )
    jwt_secret: str = Field(default="change-me", description="JWT signing secret")
    seed_enabled: bool = Field(default=False, description="Allow seed endpoints")
    seed_key: str = Field(default="dev-seed", description="Seed endpoint authorization key")
    log_level: str = Field(default="INFO", description="Application log level")
    bcrypt_rounds: int = Field(default=12, description="bcrypt cost factor")
    export_hmac_key: str = Field(default="change-me", description="HMAC secret for exports")
    graph_max_events: int = Field(default=1000, description="Maximum in-memory shipment graph events")

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()
