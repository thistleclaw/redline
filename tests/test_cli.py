from __future__ import annotations

from redline.cli import main
from redline.secrets import gemini_key_path, load_gemini_api_key


def test_cli_auth_saves_and_clears_persistent_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("getpass.getpass", lambda _prompt: "test-cli-gemini-secret")

    main(["auth"])

    assert load_gemini_api_key() == "test-cli-gemini-secret"
    assert "mode 0600" in capsys.readouterr().out

    main(["auth", "--clear"])

    assert not gemini_key_path().exists()
    assert "removed" in capsys.readouterr().out
