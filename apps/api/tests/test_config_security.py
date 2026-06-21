import logging

from app.config import Settings
from app.logging_security import install_sensitive_data_filter, sanitize_for_logging


def test_default_settings_do_not_embed_database_credentials(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = Settings()

    assert "@" not in settings.database_url
    assert "topoaudit:topoaudit" not in settings.database_url


def test_sanitize_for_logging_redacts_api_keys_and_authorization_headers():
    secret_payload = {
        "x-goog-api-key": "gemini-secret-value",
        "Authorization": "Bearer azure-secret-value",
        "nested": {"safe": "visible"},
    }

    sanitized = sanitize_for_logging(secret_payload)

    assert sanitized["x-goog-api-key"] == "[REDACTED]"
    assert sanitized["Authorization"] == "[REDACTED]"
    assert sanitized["nested"]["safe"] == "visible"


def test_log_filter_redacts_api_keys_from_log_messages(caplog, monkeypatch):
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "azure-secret-value")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret-value")
    Settings()
    install_sensitive_data_filter()

    logger = logging.getLogger("tests.config_security")
    with caplog.at_level(logging.INFO, logger=logger.name):
        logger.info(
            "headers=%s url=%s authorization=%s",
            {"Ocp-Apim-Subscription-Key": "azure-secret-value", "x-goog-api-key": "gemini-secret-value"},
            "https://example.test?api_key=gemini-secret-value",
            "Bearer azure-secret-value",
        )

    log_output = caplog.text
    assert "azure-secret-value" not in log_output
    assert "gemini-secret-value" not in log_output
    assert "[REDACTED]" in log_output
