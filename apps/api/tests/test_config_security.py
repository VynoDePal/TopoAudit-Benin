from app.config import Settings


def test_default_settings_do_not_embed_database_credentials(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = Settings()

    assert "@" not in settings.database_url
    assert "topoaudit:topoaudit" not in settings.database_url
