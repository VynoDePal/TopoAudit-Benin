from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.logging_security import install_sensitive_data_filter, register_secrets


class Settings(BaseSettings):
    app_env: str = "local"
    app_name: str = "TopoAudit Benin"
    database_url: str = "postgresql+psycopg://localhost:5432/topoaudit"
    frontend_url: str = "http://localhost:3000"
    local_storage_path: str = "/data/uploads"
    max_upload_mb: int = Field(default=25, gt=0)
    ocr_provider: str = "mock"
    azure_document_intelligence_endpoint: str = ""
    azure_document_intelligence_key: str = ""
    azure_document_intelligence_api_version: str = "2024-11-30"
    azure_document_intelligence_model_id: str = "prebuilt-layout"
    gemini_api_key: str = ""
    gemini_api_endpoint: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model: str = "gemma-4-31b-it"
    ocr_rate_limit_per_minute: int = 10
    # Sécurité (P1.1) : secret JWT + mode démo sans auth (jamais en production).
    jwt_secret: str = "dev-insecure-change-me"
    jwt_expires_seconds: int = Field(default=86400, gt=0)
    demo_local: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def demo_local_enabled(self) -> bool:
        """Mode démo sans auth : actif uniquement hors production."""
        return self.demo_local and self.app_env != "production"

    @model_validator(mode="after")
    def register_configured_secrets_for_log_redaction(self) -> "Settings":
        register_secrets(
            [
                self.azure_document_intelligence_key,
                self.gemini_api_key,
                self.jwt_secret,
            ]
        )
        install_sensitive_data_filter()
        return self


settings = Settings()
