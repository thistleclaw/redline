from __future__ import annotations

from redline.config import Config


def test_config_round_trips_language_and_ai_models_without_api_key(tmp_path):
    path = tmp_path / "config.toml"
    config = Config(
        initialized=True,
        language="en",
        ai_models=["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
    )

    config.save(path)
    loaded = Config.load(path)

    assert loaded.language == "en"
    assert loaded.ai_models == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
    assert "API key" in path.read_text(encoding="utf-8")
    assert "GEMINI_API_KEY =" not in path.read_text(encoding="utf-8")


def test_unknown_language_falls_back_to_russian(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[app]\nlanguage = "xx"\n', encoding="utf-8")

    assert Config.load(path).language == "ru"
