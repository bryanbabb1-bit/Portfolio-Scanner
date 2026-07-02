"""Application configuration.

All settings are environment-overridable so the same code runs locally (with
live Yahoo Finance data) and inside restricted sandboxes (mock data fallback).
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    # ------------------------------------------------------------------ data
    # "auto"  -> try yfinance, transparently fall back to mock on failure
    # "live"  -> force yfinance (errors surface)
    # "mock"  -> force deterministic mock data (great for demos / CI)
    DATA_MODE: str = os.getenv("DATA_MODE", "auto").lower()

    # How long (seconds) to cache a symbol's market data in-process.
    CACHE_TTL: int = int(os.getenv("CACHE_TTL", "300"))

    # ---------------------------------------------------------------- advisor
    # When enabled the backend shells out to the local `claude` CLI in headless
    # print mode, using the signed-in Claude subscription (no API key needed).
    ADVISOR_ENABLED: bool = _bool("ADVISOR_ENABLED", True)
    CLAUDE_BIN: str = os.getenv("CLAUDE_BIN", "claude")
    # Model tiers for token efficiency: routine notes/asks run on the standard
    # tier; deep research and the whole-book brief use the CLI's default
    # (best) model. "" = CLI default.
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "")
    CLAUDE_MODEL_STANDARD: str = os.getenv("CLAUDE_MODEL_STANDARD", "sonnet")
    ADVISOR_TIMEOUT: int = int(os.getenv("ADVISOR_TIMEOUT", "120"))
    # Cache advisor narratives longer than raw quotes — they are expensive.
    ADVISOR_CACHE_TTL: int = int(os.getenv("ADVISOR_CACHE_TTL", "3600"))

    # ------------------------------------------------------------------- http
    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")

    PORTFOLIO_FILE: Path = Path(
        os.getenv("PORTFOLIO_FILE", str(DATA_DIR / "portfolio.json"))
    )


settings = Settings()
