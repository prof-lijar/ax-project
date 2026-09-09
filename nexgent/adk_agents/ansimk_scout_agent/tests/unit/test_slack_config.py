from app.config import ScoutSettings


def test_slack_env_is_trimmed_and_token_not_in_repr(monkeypatch):
    monkeypatch.setenv("SCOUT_SLACK_BOT_TOKEN", "  secret-token  ")
    monkeypatch.setenv("SCOUT_SLACK_CHANNEL_ID", " C123 ")
    settings = ScoutSettings.from_env()
    assert settings.slack_bot_token == "secret-token"
    assert settings.slack_channel_id == "C123"
    assert "secret-token" not in repr(settings)
    monkeypatch.setenv("SCOUT_SLACK_BOT_TOKEN", " ")
    assert ScoutSettings.from_env().slack_bot_token is None
