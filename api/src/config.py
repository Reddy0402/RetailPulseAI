from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    app_name: str = "Store Intelligence Analytics API"
    environment: str = "production"
    
    # PostgreSQL Configuration
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "store_intelligence"
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    
    # Computed Database URL
    database_url: str = Field(default="")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def get_db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

settings = Settings()
