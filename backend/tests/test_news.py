"""Tests for the news-enrichment helpers (pure, no network).

    cd backend && .venv/Scripts/python -m pytest tests/test_news.py -q
"""
import os

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

from app.services import market_data as md  # noqa: E402


def test_clean_company_strips_suffixes():
    assert md._clean_company("Cloudflare, Inc.") == "Cloudflare"
    assert md._clean_company("Advanced Micro Devices, Inc.") == "Advanced Micro Devices"
    assert md._clean_company("Broadcom Inc.") == "Broadcom"
    assert md._clean_company("NextEra Energy, Inc.") == "NextEra Energy"
    assert md._clean_company(None) == ""


def test_merge_news_dedupes_and_sorts():
    yahoo = [{"title": "Cloudflare gains today", "published": "2026-07-08T10:00:00Z"}]
    google = [
        {"title": "Cloudflare gains today", "published": "2026-07-08T10:00:00Z"},  # dup
        {"title": "Cloudflare signs OpenAI pilot", "published": "2026-07-08T14:00:00Z"},
    ]
    merged = md._merge_news(yahoo, google, limit=8)
    titles = [n["title"] for n in merged]
    assert titles.count("Cloudflare gains today") == 1        # de-duped
    assert titles[0] == "Cloudflare signs OpenAI pilot"       # newest first
    assert len(merged) == 2


def test_merge_news_respects_limit():
    items = [{"title": f"headline {i}", "published": f"2026-07-0{i}T00:00:00Z"} for i in range(1, 9)]
    assert len(md._merge_news([], items, limit=3)) == 3
