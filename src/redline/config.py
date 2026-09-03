from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from redline.i18n import normalize_language

APP_NAME = "redline"
DEFAULT_SOURCE_IDS = (
    "who_don",
    "who_sitreps",
    "who_hed",
    "cdc_outbreaks",
    "ecdc_cdtr",
    "paho_alerts",
    "africa_cdc_ebs",
    "who_blueprint",
)
DEFAULT_AI_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")


def config_path() -> Path:
    return (
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME / "config.toml"
    )


def data_dir() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME


def cache_dir() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / APP_NAME


@dataclass(slots=True)
class Config:
    initialized: bool = False
    language: str = "ru"
    theme: str = "navy_crt"
    crt_effects: bool = True
    watch_regions: list[str] = field(default_factory=list)
    sync_minutes: int = 15
    enabled_sources: list[str] = field(default_factory=lambda: list(DEFAULT_SOURCE_IDS))
    event_retention_days: int = 365
    document_cache_days: int = 30
    translation_enabled: bool = True
    ai_models: list[str] = field(default_factory=lambda: list(DEFAULT_AI_MODELS))
    ai_timeout_seconds: int = 60

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        path = path or config_path()
        if not path.exists():
            return cls()
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
        app = raw.get("app", {})
        sync = raw.get("sync", {})
        storage = raw.get("storage", {})
        sources = raw.get("sources", {})
        ai = raw.get("ai", {})
        return cls(
            initialized=bool(app.get("initialized", False)),
            language=normalize_language(str(app.get("language", "ru"))),
            theme=str(app.get("theme", "navy_crt")),
            crt_effects=bool(app.get("crt_effects", True)),
            watch_regions=[str(item) for item in app.get("watch_regions", [])],
            sync_minutes=max(1, int(sync.get("minutes", 15))),
            enabled_sources=[str(item) for item in sources.get("enabled", DEFAULT_SOURCE_IDS)],
            event_retention_days=max(1, int(storage.get("event_retention_days", 365))),
            document_cache_days=max(1, int(storage.get("document_cache_days", 30))),
            translation_enabled=bool(app.get("translation_enabled", True)),
            ai_models=[str(item) for item in ai.get("models", DEFAULT_AI_MODELS)],
            ai_timeout_seconds=max(10, min(180, int(ai.get("timeout_seconds", 60)))),
        )

    def save(self, path: Path | None = None) -> Path:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        sources = ", ".join(f'"{item}"' for item in self.enabled_sources)
        regions = ", ".join(f'"{item}"' for item in self.watch_regions)
        models = ", ".join(f'"{item}"' for item in self.ai_models)
        content = f'''# REDLINE sends no telemetry. Translation and explicit AI commands send limited data to Google.\n\n[app]\ninitialized = {str(self.initialized).lower()}\nlanguage = "{normalize_language(self.language)}"\ntheme = "{self.theme}"\ncrt_effects = {str(self.crt_effects).lower()}\ntranslation_enabled = {str(self.translation_enabled).lower()}\nwatch_regions = [{regions}]\n\n[sync]\nminutes = {self.sync_minutes}\n\n[storage]\nevent_retention_days = {self.event_retention_days}\ndocument_cache_days = {self.document_cache_days}\n\n[sources]\nenabled = [{sources}]\n\n[ai]\n# API key is stored separately in gemini.key or read from the environment.\nmodels = [{models}]\ntimeout_seconds = {self.ai_timeout_seconds}\n'''
        path.write_text(content, encoding="utf-8")
        return path
