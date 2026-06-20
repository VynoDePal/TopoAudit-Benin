from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    app_name: str = "TopoAudit Benin"
    database_url: str = "postgresql+psycopg://topoaudit:topoaudit@localhost:5432/topoaudit"
    frontend_url: str = "http://localhost:3000"
    local_storage_path: str = "/data/uploads"
    ocr_provider: str = "mock"
    azure_document_intelligence_endpoint: str = ""
    azure_document_intelligence_key: str = ""
    azure_document_intelligence_api_version: str = "2024-11-30"
    azure_document_intelligence_model_id: str = "prebuilt-layout"
    gemini_api_key: str = ""
    gemini_api_endpoint: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model: str = "gemini-2.5-flash"
    ocr_rate_limit_per_minute: int = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
