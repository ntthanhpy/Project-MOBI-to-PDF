from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got: {raw!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "MOBI to PDF Converter")
    calibre_command: str = os.getenv("CALIBRE_COMMAND", "ebook-convert")
    max_upload_mb: int = _env_int("MAX_UPLOAD_MB", 100)
    conversion_timeout_seconds: int = _env_int("CONVERSION_TIMEOUT_SECONDS", 300)
    default_paper_size: str = os.getenv("DEFAULT_PAPER_SIZE", "a4").lower()
    default_margin_pt: int = _env_int("DEFAULT_MARGIN_PT", 36)
    default_add_page_numbers: bool = _env_bool("DEFAULT_ADD_PAGE_NUMBERS", True)
    default_add_toc: bool = _env_bool("DEFAULT_ADD_TOC", False)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


settings = Settings()
