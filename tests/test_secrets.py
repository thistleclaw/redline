from __future__ import annotations

import stat

import pytest

from redline.secrets import (
    SecretStoreError,
    clear_gemini_api_key,
    load_gemini_api_key,
    save_gemini_api_key,
)


def test_persistent_gemini_key_round_trip_uses_user_only_permissions(tmp_path):
    target = tmp_path / "redline" / "gemini.key"

    saved = save_gemini_api_key("test-gemini-secret", target)

    assert saved == target
    assert load_gemini_api_key(target) == "test-gemini-secret"
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert clear_gemini_api_key(target)
    assert load_gemini_api_key(target) is None


def test_persistent_gemini_key_rejects_whitespace(tmp_path):
    with pytest.raises(SecretStoreError, match="invalid"):
        save_gemini_api_key("bad key", tmp_path / "gemini.key")


def test_persistent_gemini_key_refuses_symlink(tmp_path):
    actual = tmp_path / "actual.key"
    actual.write_text("test-gemini-secret", encoding="utf-8")
    link = tmp_path / "gemini.key"
    link.symlink_to(actual)

    with pytest.raises(SecretStoreError, match="Cannot open"):
        load_gemini_api_key(link)
