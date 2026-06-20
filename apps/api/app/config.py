from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    app_name: str = "TopoAudit Benin"
    database_url: str = "postgresql+psycopg://topoaudit:topoaudit@localhost:5432/topoaudit"
    frontend_url: str = "http://localhost:3000"
    local_storage_path: str = "/data/uploads"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
