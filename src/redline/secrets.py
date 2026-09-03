from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from redline.config import config_path


class SecretStoreError(RuntimeError):
    pass


def gemini_key_path() -> Path:
    return config_path().with_name("gemini.key")


def save_gemini_api_key(api_key: str, path: Path | None = None) -> Path:
    """Atomically save a Gemini API key in a user-only local file."""
    target = path or gemini_key_path()
    value = api_key.strip()
    if len(value) < 8 or any(character.isspace() for character in value):
        raise SecretStoreError("Gemini API key is empty or invalid")

    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        target.parent.chmod(0o700)
    except OSError as error:
        raise SecretStoreError(f"Cannot secure REDLINE config directory: {error}") from error

    descriptor = -1
    temporary_name = ""
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".gemini-key-", dir=target.parent, text=True
        )
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(value + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
        target.chmod(0o600)
    except OSError as error:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)
        raise SecretStoreError(f"Cannot save Gemini API key: {error}") from error
    return target


def load_gemini_api_key(path: Path | None = None) -> str | None:
    """Load the persistent key without following symlinks or accepting foreign ownership."""
    target = path or gemini_key_path()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise SecretStoreError(f"Cannot open Gemini API key: {error}") from error

    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise SecretStoreError("Gemini API key path is not a regular file")
        if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
            raise SecretStoreError("Gemini API key file is owned by another user")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = -1
            value = handle.read(4097).strip()
    except OSError as error:
        raise SecretStoreError(f"Cannot read Gemini API key: {error}") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    if len(value) < 8 or len(value) > 4096 or any(character.isspace() for character in value):
        raise SecretStoreError("Stored Gemini API key is empty or invalid")
    return value


def clear_gemini_api_key(path: Path | None = None) -> bool:
    target = path or gemini_key_path()
    try:
        target.unlink()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise SecretStoreError(f"Cannot remove Gemini API key: {error}") from error
    return True
